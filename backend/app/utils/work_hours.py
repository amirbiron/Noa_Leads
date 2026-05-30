"""
זיהוי שעות עבודה לפי לוח השנה הישראלי.

חוקים (לפי האפיון):
- ימים א'-ה': WORK_DAY_START_HOUR עד WORK_DAY_END_HOUR
- יום שישי: WORK_DAY_START_HOUR עד FRIDAY_CLOSE_HOUR (ברירת מחדל: 9:00-16:00)
- שבת: סגור
- חג ישראלי: סגור כל היום
- ערב חג: סגור החל מ-FRIDAY_CLOSE_HOUR (אותה התנהגות כמו ערב שבת)

כל הזמנים מחושבים ב-Asia/Jerusalem (TZ של נועה),
גם אם ה-DB מאחסן ב-UTC.
"""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import holidays

from app.config import get_settings

ISRAEL_TZ = ZoneInfo("Asia/Jerusalem")

# cache להפחתת overhead — holidays.IL לאותה שנה זול אבל לא חינם
_HOLIDAYS_CACHE: dict[int, holidays.HolidayBase] = {}


def _get_il_holidays(year: int) -> holidays.HolidayBase:
    if year not in _HOLIDAYS_CACHE:
        # 'public' = חגים רשמיים (פסח, יו"כ, ר"ה, סוכות, שבועות, עצמאות),
        # 'optional' = ימים שמקובל לא לעבוד בהם (ת"ב, פורים) — חשוב לנועה כי
        # היא לא תעבוד בפורים גם אם זה לא יום חופש רשמי.
        _HOLIDAYS_CACHE[year] = holidays.country_holidays(
            "IL",
            years=[year],
            categories=("public", "optional"),
        )
    return _HOLIDAYS_CACHE[year]


def to_israel_tz(dt: datetime) -> datetime:
    """המרת datetime ל-Asia/Jerusalem. עובד גם על naive (מניח UTC)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    return dt.astimezone(ISRAEL_TZ)


def is_holiday(d: date) -> bool:
    """האם התאריך הוא חג ישראלי (מלא, כל היום סגור)."""
    return d in _get_il_holidays(d.year)


def is_holiday_eve(d: date) -> bool:
    """האם זה ערב חג — כלומר, מחר חג."""
    tomorrow = d + timedelta(days=1)
    return is_holiday(tomorrow)


def is_friday(d: date) -> bool:
    # weekday: שני=0, שלישי=1, ..., שישי=4, שבת=5, ראשון=6
    return d.weekday() == 4


def is_saturday(d: date) -> bool:
    return d.weekday() == 5


def is_working_time(dt: datetime) -> bool:
    """
    True רק אם הרגע הזה הוא בתוך שעות עבודה.
    הקריאה הראשית מהאפליקציה — קובעת אם לשלוח auto-reply או לא.
    """
    settings = get_settings()
    local = to_israel_tz(dt)
    d = local.date()

    # שבת — תמיד סגור
    if is_saturday(d):
        return False

    # חג מלא — סגור
    if is_holiday(d):
        return False

    hour = local.hour

    # יום שישי — עובדים עד FRIDAY_CLOSE_HOUR
    if is_friday(d):
        return settings.work_day_start_hour <= hour < settings.friday_close_hour

    # ערב חג ביום רגיל — סגור החל מ-FRIDAY_CLOSE_HOUR
    if is_holiday_eve(d):
        return settings.work_day_start_hour <= hour < settings.friday_close_hour

    # ימי חול רגילים
    return settings.work_day_start_hour <= hour < settings.work_day_end_hour


def next_working_day_start(dt: datetime) -> datetime:
    """
    מחזיר את ה-datetime הבא שבו נפתחת עבודה — לקביעת due_at של משימות
    שנפתחות מחוץ לשעות עבודה.

    מתחיל ב-WORK_DAY_START_HOUR ביום העבודה הבא (Asia/Jerusalem),
    ומחזיר datetime tz-aware.
    """
    settings = get_settings()
    local = to_israel_tz(dt)
    start_time = time(hour=settings.work_day_start_hour, tzinfo=ISRAEL_TZ)

    # אם עכשיו ב-Working hours, היום עצמו לא רלוונטי (אנחנו רוצים את ה"הבא")
    # אבל אם אנחנו מחוץ לשעות באותו יום עבודה, אולי עוד אפשר היום
    today_start = datetime.combine(local.date(), start_time)
    if local < today_start and _is_working_day(local.date()):
        return today_start

    # אחרת — חיפוש קדימה
    candidate = local.date() + timedelta(days=1)
    for _ in range(14):  # safety bound — שבועיים אמורים להספיק תמיד
        if _is_working_day(candidate):
            return datetime.combine(candidate, start_time)
        candidate += timedelta(days=1)

    # לא אמור לקרות — אם הגענו לכאן יש בעיה בנתוני החגים
    return datetime.combine(candidate, start_time)


def _is_working_day(d: date) -> bool:
    """האם מתקיימת בכלל עבודה ביום הזה (לפחות מ-WORK_DAY_START_HOUR)."""
    if is_saturday(d):
        return False
    if is_holiday(d):
        return False
    # יום שישי ועברי חג עדיין נחשבים יום עבודה (יש בהם start_hour)
    return True


def after_hours_reply_message(dt: datetime) -> str:
    """
    הודעת auto-reply לפניות שמגיעות מחוץ לשעות.

    מחושב על בסיס יום העבודה האמיתי הבא:
    - אם יום העבודה הבא הוא יום ראשון — נוסח ספציפי "ביום ראשון" (לפי האפיון)
    - אחרת — נוסח כללי "ביום העבודה הקרוב" (חגים, או ערב יום חול)

    הבעיה שהפונקציה הזו מונעת: על קלט של "שלישי 20:00", הנוסח הקודם
    החזיר "ביום ראשון" אף שהיום הבא הוא רביעי בבוקר.
    """
    next_wd = next_working_day_start(dt).astimezone(ISRAEL_TZ)
    # weekday: שני=0, ..., שישי=4, שבת=5, ראשון=6
    if next_wd.weekday() == 6:
        return (
            "קיבלנו את הפנייה.\n"
            "נחזור אליך ביום ראשון בין 9:00 ל-11:00."
        )
    return (
        "קיבלנו את הפנייה.\n"
        "נחזור אליך ביום העבודה הקרוב בין 9:00 ל-11:00."
    )


def should_skip_daily_summary(now_utc: datetime) -> bool:
    """
    האם לדלג על הסיכום היומי (C.1 §6.7) — נועה לא עובדת אז, וסיכום של "0
    פעולות" יראה כאילו המערכת מושבתת.

    מדלגים כש (מחושב בזמן ישראל):
    - שבת (כולל מוצאי שבת בערב — עדיין תאריך שבת)
    - חג ישראלי (כולל מוצאי חג בערב — עדיין תאריך החג)
    - יום שישי אחרי FRIDAY_CLOSE_HOUR (16:00)
    - ערב חג אחרי FRIDAY_CLOSE_HOUR (אותה התנהגות כמו ערב שבת)

    הערה: לא ניתן לעשות reuse של is_working_time — היא מחזירה False אחרי
    WORK_DAY_END_HOUR (18:00) בכל יום, וה-cron של הסיכום רץ ב-19:00.
    """
    il = to_israel_tz(now_utc)
    d = il.date()
    if is_saturday(d) or is_holiday(d):
        return True
    cutoff = get_settings().friday_close_hour
    if (is_friday(d) or is_holiday_eve(d)) and il.hour >= cutoff:
        return True
    return False


def should_skip_weekly_summary(now_utc: datetime) -> bool:
    """
    האם לדלג על הסיכום השבועי (C.2 §6.7). הסיכום רץ ביום ראשון בבוקר ומסכם
    את כל השבוע שעבר (כולל שישי-שבת), אבל מדלגים אם יום ראשון עצמו נופל בחג
    יהודי — נועה לא עובדת אז (עקבי עם הסיכום היומי).

    cursor bugbot: הוסר `is_saturday(d)` — ה-cron רץ ביום ראשון UTC ולכן
    התאריך הישראלי בו אינו שבת אף פעם. ב-`is_saturday` הקיים, ריצה ידנית
    בשבת (testing) הייתה גורמת ל-skip שגוי. §6.7 דורש דילוג רק על חג.
    """
    d = to_israel_tz(now_utc).date()
    return is_holiday(d)
