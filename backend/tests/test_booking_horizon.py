"""
בדיקות לאופק ההזמנה בדף קביעת התור (§11.1).

הכלל: הלקוח יכול לקבוע עד סוף החודש *הבא* בשעון ישראל — החודש הנוכחי
פתוח כולו, ועוד חודש אחד קדימה. ב-30 בספטמבר עדיין אפשר אוקטובר, אבל
לא נובמבר.

booking_horizon_end הוא pure function של הזמן — נבדק ישירות בלי DB
(לכן אין fixture `db` ברוב הבדיקות כאן ואין skip כשאין Postgres).
"""

from datetime import date, datetime, time, timedelta, timezone

import pytest

from app.services.booking import (
    MAX_AVAILABILITY_RANGE_DAYS,
    booking_horizon_end,
)


def _utc(year: int, month: int, day: int, hour: int = 12) -> datetime:
    return datetime(year, month, day, hour, tzinfo=timezone.utc)


# ===================== האופק עצמו =====================


@pytest.mark.parametrize(
    "now,expected",
    [
        # תחילת החודש — עדיין סוף החודש הבא, לא "30 יום קדימה".
        (_utc(2026, 9, 1), date(2026, 10, 31)),
        # התרחיש מהבקשה: סוף ספטמבר עדיין נותן את כל אוקטובר.
        (_utc(2026, 9, 30), date(2026, 10, 31)),
        # החודש הבא קצר מהנוכחי.
        (_utc(2026, 10, 15), date(2026, 11, 30)),
        # מעבר שנה.
        (_utc(2026, 12, 5), date(2027, 1, 31)),
        (_utc(2026, 11, 20), date(2026, 12, 31)),
        # פברואר בשנה רגילה ובשנה מעוברת — בלי לקודד אורכי חודשים.
        (_utc(2026, 1, 10), date(2026, 2, 28)),
        (_utc(2028, 1, 10), date(2028, 2, 29)),
    ],
)
def test_horizon_is_end_of_next_month(now: datetime, expected: date):
    assert booking_horizon_end(now) == expected


def test_horizon_uses_israel_date_not_utc():
    """23:30 UTC ב-30 בספטמבר זה כבר 1 באוקטובר בישראל (UTC+3).

    לכן האופק חייב להתגלגל לסוף נובמבר. אם החישוב היה על תאריך UTC,
    הלקוח היה מקבל חודש פחות בכל ערב.
    """
    assert booking_horizon_end(_utc(2026, 9, 30, hour=23)) == date(2026, 11, 30)
    # אותו יום, מוקדם יותר — עדיין 30 בספטמבר בישראל.
    assert booking_horizon_end(_utc(2026, 9, 30, hour=6)) == date(2026, 10, 31)


def test_horizon_never_shrinks_within_a_month():
    """לאורך חודש שלם האופק קבוע — הלקוח לא רואה תאריכים נעלמים מיום ליום."""
    horizons = {
        booking_horizon_end(_utc(2026, 9, day)) for day in range(1, 31)
    }
    assert horizons == {date(2026, 10, 31)}


# ===================== תקרת הטווח פר-קריאה =====================


def test_range_cap_covers_a_full_calendar_month():
    """31 יום — מספיק לשלוף חודש קלנדרי ארוך בקריאה אחת.

    זו מגבלה *נפרדת* מהאופק: היא מגנה על FreeBusy, לא מגדירה עד מתי
    אפשר לקבוע. ה-frontend שולף חודש בכל קריאה, אז היא חייבת לכסות
    את החודש הארוך ביותר — כשהוא נספר inclusive, כפי שהשאילתה מחזירה
    אותו (01/10→31/10 = 31 ימים, לא 30).
    """
    longest_month_days = (date(2026, 10, 31) - date(2026, 10, 1)).days + 1
    assert longest_month_days == 31
    assert MAX_AVAILABILITY_RANGE_DAYS >= longest_month_days


# ===================== אכיפה בשני ה-endpoints =====================
# integration מול Postgres — מדלגות אם אין DB (fixture `db`).


async def _mk_lead_with_token(db):
    """ליד מינימלי עם booking_token (server_default מייצר אותו ב-flush)."""
    from app.constants import LeadStatus
    from app.models.lead import Lead

    lead = Lead(
        full_name="בדיקת אופק",
        source_channel="manual",
        status=LeadStatus.NEW.value,
    )
    db.add(lead)
    await db.flush()
    await db.refresh(lead)
    return lead


async def test_availability_rejects_dates_beyond_horizon(db):
    """בקשת זמינות לחודש שאחרי האופק נדחית — לא מוחזרת רשימה ריקה.

    רשימה ריקה הייתה נראית ללקוח כמו "אין מועדים פנויים", וזו הודעה
    שגויה: המועדים לא תפוסים, הם פשוט מחוץ לטווח שנועה פתחה.
    """
    from app.core.exceptions import ValidationError
    from app.services import booking as booking_service

    lead = await _mk_lead_with_token(db)
    horizon = booking_service.booking_horizon_end()
    beyond = horizon + timedelta(days=1)

    with pytest.raises(ValidationError):
        await booking_service.get_availability(
            db, lead.booking_token, beyond, beyond
        )


async def test_availability_allows_the_horizon_day_itself(db):
    """היום האחרון עצמו מותר — הגבול inclusive, לא off-by-one."""
    from app.services import booking as booking_service

    lead = await _mk_lead_with_token(db)
    horizon = booking_service.booking_horizon_end()

    days, _ = await booking_service.get_availability(
        db, lead.booking_token, horizon, horizon
    )
    assert [d.date for d in days] == [horizon]


async def test_create_booking_rejects_slot_beyond_horizon(db):
    """האכיפה האמיתית: POST ישיר עם מועד מעבר לאופק נדחה.

    ה-UI לא מציג את התאריכים האלה, אבל ה-endpoint ציבורי וה-token ב-URL
    הוא ה-credential היחיד — הסתרה בממשק אינה אכיפה.
    """
    from app.core.exceptions import ValidationError
    from app.services import booking as booking_service
    from app.utils.work_hours import ISRAEL_TZ

    lead = await _mk_lead_with_token(db)
    horizon = booking_service.booking_horizon_end()
    # יום אחרי האופק, בשעה שהיא סלוט תקין לחלוטין בכל יום עבודה אחר.
    beyond = horizon + timedelta(days=1)
    start = datetime.combine(beyond, time(10, 0, tzinfo=ISRAEL_TZ))
    duration = booking_service.default_duration_minutes(lead.service_category)
    end = start + timedelta(minutes=duration)

    with pytest.raises(ValidationError):
        await booking_service.create_booking_request(
            db,
            token=lead.booking_token,
            slot_start=start.astimezone(timezone.utc),
            slot_end=end.astimezone(timezone.utc),
        )


async def test_page_info_exposes_the_bounds_for_the_ui(db):
    """הדף הציבורי מקבל את הגבולות מהשרת ולא מחשב אותם משעון המכשיר.

    זה החוזה שה-frontend בונה עליו את הגריד: `today` הוא היום בשעון
    ישראל, `booking_horizon_end` הוא היום האחרון שאפשר לקבוע בו.
    """
    from app.services import booking as booking_service
    from app.utils.work_hours import to_israel_tz

    lead = await _mk_lead_with_token(db)
    info = await booking_service.get_booking_page_info(db, lead.booking_token)

    assert info.today == to_israel_tz(datetime.now(timezone.utc)).date()
    assert info.booking_horizon_end == booking_service.booking_horizon_end()
    # שני החודשים שה-UI יציג: הנוכחי והבא בלבד.
    assert info.booking_horizon_end > info.today
    assert (info.booking_horizon_end.year - info.today.year) * 12 + (
        info.booking_horizon_end.month - info.today.month
    ) == 1


async def test_availability_range_cap_counts_both_endpoints(db):
    """טווח של MAX+1 *תאריכים* נדחה, גם כשההפרש בימים הוא בדיוק MAX.

    הבדיקה נועלת את הספירה ה-inclusive: בלעדיה הגבול היה מתיר יום אחד
    יותר ממה ששם הקבוע מבטיח, וההגנה על FreeBusy הייתה חלשה מהמתועד.
    """
    from app.core.exceptions import ValidationError
    from app.services import booking as booking_service

    lead = await _mk_lead_with_token(db)
    # מעגנים את הטווח בסוף האופק כדי שהדחייה תגיע מתקרת הטווח ולא ממנו.
    horizon = booking_service.booking_horizon_end()
    too_wide_from = horizon - timedelta(
        days=booking_service.MAX_AVAILABILITY_RANGE_DAYS
    )

    with pytest.raises(ValidationError):
        await booking_service.get_availability(
            db, lead.booking_token, too_wide_from, horizon
        )

    # יום אחד פחות — בדיוק MAX תאריכים — עובר.
    days, _ = await booking_service.get_availability(
        db, lead.booking_token, too_wide_from + timedelta(days=1), horizon
    )
    assert len(days) == booking_service.MAX_AVAILABILITY_RANGE_DAYS
