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

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import (
    CLOSED_LEAD_STATUSES,
    ActivityType,
    BookingStatus,
    LeadStatus,
    WaitingOn,
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
    to_israel_tz,
)

logger = logging.getLogger(__name__)


class CalendarTemporarilyUnavailable(AppException):
    """Google מחובר אבל FreeBusy נכשל — לא לתת לבני אדם לבחור סלוטים שעלולים
    להתנגש עם אירועים אמיתיים ביומן.
    """

    status_code = 503
    code = "calendar_unavailable"
    user_message = (
        "סנכרון היומן כשל זמנית. אנא נסי שוב בעוד דקה."
    )


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


# ===== אופק ההזמנה =====
# הלקוח יכול לקבוע עד סוף החודש *הבא* (שעון ישראל), כלומר: החודש הנוכחי
# פתוח כולו + חודש אחד קדימה. ב-30 בספטמבר עדיין אפשר ספטמבר ואוקטובר,
# אבל לא נובמבר; ב-1 באוקטובר האופק מתגלגל ל-30 בנובמבר.
#
# למה החישוב הזה חי בשרת ולא רק ב-UI: הדף הציבורי שולח POST עם slot_start
# שהלקוח בחר, ו-token ב-URL הוא ה-credential היחיד. הסתרת תאריכים בממשק
# היא נוחות, לא אכיפה — בלי הבדיקה כאן אפשר לקבוע לנובמבר בקריאת API ישירה.
#
# תקרת הטווח פר-קריאה (31) מגינה מ-query כבד ל-Google FreeBusy. היא *לא*
# האופק — היא רק אומרת כמה ימים אפשר לשלוף במכה אחת, ולכן מספיקה בדיוק
# לחודש קלנדרי שלם. ה-frontend שולף חודש בכל קריאה.
MAX_AVAILABILITY_RANGE_DAYS = 31


def _first_of_month(d: date) -> date:
    return d.replace(day=1)


def _add_one_month(first_of_month: date) -> date:
    """מקדם ב-חודש קלנדרי אחד מתוך היום הראשון בחודש (בלי תלות באורך החודש)."""
    if first_of_month.month == 12:
        return date(first_of_month.year + 1, 1, 1)
    return date(first_of_month.year, first_of_month.month + 1, 1)


def booking_horizon_end(now_utc: datetime | None = None) -> date:
    """היום האחרון שאפשר לקבוע בו פגישה — סוף החודש הבא (שעון ישראל).

    מחושב כ"תחילת החודש שאחרי הבא, מינוס יום", כדי לא להתעסק באורכי
    חודשים ובשנים מעוברות.
    """
    now_utc = now_utc or datetime.now(timezone.utc)
    today_israel = to_israel_tz(now_utc).date()
    next_month = _add_one_month(_first_of_month(today_israel))
    month_after_next = _add_one_month(next_month)
    return month_after_next - timedelta(days=1)


# הודעת החריגה — זהה בשני מקומות האכיפה (זמינות + יצירה), כדי שהלקוח
# יראה את אותו הסבר בלי קשר לאיפה נעצר.
_BEYOND_HORIZON_MESSAGE = "אפשר לקבוע פגישה עד סוף החודש הבא בלבד."


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
        raise ConflictError("הפנייה כבר טופלה. צרי קשר אם רוצה לקבוע פגישה חדשה.")
    return lead


async def _get_active_booking(db: AsyncSession, lead_id: UUID) -> Booking | None:
    """בודק אם יש תור פעיל ל-lead — pending_approval או approved
    שהסלוט שלו עדיין בעתיד. סלוט שעבר לא נחשב כ-active גם אם הסטטוס
    לא הועבר ידנית (תופס מקרים שבהם נועה לא דחתה/אישרה לפני המועד)."""
    now_utc = datetime.now(timezone.utc)
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
            Booking.requested_slot_end > now_utc,
        )
        .order_by(Booking.requested_slot_start.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _expire_stale_bookings(
    db: AsyncSession, lead_id: UUID | None = None
) -> int:
    """
    מסמן bookings שהסלוט שלהם עבר אבל הסטטוס נשאר pending_approval/approved
    כ-CANCELED, *וגם* מאפס את סטטוס הליד אם הוא היה תקוע ב-BOOKING_PENDING
    או BOOKED בלי תור פעיל.

    הצורך הראשון: ה-partial unique index idx_bookings_active_lead חוסם כל
    active חדש לליד שיש לו active קיים — אם תור ישן לא הועבר לסטטוס סופי,
    הליד חסום מ-rebook גם זמן רב אחרי שהמועד עבר.

    הצורך השני (תיקון Cursor): סטטוס הליד נשאר תקוע — דשבורד מציג
    "ממתין לאישור" / "פגישה קבועה" בלי שיש תור פעיל מאחורי זה.

    lead_id=None → cleanup גלובלי (נקרא מ-cron). אחרת מסונן ללid יחיד
    (נקרא מ-create_booking_request לפני הוספת תור חדש).

    מחזיר מספר ה-bookings שבוטלו. אינדמפוטנטי.
    """
    from sqlalchemy import func, update

    now_utc = datetime.now(timezone.utc)

    # 1. מאתרים אילו leads מושפעים (לפני ה-UPDATE — אחרת לא נדע אילו)
    affected_stmt = select(Booking.lead_id, Booking.id).where(
        Booking.status.in_(
            [
                BookingStatus.PENDING_APPROVAL.value,
                BookingStatus.APPROVED.value,
            ]
        ),
        Booking.requested_slot_end < now_utc,
    )
    if lead_id is not None:
        affected_stmt = affected_stmt.where(Booking.lead_id == lead_id)
    affected_rows = (await db.execute(affected_stmt)).all()
    if not affected_rows:
        return 0

    affected_lead_ids = list({row.lead_id for row in affected_rows})

    # 2. מבטלים את ה-bookings הפגים
    cancel_stmt = (
        update(Booking)
        .where(
            Booking.status.in_(
                [
                    BookingStatus.PENDING_APPROVAL.value,
                    BookingStatus.APPROVED.value,
                ]
            ),
            Booking.requested_slot_end < now_utc,
        )
        .values(status=BookingStatus.CANCELED.value)
    )
    if lead_id is not None:
        cancel_stmt = cancel_stmt.where(Booking.lead_id == lead_id)
    await db.execute(cancel_stmt)

    # 3. מאפסים סטטוס leads שהיו תקועים. הpartial unique index מבטיח שאחרי
    # שלב 2 אין תור פעיל ל-leads האלה. WHERE על BOOKING_PENDING/BOOKED בלבד
    # — לא דורסים WON/LOST/ARCHIVED או IN_PROGRESS שמשתמש כבר עבר אליו ידנית.
    await db.execute(
        update(Lead)
        .where(
            Lead.id.in_(affected_lead_ids),
            Lead.status.in_(
                [
                    LeadStatus.BOOKING_PENDING.value,
                    LeadStatus.BOOKED.value,
                ]
            ),
        )
        .values(
            status=LeadStatus.IN_PROGRESS.value,
            waiting_on=WaitingOn.NOAH.value,
            last_activity_type=ActivityType.MEETING_CANCELED.value,
            updated_at=func.now(),
        )
    )

    # 4. activity לכל booking שבוטל — לתיעוד בtimeline. נעשה רק במצב הגלובלי
    # (lead_id=None) כדי לא להציף את ה-timeline ב-cleanup pre-insert של
    # create_booking_request (שם הוא חלק מ-flow רגיל ולא מעניין למשתמש).
    if lead_id is None:
        for row in affected_rows:
            await log_activity(
                db,
                lead_id=row.lead_id,
                activity_type=ActivityType.MEETING_CANCELED,
                performed_by=None,  # מערכת
                content="פגישה עברה זמנה ובוטלה אוטומטית ע\"י המערכת",
                metadata={
                    "booking_id": str(row.id),
                    "source": "expire_stale_cron",
                },
            )

    return len(affected_rows)


async def expire_all_stale_bookings(db: AsyncSession) -> int:
    """
    cleanup גלובלי של bookings פגים — נקרא מcron יומי. מחזיר ספירה.
    public wrapper סביב _expire_stale_bookings בלי lead_id.
    """
    count = await _expire_stale_bookings(db, lead_id=None)
    if count:
        await db.commit()
    return count


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
        today=to_israel_tz(datetime.now(timezone.utc)).date(),
        booking_horizon_end=booking_horizon_end(),
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

    שתי מגבלות *נפרדות* על הטווח (אסור לבלבל ביניהן):
    - MAX_AVAILABILITY_RANGE_DAYS — כמה ימים בקריאה אחת (הגנה על FreeBusy).
    - booking_horizon_end() — עד מתי בכלל אפשר לקבוע (סוף החודש הבא).
    """
    if date_to < date_from:
        raise ValidationError("date_to חייב להיות אחרי date_from.")
    if (date_to - date_from).days > MAX_AVAILABILITY_RANGE_DAYS:
        raise ValidationError(
            f"ניתן לבקש זמינות לטווח של עד {MAX_AVAILABILITY_RANGE_DAYS} ימים."
        )
    if date_to > booking_horizon_end():
        raise ValidationError(_BEYOND_HORIZON_MESSAGE)

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
    קורא ל-FreeBusy API של Google.

    שלוש דרכים לחזרה:
    - Google לא מחובר/לא מוגדר → ([], False): המשתמש בחר לא להשתמש בGoogle.
      DB-only הוא בסדר; ה-UI יציג "סנכרון יומן זמני לא פעיל".
    - מחובר + API הצליח → (busy, True).
    - מחובר + API נכשל → raise CalendarTemporarilyUnavailable.
      אסור לתת למשתמש לראות "slots פנויים" שעלולים להיות תפוסים
      ביומן האמיתי. הUI יציג הודעת retry. ההבחנה חשובה: לא-מחובר
      זו בחירה מודעת; failure זה incident שדורש fail-safe.
    """
    from app.services import google_calendar as gc_service

    try:
        creds = await gc_service.get_credentials_or_404(db)
    except (
        gc_service.GoogleNotConfiguredError,
        gc_service.GoogleNotConnectedError,
    ):
        # באמת לא מחובר — fallback ל-DB-only סביר.
        return [], False
    except gc_service.GoogleAuthInvalidError as e:
        # מחובר אבל auth שבור (refresh נכשל / revoke). מבחינת UX זה
        # "מחובר" — settings מציג חיבור פעיל. דילוג שקט יציג סלוטים
        # שעלולים להיות תפוסים ביומן האמיתי. fail-safe = לחסום עד
        # שהבעלים יחבר מחדש (מסומן ב-auth_invalid_at).
        raise CalendarTemporarilyUnavailable() from e

    try:
        busy = await asyncio.to_thread(
            _freebusy_query, creds, start_utc, end_utc
        )
        return busy, True
    except Exception as e:
        logger.exception("FreeBusy query failed for connected calendar")
        raise CalendarTemporarilyUnavailable() from e


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
    """
    כל ה-bookings הפעילים בטווח — pending_approval או approved, ועדיין בעתיד.

    תוספת requested_slot_end > now_utc: _expire_stale_bookings רץ רק
    לליד ספציפי ב-create_booking_request, אז bookings תקועים של לידים
    *אחרים* (פג מועדם אך לא עברו ל-canceled) ממשיכים להחזיק את הסלוט
    באוויר ולחסום זמינות. סינון ב-query הוא ההגנה הרוחבית הנכונה — לא
    דורש cleanup job גלובלי.
    """
    now_utc = datetime.now(timezone.utc)
    effective_start = max(start_utc, now_utc)
    stmt = select(
        Booking.requested_slot_start, Booking.requested_slot_end
    ).where(
        Booking.status.in_(
            [
                BookingStatus.PENDING_APPROVAL.value,
                BookingStatus.APPROVED.value,
            ]
        ),
        Booking.requested_slot_end > effective_start,
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
    # אופק ההזמנה — האכיפה האמיתית. ה-UI מסתיר תאריכים רחוקים, אבל
    # ה-endpoint ציבורי וה-token הוא ה-credential היחיד.
    if slot_start.astimezone(ISRAEL_TZ).date() > booking_horizon_end(now_utc):
        raise ValidationError(_BEYOND_HORIZON_MESSAGE)

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

    # cleanup ראשון: bookings ישנים ב-pending/approved שהמועד שלהם עבר
    # מועברים ל-CANCELED. בלי זה ה-partial unique index חוסם rebook אחרי
    # שתור עבר בלי שעבר transition סופי (ראה _expire_stale_bookings).
    await _expire_stale_bookings(db, lead.id)

    # ולידציה: אין כבר תור פעיל (בדיקה רכה, ה-DB unique index יתפוס race)
    existing = await _get_active_booking(db, lead.id)
    if existing is not None:
        raise ConflictError(
            "כבר יש לך בקשת פגישה פעילה. צרי קשר אם רוצה להחליף מועד."
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
            "הסלוט כבר תפוס או שיש לך כבר פגישה פעילה. בחרי מועד אחר."
        ) from e

    # סטטוס הליד → BOOKING_PENDING + עדכון CRM fields. mirror של request_meeting
    # ב-state_machine: last_inbound_at, reply_boost_until (קופץ לראש בדשבורד),
    # last_activity_type. אטומי דרך WHERE status IN (open) — אם הליד נסגר בינתיים
    # ה-UPDATE לא יבוצע ואנחנו מבטלים את ה-booking כדי לא להשאיר orphan.
    # BOOKING_PENDING כלול ב-open_statuses כדי לתמוך ב-rebook: ליד שכבר במצב
    # הזה (בקשה קודמת שנדחתה ללא reset) עדיין צריך לקבל refresh של ה-CRM fields.
    from sqlalchemy import func, update

    from app.services.lead_actions import REPLY_BOOST_HOURS

    open_statuses = [
        s.value
        for s in (
            LeadStatus.NEW,
            LeadStatus.IN_PROGRESS,
            LeadStatus.PROPOSAL_SENT,
            LeadStatus.BOOKED,
            LeadStatus.BOOKING_PENDING,
        )
    ]
    update_result = await db.execute(
        update(Lead)
        .where(Lead.id == lead.id, Lead.status.in_(open_statuses))
        .values(
            status=LeadStatus.BOOKING_PENDING.value,
            waiting_on="NOAH",
            last_inbound_at=now_utc,
            reply_boost_until=now_utc + timedelta(hours=REPLY_BOOST_HOURS),
            last_activity_type="meeting_requested",
            updated_at=func.now(),
        )
    )
    # אם ה-UPDATE לא תפס שורה — הליד נסגר/שונה בrace בין השליפה כאן.
    # מבטלים את ה-booking insert כדי לא להשאיר תור פעיל על ליד שלא יקבל
    # את הטיפול שמתחייב מבקשת פגישה.
    if update_result.rowcount != 1:
        await db.rollback()
        raise ConflictError(
            "מצב הפנייה השתנה בזמן השליחה. רעני את הדף ונסי שוב."
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

    # בקשת תור = touchpoint inbound (הלקוח חזר אלינו). סוגרת tasks תקועים
    # — בעיקר warm_followup ("הלקוח לא חזר") שכבר לא רלוונטי. ה-bypass
    # שתוקן: לפני כן ה-UPDATE לא סגר tasks, ו-warm_followup שרד אחרי שהלקוח
    # קבע תור. booking לא pure-inbound (transition ל-BOOKING_PENDING), אז
    # חולק רק את Layer 1 (close_touchpoint_tasks), לא register_inbound המלא.
    from app.services.lead_actions import close_touchpoint_tasks

    await close_touchpoint_tasks(db, lead.id, now_utc)

    # extract primitives לפני commit — אחרי commit ה-ORM attributes עלולים
    # להיות expired/lazy ולגרור MissingGreenlet ב-async session (כלל 5 ב-CLAUDE.md).
    booking_id = booking.id
    booking_status = booking.status
    booking_start = booking.requested_slot_start
    booking_end = booking.requested_slot_end

    await db.commit()

    # לא שולחים Telegram על בקשת תור — לפי Spec §16.3:
    # "הדבר היחיד שמקבל פוש מיידי הוא ליד חדש שנכנס".
    # ה-surfacing בדשבורד נעשה דרך get_pending: כל ליד ב-BOOKING_PENDING
    # נכלל ברשימת "ממתין לטיפול" כדי שלא ייפול בין הכיסאות. בנוסף
    # PendingBookingCard מציג את הבקשה בעמוד הליד עצמו.
    # (F-06 ב-docs/spec-deviations.md)

    return CreateBookingResponse(
        booking_id=booking_id,
        status=booking_status,
        slot_start=booking_start,
        slot_end=booking_end,
    )


# ===== Admin operations: list / approve / reject =====


async def list_pending_bookings(
    db: AsyncSession,
) -> list[tuple[Booking, Lead]]:
    """
    כל ה-bookings ב-pending_approval שעדיין בעתיד, עם פרטי הליד שלהם
    בtuple יחיד (חסכון בfk-fetch לכל שורה). מוין לפי מועד הסלוט (הקרוב
    הראשון — נועה מטפלת בסדר זה).
    """
    now_utc = datetime.now(timezone.utc)
    result = await db.execute(
        select(Booking, Lead)
        .join(Lead, Lead.id == Booking.lead_id)
        .where(
            Booking.status == BookingStatus.PENDING_APPROVAL.value,
            Booking.requested_slot_end > now_utc,
        )
        .order_by(Booking.requested_slot_start.asc())
    )
    return [(booking, lead) for booking, lead in result.all()]


async def get_active_booking_for_lead(
    db: AsyncSession, lead_id: UUID
) -> Booking | None:
    """
    מחזיר את ה-booking הרלוונטי לכרטיס הליד:
    1. pending_approval / approved שעדיין בעתיד (כמו _get_active_booking הפנימי).
    2. + APPROVED שעבר slot_end *אם* הליד עדיין במצב BOOKED — נדרש כדי
       שכפתור "סמני שהפגישה התקיימה" יישאר זמין אחרי שהפגישה הסתיימה.
       ברגע שנועה תסמן `log_call_completed`, הסטטוס יעבור (NEW/IN_PROGRESS
       בהתאם ל-state machine) וה-booking יחדל להופיע.

    _get_active_booking הפנימי נשאר strict (slot_end > now) — משמש
    ב-create_booking_request לבדיקת קונפליקטים, שם לא רוצים שעבר ישפיע.
    """
    active = await _get_active_booking(db, lead_id)
    if active is not None:
        return active

    # Fallback: ליד BOOKED עם APPROVED שעבר slot_end → מציגים כדי שכפתור
    # "סמני שהפגישה התקיימה" יופיע. מסנן גם past meetings ישנות שלא
    # נסגרו (>30 יום) כדי לא להציג zombie bookings אם משהו השתבש.
    from app.models.lead import Lead

    now_utc = datetime.now(timezone.utc)
    cutoff = now_utc - timedelta(days=30)
    result = await db.execute(
        select(Booking)
        .join(Lead, Lead.id == Booking.lead_id)
        .where(
            Booking.lead_id == lead_id,
            Booking.status == BookingStatus.APPROVED.value,
            Booking.requested_slot_end <= now_utc,
            Booking.requested_slot_end >= cutoff,
            Lead.status == LeadStatus.BOOKED.value,
        )
        .order_by(Booking.requested_slot_start.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def approve_booking(
    db: AsyncSession,
    booking_id: UUID,
    performed_by_id: UUID,
) -> Booking:
    """
    מאשר booking pending → approved + יוצר אירוע ביומן + ליד → BOOKED.

    fail-safe: אם יצירת אירוע ביומן נכשלת כשהיומן מחובר אך שבור — rollback
    מלא, ה-booking נשאר pending_approval. אסור שנועה תחשוב שהפגישה ביומן
    אם לא. אם היומן בכלל לא מחובר — ממשיכים בלי event_id (היא מודעת
    לכך שהאינטגרציה כבויה).
    """
    from sqlalchemy import func, update

    from app.services import google_calendar as gc_service

    now_utc = datetime.now(timezone.utc)

    # 1. UPDATE אטומי על ה-booking. WHERE status=pending מבטיח שאישור
    # מקבילי לא יעבור פעמיים.
    # WHERE כולל requested_slot_end > now — אטומי, מונע אישור של תור שפג.
    # אחרת ה-UI מסתיר את הbooking (list_pending מסנן עבר) אבל POST ידני
    # היה מצליח ויוצר אירוע ביומן בעבר + מעביר ליד ל-BOOKED.
    booking_update = await db.execute(
        update(Booking)
        .where(
            Booking.id == booking_id,
            Booking.status == BookingStatus.PENDING_APPROVAL.value,
            Booking.requested_slot_end > now_utc,
        )
        .values(
            status=BookingStatus.APPROVED.value,
            approved_at=now_utc,
        )
    )
    if booking_update.rowcount != 1:
        # מבדילים בין שני המקרים כדי לתת הודעה מדויקת לנועה.
        existing = (
            await db.execute(
                select(Booking.status, Booking.requested_slot_end).where(
                    Booking.id == booking_id
                )
            )
        ).first()
        if existing is None:
            raise ConflictError("בקשת הפגישה לא נמצאה.")
        if existing.requested_slot_end <= now_utc:
            raise ConflictError(
                "הפגישה חלפה ולא ניתן עוד לאשרה. בקשי מהליד לבחור מועד חדש."
            )
        raise ConflictError(
            "הבקשה כבר עברה לסטטוס אחר. רעני את הדף ונסי שוב."
        )

    # 2. שליפת ה-booking + ה-lead לserialization של summary/description
    booking_row = (
        await db.execute(
            select(Booking)
            .where(Booking.id == booking_id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    lead = (
        await db.execute(
            select(Lead)
            .where(Lead.id == booking_row.lead_id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()

    # 3. ליד → BOOKED, waiting_on=CLIENT (הליד אמור להגיע לפגישה).
    # WHERE מסנן כל סטטוס סגור — אם הליד נסגר בrace בין השליפה ל-UPDATE,
    # rowcount=0 יגרור rollback ולא יישאר booking שמצביע על ליד סגור.
    closed_values = [s.value for s in CLOSED_LEAD_STATUSES]
    lead_update = await db.execute(
        update(Lead)
        .where(Lead.id == lead.id, ~Lead.status.in_(closed_values))
        .values(
            status=LeadStatus.BOOKED.value,
            waiting_on=WaitingOn.CLIENT.value,
            last_activity_type="meeting_approved",
            updated_at=func.now(),
        )
    )
    if lead_update.rowcount != 1:
        await db.rollback()
        raise ConflictError(
            "מצב הליד השתנה בזמן האישור. רעני את הדף ונסי שוב."
        )

    await log_activity(
        db,
        lead_id=lead.id,
        activity_type=ActivityType.MEETING_APPROVED,
        performed_by=performed_by_id,
        metadata={
            "booking_id": str(booking_id),
            "slot_start": booking_row.requested_slot_start.isoformat(),
            "slot_end": booking_row.requested_slot_end.isoformat(),
        },
    )

    # 4. יצירת אירוע ביומן — לפני commit כדי שאם נכשל נוכל rollback.
    event_id: str | None = None
    try:
        from app.utils.labels import SERVICE_SUBTYPE_HE

        summary = f"פגישה — {lead.full_name}"
        # תיאור ידידותי לנועה: רק מה ששימושי לפגישה עצמה. שדות טכניים
        # (booking_id, category code) הוסרו ב-§3.6 של phase-2.5-plan.md —
        # ה-bookingId כבר ב-extendedProperties.private (העוגן לסנכרון
        # הפוך), לא צריך להציג למשתמש.
        desc_lines: list[str] = []
        if lead.service_subtype:
            subtype_he = SERVICE_SUBTYPE_HE.get(
                lead.service_subtype, lead.service_subtype
            )
            desc_lines.append(f"סוג שירות: {subtype_he}")
        if lead.organization_name:
            desc_lines.append(f"ארגון: {lead.organization_name}")
        if lead.phone:
            desc_lines.append(f"טלפון: {lead.phone}")
        if lead.email:
            desc_lines.append(f"מייל: {lead.email}")
        description = "\n".join(desc_lines)

        event_id = await gc_service.create_calendar_event(
            db,
            booking_id=booking_id,
            summary=summary,
            description=description,
            start=booking_row.requested_slot_start,
            end=booking_row.requested_slot_end,
        )
    except (
        gc_service.GoogleNotConfiguredError,
        gc_service.GoogleNotConnectedError,
    ):
        # יומן לא מחובר — בחירה מודעת. ממשיכים בלי event_id.
        pass
    except gc_service.GoogleAuthInvalidError as e:
        await db.rollback()
        raise CalendarTemporarilyUnavailable() from e
    except Exception as e:
        logger.exception("Failed to create Google event for approved booking")
        await db.rollback()
        raise CalendarTemporarilyUnavailable() from e

    # 5. שמירת event_id ב-booking (אם נוצר)
    if event_id is not None:
        await db.execute(
            update(Booking)
            .where(Booking.id == booking_id)
            .values(google_calendar_event_id=event_id)
        )

    # 6. commit עם compensation: אם נכשל ויש לנו event_id, מוחקים את
    # האירוע ביומן כדי לא להשאיר orphan (פגישה שמופיעה ביומן של נועה
    # בלי רישום מקביל במערכת). delete_calendar_event אינדמפוטנטי
    # (404/410 נספגים), אז עוד retry של approve_booking לא ייצור כפילות.
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        if event_id is not None:
            try:
                await gc_service.delete_calendar_event(db, event_id)
            except Exception:
                logger.exception(
                    "Failed to delete orphaned Google event %s after commit failure",
                    event_id,
                )
        raise

    # refetch אחרי commit כדי להחזיר נתונים עדכניים (event_id וכו')
    return (
        await db.execute(
            select(Booking)
            .where(Booking.id == booking_id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()


async def reject_booking(
    db: AsyncSession,
    booking_id: UUID,
    performed_by_id: UUID,
) -> Booking:
    """
    דוחה booking pending → rejected, ליד חוזר ל-IN_PROGRESS (נועה תחליט
    מה עכשיו). אטומי דרך WHERE status=pending.
    """
    from sqlalchemy import func, update

    now_utc = datetime.now(timezone.utc)

    booking_update = await db.execute(
        update(Booking)
        .where(
            Booking.id == booking_id,
            Booking.status == BookingStatus.PENDING_APPROVAL.value,
        )
        .values(
            status=BookingStatus.REJECTED.value,
            rejected_at=now_utc,
        )
    )
    if booking_update.rowcount != 1:
        raise ConflictError(
            "הבקשה כבר עברה לסטטוס אחר. רעני את הדף ונסי שוב."
        )

    booking_row = (
        await db.execute(
            select(Booking)
            .where(Booking.id == booking_id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()

    # ליד חזרה ל-IN_PROGRESS — נועה צריכה להחליט אם להציע מועד אחר/לסגור.
    # waiting_on=NOAH כי הכדור חזר אליה.
    await db.execute(
        update(Lead)
        .where(
            Lead.id == booking_row.lead_id,
            Lead.status == LeadStatus.BOOKING_PENDING.value,
        )
        .values(
            status=LeadStatus.IN_PROGRESS.value,
            waiting_on="NOAH",
            last_activity_type="meeting_rejected",
            updated_at=func.now(),
        )
    )
    # rowcount לא נבדק — ליד שכבר ב-status אחר (למשל BOOKED מbooking אחר)
    # פשוט לא יושפע. ה-booking עצמו עבר ל-rejected וזה ה-source of truth.

    await log_activity(
        db,
        lead_id=booking_row.lead_id,
        activity_type=ActivityType.MEETING_REJECTED,
        performed_by=performed_by_id,
        metadata={"booking_id": str(booking_id)},
    )

    await db.commit()

    return (
        await db.execute(
            select(Booking)
            .where(Booking.id == booking_id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
