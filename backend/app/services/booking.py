"""
שירות booking — דף קביעת פגישה ציבורי + חישוב זמינות + קביעה וביטול.

חישוב סלוטים פנויים = שעות עבודה ∩ ¬(Google FreeBusy ∪ DB busy).
ראה: docs/references/google-calendar-blueprint.md סעיף 3.

עיצובי החלטות:
- **הפגישה נקבעת מיד ואין שלב אישור.** הליד בוחר מועד, הפגישה נשמרת
  כ-approved והאירוע נוצר ביומן באותה טרנזקציה. `approve_booking` /
  `reject_booking` הוסרו; `cancel_booking` החליף אותם.
- **ליד יכול להחזיק כמה פגישות עתידיות** (עד
  `MAX_ACTIVE_BOOKINGS_PER_LEAD`) — הקישור לדף ניתן לשימוש חוזר. זה
  מה שהמיגרציה 0032 אפשרה כשהסירה את `idx_bookings_active_lead`.
- אם Google לא מחובר — מחשבים סלוטים על בסיס שעות עבודה + DB busy בלבד.
  ה-flag includes_google_busy=False ב-response נותן ל-UI להציג הערה.
- הזמינות נבדקת מול **כל** היומנים שנועה סימנה כתפוסים; הפגישות עצמן
  נכתבות ליומן יעד אחד בלבד, כדי שלא ייווצר אירוע כפול.
- כל סלוט = משך ברירת מחדל לפי service_category (60/120 דק').
- קפיצות של 30 דק' (slot_step) — סטנדרט עם dgalia ל-UI.
- אין קביעה על סלוט שבעבר.

**חריגה מודעת מכלל 15** (service עושה flush, ה-route עושה commit):
`create_booking_request` ו-`cancel_booking` עושים commit בעצמם. הסיבה
היא ה-compensation מול Google — הקוד חייב לדעת מתי ה-commit נכשל כדי
למחוק אירוע יתום, והעברת גבול הטרנזקציה ל-route הייתה שוברת בדיוק את
החלק הזה.
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
    BookingCancelSource,
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
    UpcomingBooking,
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


# סטטוסים שנחשבים "פגישה פעילה". `pending_approval` נשאר ברשימה עבור
# שורות שנוצרו לפני ביטול שלב האישור — הן עדיין תופסות סלוט ביומן
# ועדיין צריכות להיספר.
ACTIVE_BOOKING_STATUSES = [
    BookingStatus.PENDING_APPROVAL.value,
    BookingStatus.APPROVED.value,
]

# כמה פגישות עתידיות מותר לליד אחד להחזיק בו-זמנית.
#
# הקישור לדף קביעת הפגישה הוא קבוע ואינו מוגבל בזמן, ואחרי ביטול שלב
# האישור אין יותר אדם שמאשר כל פגישה. בלי תקרה, ליד אחד יכול לתפוס
# חלקים גדולים מהיומן — בטעות או בזדון. 3 מכסה את התרחיש האמיתי
# ("לקבוע עוד פגישה") ועוצר את השאר.
MAX_ACTIVE_BOOKINGS_PER_LEAD = 3


async def _active_bookings(db: AsyncSession, lead_id: UUID) -> list[Booking]:
    """כל הפגישות הפעילות והעתידיות של ליד, **בסדר עולה**.

    סלוט שעבר לא נחשב פעיל גם אם הסטטוס לא הועבר ידנית (תופס מקרים
    שבהם פגישה לא נסגרה לפני המועד).

    הגרסה הקודמת החזירה שורה אחת ממוינת `.desc()` — כלומר את הפגישה
    ה**רחוקה** ביותר. כל עוד הייתה רק אחת זה היה חסר משמעות; מרגע
    שליד יכול להחזיק כמה פגישות, "הבאה בתור" חייבת להיות הראשונה.
    """
    now_utc = datetime.now(timezone.utc)
    result = await db.execute(
        select(Booking)
        .where(
            Booking.lead_id == lead_id,
            Booking.status.in_(ACTIVE_BOOKING_STATUSES),
            Booking.requested_slot_end > now_utc,
        )
        .order_by(Booking.requested_slot_start.asc())
    )
    return list(result.scalars().all())


async def release_lead_if_no_active_booking(
    db: AsyncSession, lead_id: UUID
) -> bool:
    """מחזיר ליד מ-BOOKED ל-IN_PROGRESS — אבל רק אם לא נשארה לו פגישה.

    זו נקודת החנק היחידה לכל שלושת מסלולי הביטול: ביטול ביומן Google
    (`booking_sync._apply_cancellation`), ביטול ידני (`cancel_booking`),
    וניקוי פגישות שפג מועדן (`_expire_stale_bookings`).

    עד שליד יכול היה להחזיק פגישה אחת בלבד, ההורדה ל-IN_PROGRESS
    הייתה ללא תנאי. עכשיו ביטול של פגישה אחת מתוך שתיים היה מוריד את
    הסטטוס בזמן שהשנייה עוד עומדת.

    ה-`NOT EXISTS` מוערך **בתוך** ה-UPDATE ולא לפניו — זה מה שהופך את
    זה לאטומי (CLAUDE.md כלל 2). בדיקה נפרדת לפני ה-UPDATE הייתה
    check-then-act, ושני ביטולים מקבילים היו יכולים שניהם לראות
    "נשארה עוד אחת" ואף אחד לא היה משחרר את הליד.

    מחזיר True אם הליד שוחרר.
    """
    from sqlalchemy import func, update

    now_utc = datetime.now(timezone.utc)
    still_active = (
        select(Booking.id)
        .where(
            Booking.lead_id == lead_id,
            Booking.status.in_(ACTIVE_BOOKING_STATUSES),
            Booking.requested_slot_end > now_utc,
        )
        .exists()
    )
    result = await db.execute(
        update(Lead)
        .where(
            Lead.id == lead_id,
            Lead.status == LeadStatus.BOOKED.value,
            ~still_active,
        )
        .values(
            status=LeadStatus.IN_PROGRESS.value,
            waiting_on=WaitingOn.NOAH.value,
            last_activity_type=ActivityType.MEETING_CANCELED.value,
            updated_at=func.now(),
        )
    )
    return result.rowcount == 1


async def _expire_stale_bookings(
    db: AsyncSession, lead_id: UUID | None = None
) -> int:
    """
    מסמן bookings שהסלוט שלהם עבר אבל הסטטוס נשאר pending_approval/approved
    כ-CANCELED, *וגם* מאפס את סטטוס הליד אם הוא היה תקוע ב-BOOKING_PENDING
    או BOOKED בלי תור פעיל.

    הצורך: סטטוס הליד נשאר תקוע — דשבורד מציג "ממתין לאישור" /
    "פגישה קבועה" בלי שיש פגישה פעילה מאחורי זה.

    (הצורך המקורי — שחרור ה-partial unique index `idx_bookings_active_lead`
    כדי לאפשר קביעה חוזרת — כבר לא קיים: המיגרציה 0032 הסירה את
    האינדקס, וליד יכול להחזיק כמה פגישות.)

    lead_id=None → cleanup גלובלי (נקרא מ-cron). אחרת מסונן ללid יחיד
    (נקרא מ-create_booking_request לפני הוספת תור חדש).

    מחזיר מספר ה-bookings שבוטלו. אינדמפוטנטי.
    """
    from sqlalchemy import func, update

    now_utc = datetime.now(timezone.utc)

    # 1. מאתרים אילו leads מושפעים (לפני ה-UPDATE — אחרת לא נדע אילו)
    affected_stmt = select(Booking.lead_id, Booking.id).where(
        Booking.status.in_(ACTIVE_BOOKING_STATUSES),
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
            Booking.status.in_(ACTIVE_BOOKING_STATUSES),
            Booking.requested_slot_end < now_utc,
        )
        .values(status=BookingStatus.CANCELED.value)
    )
    if lead_id is not None:
        cancel_stmt = cancel_stmt.where(Booking.lead_id == lead_id)
    await db.execute(cancel_stmt)

    # 3. מאפסים סטטוס leads שהיו תקועים — אבל **רק אם לא נשארה להם
    # פגישה פעילה**. עד מיגרציה 0032 האינדקס הייחודי הבטיח שאחרי שלב 2
    # אין פגישה פעילה לליד, ולכן ההורדה הייתה ללא תנאי. עכשיו ליד יכול
    # להחזיק פגישה שעברה *ועוד אחת עתידית*, והורדה ללא תנאי הייתה
    # מוציאה אותו מ-BOOKED בזמן שפגישה עתידית עומדת ביומן.
    #
    # ה-`NOT EXISTS` מוערך בתוך ה-UPDATE (correlated ל-`leads.id`),
    # ולכן הוא נכון גם על עדכון מרובה-שורות וגם מול cron מקביל.
    # WHERE על BOOKING_PENDING/BOOKED בלבד — לא דורסים WON/LOST/ARCHIVED
    # או IN_PROGRESS שמשתמש כבר עבר אליו ידנית.
    still_active = (
        select(Booking.id)
        .where(
            Booking.lead_id == Lead.id,
            Booking.status.in_(ACTIVE_BOOKING_STATUSES),
            Booking.requested_slot_end > now_utc,
        )
        .correlate(Lead)
        .exists()
    )
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
            ~still_active,
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
                    "source": BookingCancelSource.EXPIRE_STALE_CRON.value,
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
    """מידע לדף הציבורי.

    עד היום, פגישה פעילה **חסמה** את הדף: הלקוח שפתח את הקישור בשנית
    קיבל מסך "כבר יש לך בקשת פגישה" ולא יכול היה לקבוע מועד נוסף. זו
    הייתה המגבלה שביקשו להסיר. מעכשיו הפגישות הקיימות מוחזרות כמידע
    בלבד, והדף ממשיך להציג את בורר המועדים — עד התקרה.
    """
    lead = await get_lead_by_booking_token(db, token)
    upcoming = await _active_bookings(db, lead.id)
    # קריאת שעון *אחת* לשני השדות. שתי קריאות נפרדות שנופלות משני צדי
    # חצות (שעון ישראל) היו מחזירות today מיום אחד ו-horizon מיום אחר —
    # ביום האחרון של החודש זה מרווח של חודשיים במקום אחד, וה-UI היה בונה
    # שלושה חודשי בחירה.
    now_utc = datetime.now(timezone.utc)
    return BookingPageInfo(
        lead_name=lead.full_name,
        service_category=lead.service_category,
        service_subtype=lead.service_subtype,
        default_duration_minutes=default_duration_minutes(lead.service_category),
        upcoming_bookings=[
            UpcomingBooking(
                start=b.requested_slot_start,
                end=b.requested_slot_end,
                status=b.status,
            )
            for b in upcoming
        ],
        can_book_more=len(upcoming) < MAX_ACTIVE_BOOKINGS_PER_LEAD,
        max_bookings=MAX_ACTIVE_BOOKINGS_PER_LEAD,
        today=to_israel_tz(now_utc).date(),
        booking_horizon_end=booking_horizon_end(now_utc),
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
    # +1 כי שני הקצוות נכללים: 01/10→31/10 הוא חודש של 31 ימים, לא 30.
    # בלי זה התקרה מתירה בפועל יום אחד יותר ממה ששמה מבטיח.
    requested_days = (date_to - date_from).days + 1
    if requested_days > MAX_AVAILABILITY_RANGE_DAYS:
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

    row = await gc_service.get_credentials_row(db)
    if row is None:
        # race נדיר: ה-credentials נמחקו בין הטעינה לכאן.
        return [], False
    calendar_ids = gc_service.busy_calendar_ids(row)

    try:
        busy = await asyncio.to_thread(
            _freebusy_query, creds, calendar_ids, start_utc, end_utc
        )
        return busy, True
    except CalendarTemporarilyUnavailable:
        # כבר מנוסח כראוי ע"י _parse_freebusy_response — לא לעטוף שוב.
        raise
    except Exception as e:
        logger.exception("FreeBusy query failed for connected calendar")
        raise CalendarTemporarilyUnavailable() from e


# Google מגביל שאילתת FreeBusy אחת ל-50 יומנים
# (`calendarExpansionMax`, מסמך ה-discovery של Calendar v3). בפועל
# נועה תבחר יומן או שניים, אבל עדיף לכשול עם הודעה ברורה מאשר לקבל
# תשובה חלקית מ-Google בלי לשים לב.
MAX_FREEBUSY_CALENDARS = 50


def _parse_freebusy_response(
    result: dict, requested_ids: list[str]
) -> list[tuple[datetime, datetime]]:
    """ממזג את טווחי ה-busy של *כל* היומנים שנשאלו לרשימה אחת.

    פונקציה טהורה — כל הלוגיקה שאפשר לבדוק בלי Google חי נמצאת כאן.

    שתי נקודות שקל לפספס בתשובה של FreeBusy:

    1. **המפתח במפת `calendars` הוא מזהה היומן שנשאל**, ולא מחרוזת
       קבועה. הגרסה הקודמת חיפשה את המפתח `"primary"` בלבד; עם כמה
       יומנים זה היה מחזיר רק את הראשון. לכן עוברים על כל הערכים
       במקום לחפש מפתח.

    2. **`FreeBusyCalendar.errors`** — Google מחזיר 200 גם כשחישוב
       ליומן מסוים נכשל (יומן שנמחק, הרשאה שנשללה), והשדה `busy`
       פשוט חוזר ריק. בלי הבדיקה הזו, יומן שבור נראה בדיוק כמו יומן
       פנוי, והמערכת הייתה מציעה ללקוח שעות שנועה תפוסה בהן — בדיוק
       הבאג שבגללו נבנתה התמיכה ביומן שני. לכן: כל `errors` הוא
       fail-safe, בדיוק כמו כשל רשת.
    """
    calendars = result.get("calendars") or {}

    # יומן שנשאל ולא חזר בכלל — לא מניחים שהוא פנוי.
    missing = [cid for cid in requested_ids if cid not in calendars]
    if missing:
        logger.error("FreeBusy response missing calendars: %s", missing)
        raise CalendarTemporarilyUnavailable()

    parsed: list[tuple[datetime, datetime]] = []
    for calendar_id, entry in calendars.items():
        errors = entry.get("errors")
        if errors:
            reasons = ", ".join(
                str(e.get("reason", "unknown")) for e in errors
            )
            logger.error(
                "FreeBusy returned errors for calendar %s: %s",
                calendar_id,
                reasons,
            )
            raise CalendarTemporarilyUnavailable()
        for b in entry.get("busy", []):
            # ISO 8601 עם timezone offset — fromisoformat מטפל
            parsed.append(
                (
                    datetime.fromisoformat(b["start"]).astimezone(timezone.utc),
                    datetime.fromisoformat(b["end"]).astimezone(timezone.utc),
                )
            )
    return parsed


def _freebusy_query(
    creds,
    calendar_ids: list[str],
    start_utc: datetime,
    end_utc: datetime,
) -> list[tuple[datetime, datetime]]:
    """blocking call ל-Google API — נקרא רק בתוך asyncio.to_thread."""
    from app.services.google_calendar import _calendar_service

    if len(calendar_ids) > MAX_FREEBUSY_CALENDARS:
        logger.error(
            "Too many calendars for a single FreeBusy query: %d",
            len(calendar_ids),
        )
        raise CalendarTemporarilyUnavailable()

    service = _calendar_service(creds)
    body = {
        "timeMin": start_utc.isoformat(),
        "timeMax": end_utc.isoformat(),
        "timeZone": "Asia/Jerusalem",
        "items": [{"id": cid} for cid in calendar_ids],
    }
    result = service.freebusy().query(body=body).execute()
    return _parse_freebusy_response(result, calendar_ids)


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
        Booking.status.in_(ACTIVE_BOOKING_STATUSES),
        Booking.requested_slot_end > effective_start,
        Booking.requested_slot_start < end_utc,
    )
    rows = (await db.execute(stmt)).all()
    return [(s, e) for s, e in rows]


# ===== תיאור האירוע ביומן =====

# תקרת אורך להערה בתיאור האירוע. זהה ל-max_length של השדה ב-schema —
# החיתוך כאן הוא רשת בטחון לשורות ישנות ולא המקום שבו אוכפים.
_MAX_NOTES_IN_EVENT = 500


def _sanitize_for_event(value: str) -> str:
    """מכין טקסט חופשי מהלקוח להטמעה בתיאור אירוע ב-Google Calendar.

    `description` של אירוע ב-Google Calendar מרונדר כ-HTML חלקי, ולכן
    הוא output עם **סינטקס פעיל** — טקסט מ-endpoint ציבורי ולא מאומת
    חייב escape לפני שהוא נכנס אליו (CLAUDE.md כלל 6). בלי זה, הערה
    שמכילה `<b>` או `<a href=...>` הייתה משנה את מראה האירוע ביומן של
    נועה, ותו `&` בודד היה שובר את הרינדור.

    בנוסף מוסרים תווי בקרה (מלבד שורה חדשה וטאב) — הם לא נראים אבל
    עלולים לבלבל לקוחות יומן שונים.
    """
    import html

    stripped = "".join(
        ch for ch in value if ch in "\n\t" or ord(ch) >= 32
    ).strip()
    if len(stripped) > _MAX_NOTES_IN_EVENT:
        stripped = stripped[:_MAX_NOTES_IN_EVENT] + "…"
    return html.escape(stripped)


def build_event_description(lead: Lead, booking: Booking) -> str:
    """בונה את גוף האירוע ביומן — פונקציה טהורה, ניתנת לבדיקה בלי Google.

    התוכן לפי `docs/phase-2.5-plan.md §3.6`: רק מה ששימושי לפגישה עצמה.
    שדות טכניים (booking_id, קוד קטגוריה) לא מוצגים — ה-bookingId כבר
    יושב ב-`extendedProperties.private` כעוגן לסנכרון ההפוך.

    הטלפון נלקח מ**הפגישה** ולא מכרטיס הליד: זה המספר שהלקוח הזין
    בעצמו בדף, והוא הסיבה שהשדה נוסף מלכתחילה — שנועה תוכל ליצור קשר
    בביטול או עדכון. fallback ל-`lead.phone` עבור פגישות שנוצרו לפני
    שהשדה היה קיים.
    """
    from app.utils.labels import SERVICE_SUBTYPE_HE

    lines: list[str] = []
    if lead.service_subtype:
        subtype_he = SERVICE_SUBTYPE_HE.get(
            lead.service_subtype, lead.service_subtype
        )
        lines.append(f"סוג שירות: {subtype_he}")
    if lead.organization_name:
        lines.append(f"ארגון: {_sanitize_for_event(lead.organization_name)}")
    phone = booking.contact_phone or lead.phone
    if phone:
        lines.append(f"טלפון: {_sanitize_for_event(phone)}")
    if lead.email:
        lines.append(f"מייל: {_sanitize_for_event(lead.email)}")
    if booking.notes:
        lines.append("")
        lines.append(f"הערה מהלקוח: {_sanitize_for_event(booking.notes)}")
    return "\n".join(lines)


# ===== Create booking =====


async def create_booking_request(
    db: AsyncSession,
    token: UUID,
    slot_start: datetime,
    slot_end: datetime,
    contact_phone: str,
    notes: str | None = None,
) -> CreateBookingResponse:
    """
    קובע פגישה מאושרת מהדף הציבורי, ויוצר את האירוע ביומן באותה טרנזקציה.

    **השינוי מול הגרסה הקודמת:** אין יותר שלב אישור של נועה. הליד בוחר
    מועד — והפגישה נקבעת (`status=approved`), הליד עובר ל-BOOKED,
    והאירוע נוצר ביומן. `approve_booking`/`reject_booking` נמחקו.

    סדר הפעולות בטרנזקציה **נעול בכוונה**:
      INSERT booking → UPDATE lead → activity → יצירת האירוע ב-Google
      → שמירת event_id → commit

    1. ה-INSERT קודם לקריאה החיצונית: ה-EXCLUDE constraint הוא ה-
       UNIQUE שתופס קביעה כפולה על אותו סלוט, ואם יוצרים אירוע לפני
       שיש שורה — כל race משאיר אירוע יתום ביומן של נועה
       (reserve-then-fill).
    2. ה-UPDATE של הליד קודם ל-Google: אם הוא מחזיר rowcount=0 (הליד
       נסגר בינתיים) אנחנו עושים rollback — ואין מה לנקות ביומן.

    fail-safe: יומן מחובר ויצירת האירוע נכשלה → rollback מלא ו-503.
    אסור שהלקוח יראה "נקבע" בלי שהפגישה ביומן. יומן שלא מחובר בכלל —
    ממשיכים בלי `event_id`, כי זו בחירה מודעת של המשתמשת.
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

    from sqlalchemy import func, select as sa_select, update

    from app.services import google_calendar as gc_service
    from app.services.lead_actions import (
        REPLY_BOOST_HOURS,
        close_touchpoint_tasks,
    )

    # נעילת שורת הליד. זו לא אופטימיזציה — זה מה שהופך את בדיקת התקרה
    # למשמעותית. אחרי שמיגרציה 0032 הסירה את האינדקס הייחודי, אין יותר
    # רשת ב-DB שמגבילה כמה פגישות לליד, וספירה-ואז-INSERT היא
    # check-then-act קלאסי (CLAUDE.md כלל 2): שתי בקשות מקבילות היו
    # קוראות "יש 2", ושתיהן היו מוסיפות.
    #
    # הנעילה היא per-lead ולכן לא חוסמת לידים אחרים — היא רק מסדרת
    # בטור בקשות של *אותו* ליד, וזה בדיוק מה שצריך.
    await db.execute(
        sa_select(Lead.id).where(Lead.id == lead.id).with_for_update()
    )

    # cleanup: פגישות שהמועד שלהן עבר מועברות ל-CANCELED, כדי שלא
    # ייספרו לתקרה וכדי שסטטוס הליד לא יישאר תקוע.
    await _expire_stale_bookings(db, lead.id)

    existing = await _active_bookings(db, lead.id)
    if len(existing) >= MAX_ACTIVE_BOOKINGS_PER_LEAD:
        raise ConflictError(
            f"כבר קבועות לך {len(existing)} פגישות. "
            "צרי קשר עם נועה אם צריך לקבוע עוד אחת."
        )

    # בדיקה חוזרת מול busy ranges — מגן מ-race בין הצגת הסלוט לקביעה.
    # ה-DB EXCLUDE constraint יתפוס כל race שיחמוק מכאן.
    google_busy, _ = await _fetch_google_busy(db, slot_start, slot_end)
    db_busy = await _fetch_db_busy(db, slot_start, slot_end)
    if not _slot_free(slot_start, slot_end, google_busy + db_busy, now_utc):
        raise ConflictError(
            "הסלוט כבר תפוס. בחרי מועד אחר מהרשימה המעודכנת."
        )

    # ===== 1. INSERT — לפני כל קריאה חיצונית =====
    # `ck_bookings_no_overlap` (EXCLUDE USING gist, migration 0006) הוא
    # ה-constraint שתופס שתי קביעות מקבילות על אותו מועד.
    booking = Booking(
        lead_id=lead.id,
        requested_slot_start=slot_start,
        requested_slot_end=slot_end,
        status=BookingStatus.APPROVED.value,
        approved_at=now_utc,
        contact_phone=contact_phone,
        notes=notes,
    )
    db.add(booking)
    try:
        await db.flush()
    except IntegrityError as e:
        await db.rollback()
        raise ConflictError(
            "הסלוט כבר תפוס. בחרי מועד אחר מהרשימה המעודכנת."
        ) from e

    # ===== 2. סטטוס הליד → BOOKED =====
    # `waiting_on=CLIENT` — הכדור אצל הלקוח, הוא צריך להגיע לפגישה.
    # `last_inbound_at` + `reply_boost_until`: הלקוח פנה אלינו, ולכן
    # הליד קופץ לראש הדשבורד ל-24 שעות (Spec §12.5).
    # אטומי דרך WHERE status IN (open) — אם הליד נסגר בינתיים
    # ה-UPDATE לא יבוצע ואנחנו עושים rollback לפני שנוצר אירוע ביומן.
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
            status=LeadStatus.BOOKED.value,
            waiting_on=WaitingOn.CLIENT.value,
            last_inbound_at=now_utc,
            reply_boost_until=now_utc + timedelta(hours=REPLY_BOOST_HOURS),
            last_activity_type=ActivityType.MEETING_APPROVED.value,
            updated_at=func.now(),
        )
    )
    if update_result.rowcount != 1:
        await db.rollback()
        raise ConflictError(
            "מצב הפנייה השתנה בזמן השליחה. רעני את הדף ונסי שוב."
        )

    # ===== 3. activity אחת =====
    # `MEETING_APPROVED` ולא `MEETING_REQUESTED`, ורשומה אחת ולא שתיים:
    # - זה ה-signal הקנוני ל"הליד עבר ל-BOOKED", ושני צרכנים נשענים
    #   עליו — `jobs/post_meeting_tasks.py` (דרך `metadata.booking_id`)
    #   ו-`services/summary_inputs.py`.
    # - `Activity.created_at` הוא `now()` של הטרנזקציה, כלומר שתי
    #   רשומות באותה טרנזקציה מקבלות חותמת זמן *זהה*, וכל שאילתת
    #   "האחרון" הופכת ללא-דטרמיניסטית.
    # - `last_activity_type` על הליד חייב להיות זהה ל-type שנרשם כאן,
    #   אחרת סינונים downstream נשברים.
    await log_activity(
        db,
        lead_id=lead.id,
        activity_type=ActivityType.MEETING_APPROVED,
        performed_by=None,  # public — אין user מחובר
        content=notes,
        metadata={
            "booking_id": str(booking.id),
            "slot_start": slot_start.isoformat(),
            "slot_end": slot_end.isoformat(),
            "contact_phone": contact_phone,
            # מבדיל בין פגישה שנקבעה אוטומטית לבין אישור ידני ישן.
            "auto_confirmed": True,
        },
    )

    # קביעת פגישה = touchpoint inbound (הלקוח חזר אלינו). סוגרת tasks
    # תקועים — בעיקר warm_followup ("הלקוח לא חזר") שכבר לא רלוונטי.
    await close_touchpoint_tasks(db, lead.id, now_utc)

    # extract primitives לפני כל דבר שעלול לגרור rollback — אחרי
    # rollback כל attribute של אובייקט ORM פג-תוקף, וגישה אליו זורקת
    # MissingGreenlet ב-async session (כלל 5 ב-CLAUDE.md).
    booking_id = booking.id
    booking_start = booking.requested_slot_start
    booking_end = booking.requested_slot_end
    summary = f"פגישה — {lead.full_name}"
    description = build_event_description(lead, booking)

    # ===== 4. יצירת האירוע ביומן — עדיין לפני ה-commit =====
    event_id: str | None = None
    try:
        event_id = await gc_service.create_calendar_event(
            db,
            booking_id=booking_id,
            summary=summary,
            description=description,
            start=booking_start,
            end=booking_end,
        )
    except (
        gc_service.GoogleNotConfiguredError,
        gc_service.GoogleNotConnectedError,
    ):
        # יומן לא מחובר — בחירה מודעת. ממשיכים בלי event_id.
        pass
    except Exception as e:
        logger.exception("Failed to create Google event for new booking")
        await db.rollback()
        raise CalendarTemporarilyUnavailable() from e

    # ===== 5. שמירת ה-event_id =====
    if event_id is not None:
        await db.execute(
            update(Booking)
            .where(Booking.id == booking_id)
            .values(google_calendar_event_id=event_id)
        )

    # ===== 6. commit עם compensation =====
    # אם ה-commit נכשל ויש אירוע ביומן — מוחקים אותו, אחרת נשארת ביומן
    # של נועה פגישה שאין לה רישום במערכת. ה-compensation רץ ב-session
    # **חדש**: ה-session הנוכחי עשה rollback, ו-`delete_calendar_event`
    # עושה קריאות DB משלו (טעינת credentials, אולי רענון token).
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        if event_id is not None:
            await _delete_orphan_event(event_id)
        raise

    # אין Telegram על קביעת פגישה — Spec §16.3: "הדבר היחיד שמקבל פוש
    # מיידי הוא ליד חדש שנכנס" (F-06). הפגישה מופיעה ביומן של נועה,
    # והליד צף לראש הדשבורד ל-24 שעות דרך reply_boost_until.
    return CreateBookingResponse(
        booking_id=booking_id,
        status=BookingStatus.APPROVED.value,
        slot_start=booking_start,
        slot_end=booking_end,
    )


async def _delete_orphan_event(event_id: str) -> None:
    """מוחק אירוע שנוצר ביומן אבל ה-commit שלו נכשל.

    רץ ב-session נפרד בכוונה: הקורא כבר עשה rollback על ה-session שלו,
    ו-`delete_calendar_event` פונה ל-DB בעצמו (credentials, ואולי כתיבת
    token מרוענן). שימוש חוזר באותו session היה פותח טרנזקציה חדשה על
    session שזה עתה נזרק.

    כישלון כאן מתועד ב-ERROR ולא נבלע בשקט: התוצאה היא אירוע ביומן של
    נועה בלי רישום במערכת, וה-webhook לא יוכל לזהות אותו (ה-booking
    שאליו הוא מצביע לא קיים). זה מצב שדורש ניקוי ידני, ולכן הלוג חייב
    לשאת את ה-event_id.
    """
    from app.db.session import AsyncSessionLocal
    from app.services import google_calendar as gc_service

    try:
        async with AsyncSessionLocal() as cleanup_db:
            await gc_service.delete_calendar_event(cleanup_db, event_id)
    except Exception:
        logger.error(
            "ORPHAN CALENDAR EVENT: failed to delete event %s after a failed "
            "commit. It exists in the calendar with no booking row — needs "
            "manual removal.",
            event_id,
            exc_info=True,
        )



# ===== קריאה + ביטול ע"י נועה =====


async def get_bookings_for_lead(
    db: AsyncSession, lead_id: UUID
) -> list[Booking]:
    """הפגישות שכרטיס הליד צריך להציג, בסדר עולה.

    שתי קבוצות:
    1. כל הפגישות הפעילות שעדיין בעתיד.
    2. + פגישה מאושרת ש**הסתיימה** זה עתה, כל עוד הליד עדיין BOOKED —
       נדרש כדי שכפתור "סמני שהפגישה התקיימה" יישאר זמין אחרי שהפגישה
       נגמרה. ברגע שנועה מסמנת, הסטטוס משתנה והפגישה מפסיקה להופיע.
       מסונן ל-30 יום אחורה כדי לא להציג פגישות zombie ישנות.

    הגרסה הקודמת (`get_active_booking_for_lead`) החזירה פגישה **אחת**,
    והמסלול השני רץ רק כשלא הייתה אף פגישה עתידית. התוצאה: ליד שיש לו
    פגישה שהסתיימה *ועוד אחת עתידית* לא היה מקבל את הכפתור בכלל.
    """
    now_utc = datetime.now(timezone.utc)
    cutoff = now_utc - timedelta(days=30)

    upcoming = await _active_bookings(db, lead_id)

    just_finished = (
        await db.execute(
            select(Booking)
            .join(Lead, Lead.id == Booking.lead_id)
            .where(
                Booking.lead_id == lead_id,
                Booking.status == BookingStatus.APPROVED.value,
                Booking.requested_slot_end <= now_utc,
                Booking.requested_slot_end >= cutoff,
                Lead.status == LeadStatus.BOOKED.value,
            )
            .order_by(Booking.requested_slot_start.asc())
        )
    ).scalars().all()

    combined = [*just_finished, *upcoming]
    combined.sort(key=lambda b: b.requested_slot_start)
    return combined


async def cancel_booking(
    db: AsyncSession,
    booking_id: UUID,
    performed_by_id: UUID,
) -> Booking:
    """מבטל פגישה: סטטוס → canceled, מחיקת האירוע ביומן, שחרור הליד.

    מחליף את `approve_booking`/`reject_booking` שנמחקו יחד עם שלב
    האישור. נועה עדיין צריכה דרך לבטל פגישה מתוך המערכת — אחרת הדרך
    היחידה הייתה למחוק את האירוע ביומן Google ולסמוך על הסנכרון ההפוך.

    אטומי: ה-`WHERE status IN (active)` מבטיח ששני ביטולים מקבילים
    (למשל לחיצה בממשק + ביטול ביומן שמגיע כ-webhook) לא ירשמו פעמיים
    — השני מקבל rowcount=0.

    כלל 9 / Pattern 9: ה-activity נרשם **גם** כש-rowcount=0, עם
    `applied=false`. ה-activity מתעד את ה-*כוונה*, וצרכנים downstream
    (post_meeting cron) מסיקים ממנו מצב.
    """
    from sqlalchemy import update

    from app.services import google_calendar as gc_service

    now_utc = datetime.now(timezone.utc)

    row = (
        await db.execute(
            select(
                Booking.lead_id,
                Booking.google_calendar_event_id,
                Booking.status,
            ).where(Booking.id == booking_id)
        )
    ).first()
    if row is None:
        raise NotFoundError("הפגישה לא נמצאה.")

    lead_id = row.lead_id
    event_id = row.google_calendar_event_id

    cancel_result = await db.execute(
        update(Booking)
        .where(
            Booking.id == booking_id,
            Booking.status.in_(ACTIVE_BOOKING_STATUSES),
        )
        .values(status=BookingStatus.CANCELED.value)
    )
    applied = cancel_result.rowcount == 1

    # `source="manual_cancel"` הוא לא קישוט: `jobs/post_meeting_tasks.py`
    # מחשיב booking מבוטל שאושר בעבר כ"הפגישה התקיימה" (זה המסלול של
    # expire_stale), ומדכא רק ביטולים שמקורם בסנכרון מ-Google. בלי
    # המקור הזה, ביטול של פגישה עתידית היה מייצר משימת "עדכון אחרי
    # פגישה" לפגישה שמעולם לא קרתה.
    await log_activity(
        db,
        lead_id=lead_id,
        activity_type=ActivityType.MEETING_CANCELED,
        performed_by=performed_by_id,
        content=(
            "הפגישה בוטלה"
            if applied
            else "ניסיון ביטול — הפגישה כבר הייתה בסטטוס אחר"
        ),
        metadata={
            "booking_id": str(booking_id),
            "source": BookingCancelSource.MANUAL.value,
            "applied": applied,
            "canceled_at": now_utc.isoformat(),
        },
    )

    if applied:
        await release_lead_if_no_active_booking(db, lead_id)

    await db.commit()

    # מחיקת האירוע אחרי ה-commit, ורק אם באמת ביטלנו. הסדר ההפוך
    # מהיצירה, ובכוונה: כאן המצב הבטוח הוא "בוטל במערכת" — אירוע
    # שנשאר ביומן הוא מטרד שנועה רואה ויכולה למחוק, בעוד פגישה
    # שנשארת פעילה במערכת בלי אירוע היא נתון שגוי שאיש לא רואה.
    # `delete_calendar_event` אידמפוטנטי ל-404/410.
    if applied and event_id:
        try:
            await gc_service.delete_calendar_event(db, event_id)
        except (
            gc_service.GoogleNotConfiguredError,
            gc_service.GoogleNotConnectedError,
            gc_service.GoogleAuthInvalidError,
        ):
            logger.warning(
                "Booking %s canceled but calendar not available — event %s "
                "left in the calendar",
                booking_id,
                event_id,
            )
        except Exception:
            logger.exception(
                "Booking %s canceled but failed to delete calendar event %s",
                booking_id,
                event_id,
            )

    if not applied:
        raise ConflictError(
            "הפגישה כבר בוטלה או שהסטטוס שלה השתנה. רעני את הדף."
        )

    return (
        await db.execute(
            select(Booking)
            .where(Booking.id == booking_id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
