"""
הקישור הפתוח לקביעת פגישה — קביעה בלי ליד.

מה שהפיצ'ר מבטיח, ומה שהטסטים כאן בודקים:

1. הפגישה נכנסת ליומן Google עם השם, הטלפון והמועד — **ביומן אחד**,
   יומן היעד, גם כשמוגדרים יומנים נוספים לחישוב הזמינות.
2. **זהו.** אין ליד, אין activity ואין משימה.
3. ההגנה מפני שתי פגישות באותו מועד חלה גם על שורה בלי ליד — מול קישור
   פתוח אחר וגם מול פגישה של ליד, ובמקביל ולא רק ברצף.
4. שורה בלי ליד לא שוברת את מי שצורך את טבלת `bookings`: הסנכרון
   מ-Google, ה-cron הלילי והביטול הידני. הטסטים של שלושתם נכתבו אחרי
   שנמצאו שם באגים אמיתיים, והורצו על הקוד שלפני התיקון ונפלו.

**מצב ההרצה — מחובר, כמו בפרודקשן** (testing.md §1). מזויפות רק שלוש
הפונקציות שעושות הצפנה או רשת: `get_credentials_or_404`,
`_freebusy_query` ו-`_create_event_blocking`. כל השאר — שורת ה-
credentials, בחירת יומן היעד ורשימת היומנים הנוספים — הוא הקוד האמיתי.
הטסטים של "היומן לא מחובר" רצים בלי הזיוף, במצב שבו סביבת הטסטים
באמת נמצאת (אין משתני Google).
"""

import asyncio
from datetime import datetime, time, timedelta, timezone
from uuid import uuid4

import pytest
import pytest_asyncio

from app.utils.work_hours import ISRAEL_TZ

pytestmark = pytest.mark.asyncio

TARGET_CALENDAR = "target-cal@group.calendar.google.com"
EXTRA_CALENDAR = "extra-cal@group.calendar.google.com"


class _FakeGoogle:
    """מה ש-Google "קיבל". כל קריאה נרשמת, כדי שהטסט יבדוק את התוכן."""

    def __init__(self) -> None:
        self.created: list[dict] = []
        self.busy: list[tuple[datetime, datetime]] = []

    def freebusy(self, _creds, _calendar_ids, _start, _end):
        return list(self.busy)

    def create_event(
        self, _creds, calendar_id, booking_id, summary, description, start, end
    ):
        event_id = f"evt-{len(self.created) + 1}"
        self.created.append(
            {
                "event_id": event_id,
                "calendar_id": calendar_id,
                "booking_id": booking_id,
                "summary": summary,
                "description": description,
                "start": start,
                "end": end,
            }
        )
        return event_id


@pytest_asyncio.fixture
async def google(db, monkeypatch):
    from sqlalchemy import delete

    from app.models.google_credentials import GoogleCalendarCredentials
    from app.services import booking as booking_service
    from app.services import google_calendar as gc

    # השורה היא singleton (id=1). אם ב-DB המקומי כבר יש אחת, היא נמחקת
    # **בתוך** הטרנזקציה של הטסט, ולכן חוזרת ב-rollback.
    await db.execute(delete(GoogleCalendarCredentials))
    db.add(
        GoogleCalendarCredentials(
            id=1,
            google_account_email="noa@example.com",
            calendar_id=TARGET_CALENDAR,
            busy_calendar_ids=[EXTRA_CALENDAR],
            refresh_token_encrypted="לא-בשימוש-בטסט",
        )
    )
    await db.flush()

    fake = _FakeGoogle()

    async def _creds(_db):
        return object()

    monkeypatch.setattr(gc, "get_credentials_or_404", _creds)
    monkeypatch.setattr(booking_service, "_freebusy_query", fake.freebusy)
    monkeypatch.setattr(gc, "_create_event_blocking", fake.create_event)
    return fake


def _open_slot(nth: int = 1, hour: int = 10) -> tuple[datetime, datetime]:
    """המועד התקין ה-N-י קדימה, במשך של הקישור הפתוח, ב-UTC.

    `nth` סופר **ימים שיש בהם את השעה הזו**, לא ימים קלנדריים, ומדלג על
    סופ"ש וחגים דרך `_candidate_slots` — אותה פונקציה שהשירות משתמש בה.
    """
    from app.services.booking import _candidate_slots, open_booking_duration_minutes
    from app.utils.work_hours import to_israel_tz

    duration = open_booking_duration_minutes()
    today = to_israel_tz(datetime.now(timezone.utc)).date()
    found = 0
    for extra in range(1, 41):
        day = today + timedelta(days=extra)
        wanted = datetime.combine(day, time(hour, 0, tzinfo=ISRAEL_TZ))
        match = next(
            (s for s in _candidate_slots(day, duration) if s[0] == wanted), None
        )
        if match is None:
            continue
        found += 1
        if found == nth:
            return (
                match[0].astimezone(timezone.utc),
                match[1].astimezone(timezone.utc),
            )
    raise AssertionError(f"לא נמצאו {nth} מועדים תקינים ב-40 הימים הקרובים")


async def _mk_lead(db, *, name: str = "ליד לבדיקת הקישור הפתוח"):
    """ליד **בלי קטגוריית שירות** — כך משך הפגישה שלו זהה לזה של הקישור
    הפתוח, והשוואה בין שתי הרשתות היא השוואה של אותו דבר."""
    from app.constants import LeadStatus
    from app.models.lead import Lead

    lead = Lead(full_name=name, source_channel="manual", status=LeadStatus.NEW.value)
    db.add(lead)
    await db.flush()
    await db.refresh(lead)
    return lead


async def _count(db, model) -> int:
    from sqlalchemy import func, select

    return (await db.execute(select(func.count()).select_from(model))).scalar_one()


async def _open_row(db, booking_id):
    from sqlalchemy import select

    from app.models.booking import Booking

    return (
        await db.execute(
            select(Booking)
            .where(Booking.id == booking_id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()


async def _book_open(db, google, *, nth: int = 1, hour: int = 10, name: str = "דנה כהן"):
    """קובעת בקישור הפתוח ומחזירה את מזהה השורה.

    המזהה נשלף מ-Google המזויף ולא מהתשובה: `OpenBookingResponse` אינו
    חושף אותו בכוונה, ולטסט אין דרך לגיטימית אחרת להגיע אליו.
    """
    from app.services.booking import create_open_booking

    start, end = _open_slot(nth, hour)
    await create_open_booking(
        db, full_name=name, contact_phone="052-1234567", slot_start=start, slot_end=end
    )
    return google.created[-1]["booking_id"], start, end


# ===================== 1–2: מה נכנס ליומן, ומה לא נוצר =====================


async def test_event_carries_name_phone_and_time_in_the_target_calendar_only(db, google):
    """הלב של הפיצ'ר, כפי שהמתאם ניסח אותו: שם, טלפון ומועד — ביומן אחד.

    `EXTRA_CALENDAR` מוגדר בכוונה: הוא משמש לחישוב הזמינות בלבד, ואסור
    שהאירוע ייכתב אליו. זו "בלי כפילות ליומנים" מהבקשה.
    """
    from app.constants import BookingStatus
    from app.models.activity import Activity
    from app.models.lead import Lead
    from app.models.task import Task
    from app.services.booking import create_open_booking

    before = {m: await _count(db, m) for m in (Lead, Activity, Task)}
    start, end = _open_slot(1)

    res = await create_open_booking(
        db,
        full_name="דנה כהן",
        contact_phone="052-1234567",
        slot_start=start,
        slot_end=end,
    )
    assert (res.slot_start, res.slot_end) == (start, end)

    assert len(google.created) == 1, "האירוע חייב להיווצר פעם אחת בדיוק"
    event = google.created[0]
    assert event["calendar_id"] == TARGET_CALENDAR
    assert event["summary"] == "פגישה — דנה כהן"
    assert "טלפון: 052-1234567" in event["description"]
    assert (event["start"], event["end"]) == (start, end)

    # **קריאה חוזרת של השורה** — ערך ההחזרה של הכתיבה אינו אימות שלה.
    row = await _open_row(db, event["booking_id"])
    assert row.lead_id is None
    assert row.contact_name == "דנה כהן"
    assert row.contact_phone == "052-1234567"
    assert row.status == BookingStatus.APPROVED.value
    assert row.google_calendar_event_id == event["event_id"]
    assert row.google_calendar_id == TARGET_CALENDAR

    # "זהו": שום ישות אחרת לא נוצרה.
    after = {m: await _count(db, m) for m in (Lead, Activity, Task)}
    assert after == before


async def test_calendar_title_is_not_html_escaped(db, google):
    """`summary` אינו HTML (מסמך ה-discovery של Calendar v3), ולכן `&`
    נשאר `&`. escape כאן היה מציג ביומן "בן &amp; ג'רי"."""
    from app.services.booking import create_open_booking

    start, end = _open_slot(1)
    await create_open_booking(
        db, full_name="בן & ג'רי", contact_phone="052-1234567",
        slot_start=start, slot_end=end,
    )
    assert google.created[0]["summary"] == "פגישה — בן & ג'רי"


# ===================== 3: אותו מועד לא נתפס פעמיים =====================


async def test_open_link_and_lead_link_block_each_other(db, google):
    """ההתנגשות החוצה-מסלולים, בשני הכיוונים."""
    from app.core.exceptions import ConflictError
    from app.services.booking import create_booking_request, create_open_booking

    lead = await _mk_lead(db)

    # ליד קבע ראשון → הקישור הפתוח נחסם.
    a_start, a_end = _open_slot(1)
    await create_booking_request(
        db, lead.booking_token, a_start, a_end, contact_phone="052-1234567"
    )
    with pytest.raises(ConflictError):
        await create_open_booking(
            db, full_name="דנה", contact_phone="052-7654321",
            slot_start=a_start, slot_end=a_end,
        )

    # הקישור הפתוח קבע ראשון → הליד נחסם.
    b_start, b_end = _open_slot(2)
    await create_open_booking(
        db, full_name="דנה", contact_phone="052-7654321",
        slot_start=b_start, slot_end=b_end,
    )
    with pytest.raises(ConflictError):
        await create_booking_request(
            db, lead.booking_token, b_start, b_end, contact_phone="052-1234567"
        )


async def test_overlap_is_refused_by_the_database_not_only_by_the_precheck(
    db, google, monkeypatch
):
    """הבדיקה המוקדמת מבוטלת, כדי לדמות את חלון ה-race שבו שתי בקשות
    עברו אותה יחד. מה שנשאר לחסום הוא `ck_bookings_no_overlap` — והוא
    חייב לחסום גם שורה בלי ליד.

    ובנוסף: השנייה לא הגיעה ל-Google. השורה נכנסת **לפני** הקריאה
    החיצונית (CORE U1), ולכן סירוב של ה-DB עוצר לפני שנוצר אירוע כפול.
    """
    from app.core.exceptions import ConflictError
    from app.services import booking as booking_service

    async def _no_precheck(*_args, **_kwargs):
        return None

    monkeypatch.setattr(booking_service, "_assert_slot_still_free", _no_precheck)

    start, end = _open_slot(1)
    await booking_service.create_open_booking(
        db, full_name="ראשונה", contact_phone="052-1234567",
        slot_start=start, slot_end=end,
    )
    with pytest.raises(ConflictError):
        await booking_service.create_open_booking(
            db, full_name="שנייה", contact_phone="052-7654321",
            slot_start=start, slot_end=end,
        )
    assert len(google.created) == 1


async def test_two_concurrent_open_bookings_on_one_slot_one_wins(monkeypatch):
    """**במקביל**, על שני חיבורים נפרדים (testing.md §3).

    שתי הבקשות עוברות יחד את הבדיקה המוקדמת — אף אחת לא רואה את השורה
    של השנייה, כי היא עוד לא נשמרה. מה שמכריע הוא ה-EXCLUDE: ה-INSERT
    השני ממתין לטרנזקציה הראשונה, ונכשל כשהיא נשמרת.

    הטסט הזה **אינו** משתמש ב-fixture `db`: טרנזקציה אחת על חיבור אחד
    אינה יכולה לייצר מקביליות אמיתית. לכן השורה של המנצחת נשמרת באמת,
    ונמחקת ב-`finally` לפי המזהה שלה בלבד.
    """
    from sqlalchemy import delete, select
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.config import get_settings
    from app.constants import BookingStatus
    from app.core.exceptions import ConflictError
    from app.models.booking import Booking
    from app.services import booking as booking_service
    from app.services import google_calendar as gc

    async def _connected_no_busy(_db, _start, _end):
        return [], True

    created: list = []

    async def _slow_event(_db, *, booking_id, summary, description, start, end):
        # מחזיק את הטרנזקציה הראשונה פתוחה מספיק זמן כדי שה-INSERT
        # השני ייתקל בשורה שלה לפני שהיא נשמרת.
        await asyncio.sleep(0.3)
        created.append(booking_id)
        return f"evt-{booking_id}", TARGET_CALENDAR

    monkeypatch.setattr(booking_service, "_fetch_google_busy", _connected_no_busy)
    monkeypatch.setattr(gc, "create_calendar_event", _slow_event)

    engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
    try:
        # מועד שאין עליו פגישה פעילה ב-DB המקומי — הטסט שומר באמת, ולכן
        # אסור לו להיתקל בנתונים שלא הוא יצר.
        async with AsyncSession(engine) as probe:
            for nth in range(1, 15):
                start, end = _open_slot(nth, hour=15)
                taken = (
                    await probe.execute(
                        select(Booking.id).where(
                            Booking.status.in_(booking_service.ACTIVE_BOOKING_STATUSES),
                            Booking.requested_slot_start < end,
                            Booking.requested_slot_end > start,
                        )
                    )
                ).first()
                if taken is None:
                    break
            else:
                pytest.skip("לא נמצא מועד פנוי ב-DB המקומי")

        async def _attempt(name: str):
            async with AsyncSession(engine, expire_on_commit=False) as session:
                try:
                    await booking_service.create_open_booking(
                        session, full_name=name, contact_phone="052-1234567",
                        slot_start=start, slot_end=end,
                    )
                    return "ok"
                except ConflictError:
                    return "conflict"

        results = await asyncio.gather(_attempt("ראשונה"), _attempt("שנייה"))
        assert sorted(results) == ["conflict", "ok"], results
        assert len(created) == 1, "רק המנצחת הגיעה ל-Google"

        async with AsyncSession(engine) as check:
            active = (
                await check.execute(
                    select(Booking.id).where(
                        Booking.lead_id.is_(None),
                        Booking.status == BookingStatus.APPROVED.value,
                        Booking.requested_slot_start == start,
                    )
                )
            ).scalars().all()
        assert active == created
    finally:
        async with AsyncSession(engine) as cleanup:
            if created:
                await cleanup.execute(delete(Booking).where(Booking.id.in_(created)))
                await cleanup.commit()
        await engine.dispose()


# ===================== בלי יומן — סירוב, לא הצלחה חלקית =====================


async def test_booking_is_refused_without_a_calendar_and_leaves_no_row(db):
    """בלי יומן אין לפיצ'ר מה לעשות — ולכן סירוב, ולא שורה בלי אירוע.

    זה ההבדל מזרימת הליד, ששם נשמרת פגישה מסומנת ונועה רואה אזהרה
    בכרטיס. כאן אין כרטיס: שורה כזו לא הייתה נראית לאף אחד, בזמן
    שהלקוח קיבל "נקבע".
    """
    from sqlalchemy import func, select

    from app.models.booking import Booking
    from app.services.booking import OpenBookingUnavailable, create_open_booking

    start, end = _open_slot(1)
    with pytest.raises(OpenBookingUnavailable):
        await create_open_booking(
            db, full_name="דנה", contact_phone="052-1234567",
            slot_start=start, slot_end=end,
        )
    left = (
        await db.execute(
            select(func.count())
            .select_from(Booking)
            .where(Booking.lead_id.is_(None), Booking.requested_slot_start == start)
        )
    ).scalar_one()
    assert left == 0


async def test_availability_is_refused_without_a_calendar(db):
    """רשת בלי Google הייתה מציעה מועדים שאי אפשר לקבוע — והלקוח היה
    מגלה את זה רק אחרי שמילא שם וטלפון."""
    from app.services.booking import OpenBookingUnavailable, get_open_availability

    start, _ = _open_slot(1)
    day = start.astimezone(ISRAEL_TZ).date()
    with pytest.raises(OpenBookingUnavailable):
        await get_open_availability(db, day, day)


# ===================== רשת אחת לשני המסלולים =====================


async def test_open_grid_equals_the_lead_grid(db, google):
    """"אותם מקורות busy בדיוק" — כאן כהשוואה ולא כהבטחה בהערה.

    ביום הבדיקה יש שלושה דברים תפוסים: פגישה של ליד, פגישה מהקישור הפתוח,
    ואירוע ב-Google. שתי הרשתות חייבות להסתיר את שלושתם, ולהיות זהות.
    """
    from app.services.booking import (
        create_booking_request,
        get_availability,
        get_open_availability,
    )

    lead = await _mk_lead(db)
    lead_start, lead_end = _open_slot(1, hour=10)
    await create_booking_request(
        db, lead.booking_token, lead_start, lead_end, contact_phone="052-1234567"
    )
    _, open_start, _ = await _book_open(db, google, nth=1, hour=12)
    google_busy_start, google_busy_end = _open_slot(1, hour=14)
    google.busy = [(google_busy_start, google_busy_end)]

    day = lead_start.astimezone(ISRAEL_TZ).date()
    lead_days, _ = await get_availability(db, lead.booking_token, day, day)
    open_days, _ = await get_open_availability(db, day, day)

    assert open_days == lead_days
    offered = {s.start for s in open_days[0].slots}
    for taken in (lead_start, open_start, google_busy_start):
        assert taken not in offered


async def test_page_info_comes_from_the_server_clock(db):
    from app.services.booking import (
        booking_horizon_end,
        get_open_booking_page_info,
        open_booking_duration_minutes,
    )
    from app.utils.work_hours import to_israel_tz

    info = get_open_booking_page_info()
    assert info.today == to_israel_tz(datetime.now(timezone.utc)).date()
    assert info.booking_horizon_end == booking_horizon_end()
    assert info.default_duration_minutes == open_booking_duration_minutes()


# ===================== 4: מי שצורך את `bookings` =====================


async def test_google_cancel_of_an_open_booking_frees_the_slot_without_an_error(db, google):
    """הבאג: הענף הנפרד לשורה בלי ליד החזיר `"applied"`, שאינו מפתח
    ב-`stats`. כל ביטול מוצלח נספר כשגיאה, וה-sync token לא התקדם."""
    from app.constants import BookingStatus
    from app.models.activity import Activity
    from app.services.booking_sync import apply_calendar_changes
    from app.services.google_calendar import CalendarChange

    booking_id, _, _ = await _book_open(db, google)
    event_id = google.created[-1]["event_id"]
    activities_before = await _count(db, Activity)

    stats = await apply_calendar_changes(
        db,
        [CalendarChange(booking_id=booking_id, event_id=event_id,
                        status="cancelled", start=None, end=None)],
    )

    assert stats == {"canceled": 1, "rescheduled": 0, "skipped": 0, "errors": 0}
    assert (await _open_row(db, booking_id)).status == BookingStatus.CANCELED.value
    assert await _count(db, Activity) == activities_before


async def test_google_move_of_an_open_booking_moves_the_slot(db, google):
    from app.services.booking_sync import apply_calendar_changes
    from app.services.google_calendar import CalendarChange

    booking_id, _, _ = await _book_open(db, google, nth=1, hour=10)
    new_start, new_end = _open_slot(1, hour=12)

    stats = await apply_calendar_changes(
        db,
        [CalendarChange(booking_id=booking_id,
                        event_id=google.created[-1]["event_id"],
                        status="confirmed", start=new_start, end=new_end)],
    )

    assert stats == {"canceled": 0, "rescheduled": 1, "skipped": 0, "errors": 0}
    row = await _open_row(db, booking_id)
    assert (row.requested_slot_start, row.requested_slot_end) == (new_start, new_end)


async def test_google_move_onto_a_taken_slot_is_skipped_not_an_error(db, google):
    """הבאג: לענף הנפרד חסר ה-`except IntegrityError` שיש במסלול הליד.
    הזזה על פגישה קיימת נספרה כשגיאה בכל webhook, וה-sync token לא
    היה מתקדם לעולם — כל שינוי ביומן מאז היה מעובד מחדש, לנצח."""
    from app.services.booking import create_booking_request
    from app.services.booking_sync import apply_calendar_changes
    from app.services.google_calendar import CalendarChange

    lead = await _mk_lead(db)
    taken_start, taken_end = _open_slot(1, hour=12)
    await create_booking_request(
        db, lead.booking_token, taken_start, taken_end, contact_phone="052-1234567"
    )
    booking_id, own_start, own_end = await _book_open(db, google, nth=1, hour=10)

    stats = await apply_calendar_changes(
        db,
        [CalendarChange(booking_id=booking_id,
                        event_id=google.created[-1]["event_id"],
                        status="confirmed", start=taken_start, end=taken_end)],
    )

    assert stats == {"canceled": 0, "rescheduled": 0, "skipped": 1, "errors": 0}
    row = await _open_row(db, booking_id)
    assert (row.requested_slot_start, row.requested_slot_end) == (own_start, own_end)


async def test_nightly_expiry_survives_open_booking_rows(db):
    """הבאג: שלב 4 רשם activity לכל שורה שפגה, עם `lead_id=None`.

    פגישה מהקישור הפתוח פגה ברגע שמועדה עבר — זה מחזור החיים הרגיל
    שלה. `activities.lead_id` הוא NOT NULL, ולכן הריצה כולה נפלה: שום
    פגישה לא סומנה, ואף ליד לא שוחרר מ-BOOKED, בכל לילה מחדש.
    """
    from sqlalchemy import func, select

    from app.constants import ActivityType, BookingStatus
    from app.models.activity import Activity
    from app.models.booking import Booking
    from app.services.booking import expire_all_stale_bookings

    lead = await _mk_lead(db)
    past = datetime.now(timezone.utc) - timedelta(days=2)
    lead_row = Booking(
        lead_id=lead.id, requested_slot_start=past,
        requested_slot_end=past + timedelta(hours=1),
        status=BookingStatus.APPROVED.value,
    )
    # שעה אחרת, כדי שה-EXCLUDE לא ידחה את שתי השורות כחופפות.
    open_past = past - timedelta(hours=3)
    open_row = Booking(
        lead_id=None, contact_name="דנה", contact_phone="052-1234567",
        requested_slot_start=open_past,
        requested_slot_end=open_past + timedelta(hours=1),
        status=BookingStatus.APPROVED.value,
    )
    db.add_all([lead_row, open_row])
    await db.flush()

    await expire_all_stale_bookings(db)

    assert (await _open_row(db, lead_row.id)).status == BookingStatus.CANCELED.value
    assert (await _open_row(db, open_row.id)).status == BookingStatus.CANCELED.value
    logged = (
        await db.execute(
            select(func.count())
            .select_from(Activity)
            .where(
                Activity.lead_id == lead.id,
                Activity.type == ActivityType.MEETING_CANCELED.value,
            )
        )
    ).scalar_one()
    assert logged == 1, "הליד עדיין מקבל את השורה שלו בציר הזמן"


async def test_manual_cancel_route_does_not_reach_an_open_booking(db, google):
    """הבאג: `cancel_booking` אינו תחום לליד, ומזהה של שורה בלי ליד
    הגיע עד `log_activity(lead_id=None)` ונפל ב-500."""
    from app.constants import BookingStatus
    from app.core.exceptions import NotFoundError
    from app.services.booking import cancel_booking

    booking_id, _, _ = await _book_open(db, google)

    with pytest.raises(NotFoundError):
        await cancel_booking(db, booking_id=booking_id, performed_by_id=uuid4())

    assert (await _open_row(db, booking_id)).status == BookingStatus.APPROVED.value


# ===================== דרך ה-HTTP — כמו שהדפדפן צורך =====================


def _client():
    import httpx

    from app.main import app

    # `ASGITransport` שולח רק scope מסוג http, ולכן ה-lifespan של
    # האפליקציה (scheduler וכו') לא רץ. הבקשה פותחת session דרך
    # `get_db` ← `AsyncSessionLocal`, שה-fixture `db` קושר לחיבור של
    # הטסט — כלומר היא רצה בתוך הטרנזקציה שמתגלגלת אחורה בסוף.
    # מקור: httpx/_transports/asgi.py (0.28.1), tests/conftest.py §3.
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )


@pytest.fixture(autouse=True)
def _fresh_open_limiters():
    """המכסות גלובליות לתהליך. בלי איפוס, טסט אחד היה יכול לנצל מכסה
    של אחר ולקבל 429 שאינו קשור למה שהוא בודק."""
    from app.api.routes import booking_page

    booking_page._open_booking_limiter.reset()
    booking_page._open_availability_limiter.reset()


async def test_open_routes_are_not_swallowed_by_the_token_route(db):
    """`/booking/open` נרשם לפני `/booking/{token}`. בסדר ההפוך FastAPI
    מתאים את `open` לתבנית ה-UUID ומחזיר 422 — ולא נופל ל-route הבא."""
    async with _client() as client:
        info = await client.get("/booking/open")
        assert info.status_code == 200, info.text
        body = info.json()
        assert set(body) >= {"today", "booking_horizon_end", "default_duration_minutes"}

        day = body["today"]
        availability = await client.get(
            f"/booking/open/availability?date_from={day}&date_to={day}"
        )
    # סביבת הטסטים אינה מחוברת ל-Google — ולכן הסירוב הייעודי, ולא 422.
    assert availability.status_code == 503, availability.text
    assert availability.json() == {
        "error": "open_booking_unavailable",
        "message": "לא ניתן לקבוע פגישה דרך הקישור הזה כרגע.",
    }


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"full_name": "   "}, "יש להזין שם."),
        ({"full_name": "א" * 201}, "הערך שהוזן ארוך מדי. מותרים עד 200 תווים."),
        (
            {"contact_phone": "05212345678"},
            "מספר טלפון לא תקין. נייד = 10 ספרות (05X), קווי = 9 ספרות (0X).",
        ),
        ({"full_name": None}, "יש להזין שם."),
    ],
)
async def test_each_refusal_names_its_own_reason(db, overrides, message):
    """ארבע תקלות שונות, ארבע הודעות שונות. עד התיקון ב-`main.py` שלושתן
    הראשונות קיבלו את אותה הודעה, והיא אמרה שהשדה *חסר* גם כשהיה ארוך
    מדי — כלומר שלחה את הלקוח לחפש במקום הלא נכון."""
    start, end = _open_slot(1)
    payload = {
        "full_name": "דנה כהן",
        "contact_phone": "052-1234567",
        "slot_start": start.isoformat(),
        "slot_end": end.isoformat(),
        **overrides,
    }
    payload = {k: v for k, v in payload.items() if v is not None}
    async with _client() as client:
        res = await client.post("/booking/open", json=payload)
    assert res.status_code == 422, res.text
    assert res.json()["message"] == message


async def test_booking_over_http_normalizes_the_phone_and_hides_the_row_id(db, google):
    """המסלול המלא כפי שהדף מריץ אותו: הסכמה מנרמלת את הטלפון, השירות
    כותב, והתשובה אינה חושפת מזהה של שורה שאין ללקוח מה לעשות איתה."""
    start, end = _open_slot(1)
    async with _client() as client:
        res = await client.post(
            "/booking/open",
            json={
                "full_name": "  דנה   כהן ",
                "contact_phone": "+972 52 123 4567",
                "slot_start": start.isoformat(),
                "slot_end": end.isoformat(),
            },
        )
    assert res.status_code == 201, res.text
    assert set(res.json()) == {"slot_start", "slot_end"}

    event = google.created[-1]
    assert "טלפון: 052-1234567" in event["description"]
    # הרווחים הפנימיים מתנרמלים בכותרת; השם השמור הוא מה שהלקוח הקליד,
    # בלי רווחי הקצוות בלבד.
    assert event["summary"] == "פגישה — דנה כהן"
    row = await _open_row(db, event["booking_id"])
    assert (row.contact_name, row.contact_phone) == ("דנה   כהן", "052-1234567")
