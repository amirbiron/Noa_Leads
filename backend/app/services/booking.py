"""
שירות booking — דף קביעת תור ציבורי + חישוב זמינות + יצירת בקשה.

חישוב סלוטים פנויים = שעות עבודה ∩ ¬(Google FreeBusy ∪ DB busy).
ראה: docs/references/google-calendar-blueprint.md סעיף 3.

עיצובי החלטות:
- אם Google לא מחובר — מחשבים סלוטים על בסיס שעות עבודה + DB busy בלבד.
  ה-flag includes_google_busy=False ב-response נותן ל-UI להציג הערה.
- כל סלוט = משך ברירת מחדל לפי service_category (60/120 דק').
- קפיצות של 30 דק' (slot_step) — סטנדרט עם dgalia ל-UI.
- אין יצירת תור על סלוט שבעבר. אין יצירה אם כבר יש pending/approved
  לאותו ליד (UX — מעדיפים שתבטל קודם).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import (
    CLOSED_LEAD_STATUSES,
    ActivityType,
    BookingStatus,
    LeadStatus,
)
from app.core.exceptions import (
    AppException,
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.models.booking import Booking
from app.models.lead import Lead
from app.schemas.booking_page import (
    BookingPageInfo,
    CreateBookingResponse,
    DayAvailability,
    TimeSlot,
)
from app.services.activities import log_activity
from app.utils.work_hours import (
    ISRAEL_TZ,
    is_friday,
    is_holiday,
    is_holiday_eve,
    is_saturday,
)

logger = logging.getLogger(__name__)


# ===== ברירות מחדל למשך תור לפי קטגוריה =====
_DEFAULT_BOOKING_DURATION_MIN: dict[str, int] = {
    "clinic": 60,
    "workshops": 120,
    "production": 60,
    "digital_course": 60,
}
_FALLBACK_DURATION = 60
_SLOT_STEP_MINUTES = 30


def default_duration_minutes(service_category: str) -> int:
    return _DEFAULT_BOOKING_DURATION_MIN.get(service_category, _FALLBACK_DURATION)


# ===== Lead lookup by booking_token =====


async def get_lead_by_booking_token(db: AsyncSession, token: UUID) -> Lead:
    """
    שולף ליד לפי booking_token. זורק NotFoundError לטוקן לא ידוע,
    ConflictError לליד סגור (UI יציג "פנייה זו כבר נסגרה").
    """
    result = await db.execute(
        select(Lead)
        .where(Lead.booking_token == token)
        .execution_options(populate_existing=True)
    )
    lead = result.scalar_one_or_none()
    if lead is None:
        raise NotFoundError("הקישור לא תקף או שפג תוקפו.")
    if lead.status in CLOSED_LEAD_STATUSES:
        raise ConflictError("הפנייה כבר טופלה. צרי קשר אם רוצה לקבוע תור חדש.")
    return lead


async def _get_active_booking(db: AsyncSession, lead_id: UUID) -> Booking | None:
    """בודק אם יש תור פעיל ל-lead — pending_approval או approved."""
    result = await db.execute(
        select(Booking)
        .where(
            Booking.lead_id == lead_id,
            Booking.status.in_(
                [
                    BookingStatus.PENDING_APPROVAL.value,
                    BookingStatus.APPROVED.value,
                ]
            ),
        )
        .order_by(Booking.requested_slot_start.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


# ===== Public page info =====


async def get_booking_page_info(db: AsyncSession, token: UUID) -> BookingPageInfo:
    lead = await get_lead_by_booking_token(db, token)
    active = await _get_active_booking(db, lead.id)
    return BookingPageInfo(
        lead_name=lead.full_name,
        service_category=lead.service_category,
        service_subtype=lead.service_subtype,
        default_duration_minutes=default_duration_minutes(lead.service_category),
        has_active_booking=active is not None,
        active_booking_at=active.requested_slot_start if active else None,
        active_booking_end=active.requested_slot_end if active else None,
        active_booking_status=active.status if active else None,
    )


# ===== Availability computation =====


async def get_availability(
    db: AsyncSession,
    token: UUID,
    date_from: date,
    date_to: date,
) -> tuple[list[DayAvailability], bool]:
    """
    מחזיר זמינות בטווח [date_from, date_to] (שניהם inclusive).
    מגביל ל-14 ימים מקסימום למניעת query מאסיבי מ-Google.
    """
    if date_to < date_from:
        raise ValidationError("date_to חייב להיות אחרי date_from.")
    if (date_to - date_from).days > 14:
        raise ValidationError("ניתן לבקש זמינות לטווח של עד 14 ימים.")

    lead = await get_lead_by_booking_token(db, token)
    duration = default_duration_minutes(lead.service_category)

    # שליפת busy ranges פעם אחת לכל הטווח (יעיל יותר מקריאה ליום)
    range_start_utc, range_end_utc = _range_utc_bounds(date_from, date_to)
    google_busy, includes_google = await _fetch_google_busy(
        db, range_start_utc, range_end_utc
    )
    db_busy = await _fetch_db_busy(db, range_start_utc, range_end_utc)
    all_busy = google_busy + db_busy

    now_utc = datetime.now(timezone.utc)
    days: list[DayAvailability] = []
    current = date_from
    while current <= date_to:
        candidates = _candidate_slots(current, duration)
        free = [
            TimeSlot(start=s, end=e)
            for s, e in candidates
            if _slot_free(s, e, all_busy, now_utc)
        ]
        days.append(DayAvailability(date=current, slots=free))
        current = current + timedelta(days=1)

    return days, includes_google


def _range_utc_bounds(
    date_from: date, date_to: date
) -> tuple[datetime, datetime]:
    """תחילת date_from + סוף date_to (exclusive) ב-UTC."""
    start_local = datetime.combine(date_from, time(0, 0, tzinfo=ISRAEL_TZ))
    end_local = datetime.combine(date_to + timedelta(days=1), time(0, 0, tzinfo=ISRAEL_TZ))
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def _candidate_slots(
    target_date: date, duration_minutes: int
) -> list[tuple[datetime, datetime]]:
    """
    מחזיר את כל הסלוטים הפוטנציאליים ליום, לפי שעות עבודה ובלי overlap.
    שבת/חג מלא → רשימה ריקה. ערב חג/שישי → עד FRIDAY_CLOSE_HOUR.
    """
    from app.config import get_settings

    if is_saturday(target_date) or is_holiday(target_date):
        return []

    settings = get_settings()
    start_hour = settings.work_day_start_hour
    if is_friday(target_date) or is_holiday_eve(target_date):
        end_hour = settings.friday_close_hour
    else:
        end_hour = settings.work_day_end_hour

    start = datetime.combine(target_date, time(start_hour, 0, tzinfo=ISRAEL_TZ))
    end = datetime.combine(target_date, time(end_hour, 0, tzinfo=ISRAEL_TZ))

    slots: list[tuple[datetime, datetime]] = []
    current = start
    delta = timedelta(minutes=duration_minutes)
    step = timedelta(minutes=_SLOT_STEP_MINUTES)
    while current + delta <= end:
        slots.append((current, current + delta))
        current += step
    return slots


def _slot_free(
    slot_start: datetime,
    slot_end: datetime,
    busy_ranges: list[tuple[datetime, datetime]],
    now: datetime,
) -> bool:
    if slot_start < now:
        return False
    for b_start, b_end in busy_ranges:
        # overlap מתקיים אם השלובים נחתכים אפילו ב-1 דקה
        if slot_start < b_end and slot_end > b_start:
            return False
    return True


# ===== Busy sources =====


async def _fetch_google_busy(
    db: AsyncSession, start_utc: datetime, end_utc: datetime
) -> tuple[list[tuple[datetime, datetime]], bool]:
    """
    קורא ל-FreeBusy API של Google. אם Google לא מחובר → מחזיר ([], False).
    אם מחובר אבל שגיאת API → log + מחזיר ([], True) (אופטימי, ה-DB busy יתפוס מקרים פעילים).
    """
    from app.services import google_calendar as gc_service

    try:
        creds = await gc_service.get_credentials_or_404(db)
    except (
        gc_service.GoogleNotConfiguredError,
        gc_service.GoogleNotConnectedError,
        gc_service.GoogleAuthInvalidError,
    ):
        return [], False

    try:
        busy = await asyncio.to_thread(
            _freebusy_query, creds, start_utc, end_utc
        )
        return busy, True
    except Exception:
        logger.exception("FreeBusy query failed; falling back to DB-busy only")
        # מחזירים False כדי שה-UI יציג את אותה הודעה כמו ב-not_connected:
        # "סנכרון יומן זמני לא פעיל". המשתמש יבין שייתכן שיש אירוע ביומן
        # שלא נספר. כיוון שהאמת היא שהקריאה נכשלה — זה דיוק יותר טוב
        # מאשר להגיד שהסנכרון פעיל.
        return [], False


def _freebusy_query(
    creds, start_utc: datetime, end_utc: datetime
) -> list[tuple[datetime, datetime]]:
    """blocking call ל-Google API — נקרא רק בתוך asyncio.to_thread."""
    from googleapiclient.discovery import build

    service = build("calendar", "v3", credentials=creds, cache_discovery=False)
    body = {
        "timeMin": start_utc.isoformat(),
        "timeMax": end_utc.isoformat(),
        "timeZone": "Asia/Jerusalem",
        "items": [{"id": "primary"}],
    }
    result = service.freebusy().query(body=body).execute()
    busy_list = result.get("calendars", {}).get("primary", {}).get("busy", [])
    parsed: list[tuple[datetime, datetime]] = []
    for b in busy_list:
        # ISO 8601 עם timezone offset — fromisoformat מטפל
        parsed.append(
            (
                datetime.fromisoformat(b["start"]).astimezone(timezone.utc),
                datetime.fromisoformat(b["end"]).astimezone(timezone.utc),
            )
        )
    return parsed


async def _fetch_db_busy(
    db: AsyncSession, start_utc: datetime, end_utc: datetime
) -> list[tuple[datetime, datetime]]:
    """כל ה-bookings הפעילים בטווח — pending_approval או approved."""
    stmt = select(
        Booking.requested_slot_start, Booking.requested_slot_end
    ).where(
        Booking.status.in_(
            [
                BookingStatus.PENDING_APPROVAL.value,
                BookingStatus.APPROVED.value,
            ]
        ),
        Booking.requested_slot_end > start_utc,
        Booking.requested_slot_start < end_utc,
    )
    rows = (await db.execute(stmt)).all()
    return [(s, e) for s, e in rows]


# ===== Create booking =====


async def create_booking_request(
    db: AsyncSession,
    token: UUID,
    slot_start: datetime,
    slot_end: datetime,
    notes: str | None = None,
) -> CreateBookingResponse:
    """
    יוצר בקשת תור (status=pending_approval). אטומי דרך partial unique
    index על (lead_id, requested_slot_start). מסמן את הליד כ-BOOKING_PENDING
    + מתעד activity + שולח התראה לנועה.
    """
    lead = await get_lead_by_booking_token(db, token)

    # ולידציה בסיסית: עתידי + סדר זמנים
    now_utc = datetime.now(timezone.utc)
    if slot_start < now_utc:
        raise ValidationError("הסלוט שנבחר כבר עבר. רעני את הדף וכבחרי שוב.")
    if slot_end <= slot_start:
        raise ValidationError("נתוני זמן לא תקינים.")

    # ולידציה מחמירה: הסלוט חייב להתאים לכללי הזמינות (שעות עבודה,
    # יום עבודה, אורך לפי קטגוריה, יישור ל-grid 30 דק'). אחרת קלינט
    # זדוני יכול לבקש 03:00 בשבת בלילה.
    duration = default_duration_minutes(lead.service_category)
    actual_duration = (slot_end - slot_start).total_seconds() / 60
    if abs(actual_duration - duration) > 0.01:
        raise ValidationError(
            f"משך הסלוט חייב להיות {duration} דקות."
        )
    day_local = slot_start.astimezone(ISRAEL_TZ).date()
    candidates = _candidate_slots(day_local, duration)
    # השוואה ב-UTC כדי לא להסתבך עם offset
    target = (
        slot_start.astimezone(timezone.utc),
        slot_end.astimezone(timezone.utc),
    )
    candidates_utc = [
        (cs.astimezone(timezone.utc), ce.astimezone(timezone.utc))
        for cs, ce in candidates
    ]
    if target not in candidates_utc:
        raise ValidationError(
            "המועד לא בטווח הסלוטים המוצעים. בחרי מועד מהרשימה."
        )

    # ולידציה: אין כבר תור פעיל (בדיקה רכה, ה-DB unique index יתפוס race)
    existing = await _get_active_booking(db, lead.id)
    if existing is not None:
        raise ConflictError(
            "כבר יש לך בקשת תור פעילה. צרי קשר אם רוצה להחליף מועד."
        )

    # בדיקה חוזרת מול busy ranges — מגן מ-race בין הצגת הסלוט לאישור.
    # ה-DB EXCLUDE constraint יתפוס כל race שיחמוק מכאן.
    google_busy, _ = await _fetch_google_busy(db, slot_start, slot_end)
    db_busy = await _fetch_db_busy(db, slot_start, slot_end)
    if not _slot_free(slot_start, slot_end, google_busy + db_busy, now_utc):
        raise ConflictError(
            "הסלוט כבר תפוס. בחרי מועד אחר מהרשימה המעודכנת."
        )

    # insert + עדכון סטטוס הליד באותה טרנזקציה.
    # DB constraints (ראה migration 0006):
    # - idx_bookings_active_lead UNIQUE WHERE active → תופס race "2 תורים לליד"
    # - ck_bookings_no_overlap EXCLUDE WHERE active → תופס race "2 תורים לאותו slot"
    booking = Booking(
        lead_id=lead.id,
        requested_slot_start=slot_start,
        requested_slot_end=slot_end,
        status=BookingStatus.PENDING_APPROVAL.value,
    )
    db.add(booking)
    try:
        await db.flush()
    except IntegrityError as e:
        await db.rollback()
        # שתי האפשרויות הופכות לאותה הודעה ידידותית למשתמש
        raise ConflictError(
            "הסלוט כבר תפוס או שיש לך כבר תור פעיל. בחרי מועד אחר."
        ) from e

    # סטטוס הליד → BOOKING_PENDING (atomic, רק אם פתוח)
    from sqlalchemy import func, update

    open_statuses = [s.value for s in (LeadStatus.NEW, LeadStatus.IN_PROGRESS, LeadStatus.PROPOSAL_SENT, LeadStatus.BOOKED)]
    await db.execute(
        update(Lead)
        .where(Lead.id == lead.id, Lead.status.in_(open_statuses))
        .values(
            status=LeadStatus.BOOKING_PENDING.value,
            waiting_on="NOAH",
            updated_at=func.now(),
        )
    )

    await log_activity(
        db,
        lead_id=lead.id,
        activity_type=ActivityType.MEETING_REQUESTED,
        performed_by=None,  # public — אין user מחובר
        content=notes,
        metadata={
            "booking_id": str(booking.id),
            "slot_start": slot_start.isoformat(),
            "slot_end": slot_end.isoformat(),
        },
    )

    await db.commit()
    await db.refresh(booking)

    # התראה לנועה — אחרי commit, ושגיאה לא הופלת את ה-flow
    try:
        from app.services import telegram as telegram_service

        await telegram_service.notify_booking_requested(
            lead_name=lead.full_name,
            slot_start_iso=slot_start.isoformat(),
        )
    except Exception:
        logger.exception("Telegram notify_booking_requested failed")

    return CreateBookingResponse(
        booking_id=booking.id,
        status=booking.status,
        slot_start=booking.requested_slot_start,
        slot_end=booking.requested_slot_end,
    )
