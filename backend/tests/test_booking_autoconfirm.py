"""
זרימת הפגישה החדשה: נקבעת מיד, כמה פגישות לליד, ביטול.

הטסטים כאן מכסים את שלושת השינויים שביקש הלקוח בבת אחת, כי הם חולקים
את אותה טרנזקציה ואת אותם side-effects:
- הפגישה נקבעת בלי אישור של נועה (`status=approved`).
- ליד יכול להחזיק כמה פגישות עתידיות, עד תקרה.
- טלפון חובה, והערה מגיעה לתיאור האירוע ביומן.

**Google לא מחובר בטסטים האלה**, ולכן `create_calendar_event` מרים
`GoogleNotConnectedError` ו-`create_booking_request` ממשיך בלי
`event_id` — בדיוק המסלול "היומן כבוי" בפרודקשן. מה שדורש יומן חי
נבדק בנפרד דרך פונקציות טהורות (`build_event_description`,
`_parse_freebusy_response`).
"""

from datetime import datetime, time, timedelta, timezone

import pytest

from app.utils.work_hours import ISRAEL_TZ

pytestmark = pytest.mark.asyncio


async def _mk_lead(db, *, name: str = "בדיקת פגישות"):
    from app.constants import LeadStatus
    from app.models.lead import Lead

    lead = Lead(
        full_name=name,
        source_channel="manual",
        status=LeadStatus.NEW.value,
    )
    db.add(lead)
    await db.flush()
    await db.refresh(lead)
    return lead


def _next_workday_slot(offset_days: int = 1, hour: int = 10):
    """המועד התקין ה-N-י קדימה (1 = הקרוב ביותר), מוחזר ב-UTC.

    `offset_days` הוא **מונה של ימי עבודה**, לא הפרש בימים קלנדריים.
    זה חשוב: הגרסה הראשונה של ה-helper פשוט הוסיפה N ימים וחיפשה
    קדימה, ולכן 1 ו-2 החזירו את *אותו* יום כששניהם נפלו על סוף שבוע —
    ושלושה טסטים נכשלו על "הסלוט כבר תפוס" במקום על מה שהם בודקים.

    מדלג על שבת/שישי/חג דרך אותה פונקציה שהשירות משתמש בה, כדי שהטסט
    לא יישבר בערב חג אקראי.
    """
    from app.services.booking import _candidate_slots, default_duration_minutes
    from app.utils.work_hours import to_israel_tz

    duration = default_duration_minutes("clinic")
    day = to_israel_tz(datetime.now(timezone.utc)).date()
    found = 0
    # 40 ימים קדימה מכסים בנוחות גם רצף חגים ארוך.
    for extra in range(1, 41):
        candidate_day = day + timedelta(days=extra)
        slots = _candidate_slots(candidate_day, duration)
        wanted = datetime.combine(candidate_day, time(hour, 0, tzinfo=ISRAEL_TZ))
        match = next((s for s in slots if s[0] == wanted), None)
        if match is None:
            continue
        found += 1
        if found == offset_days:
            start, end = match
            return (
                start.astimezone(timezone.utc),
                end.astimezone(timezone.utc),
            )
    raise AssertionError(
        f"לא נמצאו {offset_days} סלוטים תקינים ב-40 הימים הקרובים"
    )


# ===================== קביעה מיידית =====================


async def test_booking_is_confirmed_immediately(db):
    """הליד בוחר מועד → הפגישה מאושרת, הליד BOOKED, והכדור אצל הלקוח.

    זה הלב של השינוי: עד עכשיו נוצרה *בקשה* ב-pending_approval שחיכתה
    לנועה.
    """
    from sqlalchemy import select

    from app.constants import ActivityType, BookingStatus, LeadStatus, WaitingOn
    from app.models.activity import Activity
    from app.models.lead import Lead
    from app.services import booking as booking_service

    lead = await _mk_lead(db)
    start, end = _next_workday_slot()

    res = await booking_service.create_booking_request(
        db,
        token=lead.booking_token,
        slot_start=start,
        slot_end=end,
        contact_phone="052-1234567",
        notes="הפגישה הראשונה שלי",
    )

    assert res.status == BookingStatus.APPROVED.value

    refreshed = (
        await db.execute(
            select(Lead)
            .where(Lead.id == lead.id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    assert refreshed.status == LeadStatus.BOOKED.value
    assert refreshed.waiting_on == WaitingOn.CLIENT.value
    # `last_activity_type` חייב להיות זהה ל-type שנרשם ב-activity log,
    # אחרת סינונים downstream נשברים.
    assert refreshed.last_activity_type == ActivityType.MEETING_APPROVED.value

    activities = (
        await db.execute(
            select(Activity).where(Activity.lead_id == lead.id)
        )
    ).scalars().all()
    meeting_acts = [
        a
        for a in activities
        if a.type
        in (
            ActivityType.MEETING_APPROVED.value,
            ActivityType.MEETING_REQUESTED.value,
        )
    ]
    # **רשומה אחת בדיוק.** שתי רשומות באותה טרנזקציה מקבלות `created_at`
    # זהה (זמן הטרנזקציה), וכל שאילתת "האחרון" הופכת להגרלה.
    assert len(meeting_acts) == 1
    assert meeting_acts[0].type == ActivityType.MEETING_APPROVED.value
    # `booking_id` ב-metadata הוא תנאי הכרחי: `post_meeting_tasks`
    # מזהה דרכו שהפגישה אושרה אי-פעם.
    assert meeting_acts[0].activity_metadata["booking_id"] == str(
        res.booking_id
    )
    assert meeting_acts[0].activity_metadata["auto_confirmed"] is True


async def test_booking_closes_stale_followup_tasks(db):
    """קביעת פגישה היא touchpoint — סוגרת משימות שכבר לא רלוונטיות.

    בלי זה, "הלקוח לא חזר" ממשיך להופיע ב-/today אחרי שהלקוח קבע תור.
    """
    from sqlalchemy import select

    from app.constants import TaskStatus, TaskType
    from app.models.task import Task
    from app.services import booking as booking_service

    lead = await _mk_lead(db)
    task = Task(
        lead_id=lead.id,
        type=TaskType.WARM_FOLLOWUP.value,
        status=TaskStatus.OPEN.value,
        due_at=datetime.now(timezone.utc),
        origin_rule="test",
    )
    db.add(task)
    await db.flush()

    start, end = _next_workday_slot()
    await booking_service.create_booking_request(
        db,
        token=lead.booking_token,
        slot_start=start,
        slot_end=end,
        contact_phone="052-1234567",
    )

    refreshed = (
        await db.execute(
            select(Task)
            .where(Task.id == task.id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    assert refreshed.status == TaskStatus.DONE.value


# ===================== כמה פגישות לליד =====================


async def test_same_lead_can_book_a_second_meeting(db):
    """הבאג שדווח: הקישור היה חד-פעמי בפועל.

    עד מיגרציה 0032, אינדקס ייחודי חסם פגישה שנייה לאותו ליד, והלקוח
    שפתח את הקישור בשנית קיבל מסך "כבר יש לך בקשת פגישה".
    """
    from app.services import booking as booking_service

    lead = await _mk_lead(db)
    first_start, first_end = _next_workday_slot(offset_days=1)
    second_start, second_end = _next_workday_slot(offset_days=2)

    await booking_service.create_booking_request(
        db,
        token=lead.booking_token,
        slot_start=first_start,
        slot_end=first_end,
        contact_phone="052-1234567",
    )
    second = await booking_service.create_booking_request(
        db,
        token=lead.booking_token,
        slot_start=second_start,
        slot_end=second_end,
        contact_phone="052-1234567",
    )

    assert second.booking_id is not None
    active = await booking_service._active_bookings(db, lead.id)
    assert len(active) == 2
    # סדר עולה — "הפגישה הבאה" היא הראשונה ברשימה.
    assert active[0].requested_slot_start < active[1].requested_slot_start


async def test_booking_page_no_longer_blocks_on_existing_meeting(db):
    """הדף הציבורי ממשיך להציע מועדים גם כשכבר יש פגישה."""
    from app.services import booking as booking_service

    lead = await _mk_lead(db)
    start, end = _next_workday_slot()
    await booking_service.create_booking_request(
        db,
        token=lead.booking_token,
        slot_start=start,
        slot_end=end,
        contact_phone="052-1234567",
    )

    info = await booking_service.get_booking_page_info(db, lead.booking_token)
    assert len(info.upcoming_bookings) == 1
    assert info.can_book_more is True


async def test_cap_blocks_the_fourth_meeting(db):
    """תקרה: 3 פגישות עתידיות מותרות, הרביעית נחסמת בעברית."""
    from app.core.exceptions import ConflictError
    from app.services import booking as booking_service

    lead = await _mk_lead(db)
    for day in range(1, booking_service.MAX_ACTIVE_BOOKINGS_PER_LEAD + 1):
        start, end = _next_workday_slot(offset_days=day)
        await booking_service.create_booking_request(
            db,
            token=lead.booking_token,
            slot_start=start,
            slot_end=end,
            contact_phone="052-1234567",
        )

    over_start, over_end = _next_workday_slot(
        offset_days=booking_service.MAX_ACTIVE_BOOKINGS_PER_LEAD + 1
    )
    with pytest.raises(ConflictError) as exc:
        await booking_service.create_booking_request(
            db,
            token=lead.booking_token,
            slot_start=over_start,
            slot_end=over_end,
            contact_phone="052-1234567",
        )
    assert "פגישות" in exc.value.user_message

    info = await booking_service.get_booking_page_info(db, lead.booking_token)
    assert info.can_book_more is False


async def test_overlapping_slot_is_rejected_across_leads(db):
    """שני לידים שונים לא יכולים לתפוס את אותו מועד.

    זו ההגנה שנשארה אחרי שהאינדקס הייחודי הוסר — היא פועלת ברמת ה-DB
    (`ck_bookings_no_overlap`), ולכן תופסת גם race אמיתי.
    """
    from app.core.exceptions import ConflictError
    from app.services import booking as booking_service

    lead_a = await _mk_lead(db, name="ליד א")
    lead_b = await _mk_lead(db, name="ליד ב")
    start, end = _next_workday_slot()

    await booking_service.create_booking_request(
        db,
        token=lead_a.booking_token,
        slot_start=start,
        slot_end=end,
        contact_phone="052-1234567",
    )
    with pytest.raises(ConflictError):
        await booking_service.create_booking_request(
            db,
            token=lead_b.booking_token,
            slot_start=start,
            slot_end=end,
            contact_phone="053-7654321",
        )


# ===================== ביטול =====================


async def test_canceling_one_of_two_keeps_lead_booked(db):
    """הרגרסיה שהאינדקס הישן הסתיר.

    ביטול פגישה החזיר את הליד ל-IN_PROGRESS ללא תנאי. כל עוד יכלה
    להיות פגישה אחת בלבד זה היה נכון; עם שתיים, ביטול של אחת היה
    מוציא את הליד מ-BOOKED בזמן שהשנייה עומדת ביומן.
    """
    from sqlalchemy import select

    from app.constants import LeadStatus
    from app.models.lead import Lead
    from app.services import booking as booking_service

    lead = await _mk_lead(db)
    s1, e1 = _next_workday_slot(offset_days=1)
    s2, e2 = _next_workday_slot(offset_days=2)
    first = await booking_service.create_booking_request(
        db, token=lead.booking_token, slot_start=s1, slot_end=e1,
        contact_phone="052-1234567",
    )
    await booking_service.create_booking_request(
        db, token=lead.booking_token, slot_start=s2, slot_end=e2,
        contact_phone="052-1234567",
    )

    owner_id = await _mk_user(db)
    await booking_service.cancel_booking(
        db, booking_id=first.booking_id, performed_by_id=owner_id
    )

    refreshed = (
        await db.execute(
            select(Lead)
            .where(Lead.id == lead.id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    assert refreshed.status == LeadStatus.BOOKED.value


async def test_canceling_the_last_meeting_releases_the_lead(db):
    """כשלא נשארה אף פגישה — הליד חוזר לטיפול של נועה."""
    from sqlalchemy import select

    from app.constants import LeadStatus, WaitingOn
    from app.models.lead import Lead
    from app.services import booking as booking_service

    lead = await _mk_lead(db)
    start, end = _next_workday_slot()
    created = await booking_service.create_booking_request(
        db, token=lead.booking_token, slot_start=start, slot_end=end,
        contact_phone="052-1234567",
    )

    owner_id = await _mk_user(db)
    await booking_service.cancel_booking(
        db, booking_id=created.booking_id, performed_by_id=owner_id
    )

    refreshed = (
        await db.execute(
            select(Lead)
            .where(Lead.id == lead.id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    assert refreshed.status == LeadStatus.IN_PROGRESS.value
    assert refreshed.waiting_on == WaitingOn.NOAH.value


async def test_cancel_marks_source_so_no_post_meeting_task(db):
    """מקור הביטול נרשם — וזה מה שמונע משימת "מה היה בפגישה" מיותרת.

    `post_meeting_tasks` מחשיב פגישה מבוטלת שאושרה בעבר כאילו התקיימה
    (זה המסלול של ניקוי ה-cron). הוא מדלג רק על מקורות שמשמעותם
    "בוטלה לפני המועד" — ולכן המקור חייב להירשם.
    """
    from sqlalchemy import select

    from app.constants import (
        BOOKING_CANCEL_SOURCES_MEETING_NOT_HELD,
        ActivityType,
        BookingCancelSource,
    )
    from app.models.activity import Activity
    from app.services import booking as booking_service

    lead = await _mk_lead(db)
    start, end = _next_workday_slot()
    created = await booking_service.create_booking_request(
        db, token=lead.booking_token, slot_start=start, slot_end=end,
        contact_phone="052-1234567",
    )
    owner_id = await _mk_user(db)
    await booking_service.cancel_booking(
        db, booking_id=created.booking_id, performed_by_id=owner_id
    )

    cancel_act = (
        await db.execute(
            select(Activity).where(
                Activity.lead_id == lead.id,
                Activity.type == ActivityType.MEETING_CANCELED.value,
            )
        )
    ).scalars().one()
    assert (
        cancel_act.activity_metadata["source"]
        == BookingCancelSource.MANUAL.value
    )
    assert cancel_act.activity_metadata["applied"] is True
    # ולידציה שהמקור באמת ברשימה שה-cron מסנן לפיה.
    assert (
        cancel_act.activity_metadata["source"]
        in BOOKING_CANCEL_SOURCES_MEETING_NOT_HELD
    )


async def test_double_cancel_is_rejected_but_logged(db):
    """ביטול שני מקבל שגיאה ברורה, וה-activity מתעד את הניסיון.

    כלל 9: ה-log מתעד את ה-*כוונה*, לא רק את מה שה-UPDATE הצליח לכתוב.
    """
    from sqlalchemy import select

    from app.constants import ActivityType
    from app.core.exceptions import ConflictError
    from app.models.activity import Activity
    from app.services import booking as booking_service

    lead = await _mk_lead(db)
    start, end = _next_workday_slot()
    created = await booking_service.create_booking_request(
        db, token=lead.booking_token, slot_start=start, slot_end=end,
        contact_phone="052-1234567",
    )
    owner_id = await _mk_user(db)
    await booking_service.cancel_booking(
        db, booking_id=created.booking_id, performed_by_id=owner_id
    )

    with pytest.raises(ConflictError):
        await booking_service.cancel_booking(
            db, booking_id=created.booking_id, performed_by_id=owner_id
        )

    acts = (
        await db.execute(
            select(Activity).where(
                Activity.lead_id == lead.id,
                Activity.type == ActivityType.MEETING_CANCELED.value,
            )
        )
    ).scalars().all()
    assert len(acts) == 2
    applied_flags = sorted(a.activity_metadata["applied"] for a in acts)
    assert applied_flags == [False, True]


async def test_closing_a_lead_cancels_its_future_meetings(db):
    """סגירת ליד מבטלת פגישות עתידיות.

    בלי זה, סגירת ליד הייתה משאירה **פגישה אמיתית ביומן של נועה**
    לליד שכבר נסגר — ואף cron לא היה מנקה אותה.
    """
    from sqlalchemy import select

    from app.constants import BookingStatus, ClosureReason, LeadStatus
    from app.models.booking import Booking
    from app.schemas.lead import LeadCloseRequest
    from app.services import booking as booking_service
    from app.services import leads as leads_service

    lead = await _mk_lead(db)
    start, end = _next_workday_slot()
    created = await booking_service.create_booking_request(
        db, token=lead.booking_token, slot_start=start, slot_end=end,
        contact_phone="052-1234567",
    )

    owner_id = await _mk_user(db)
    await leads_service.close_lead(
        db,
        lead.id,
        LeadCloseRequest(
            target_status=LeadStatus.LOST,
            closure_reason=ClosureReason.NO_RESPONSE,
        ),
        owner_id,
    )

    booking = (
        await db.execute(
            select(Booking)
            .where(Booking.id == created.booking_id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    assert booking.status == BookingStatus.CANCELED.value


# ===================== עזר =====================


async def _mk_user(db):
    """משתמש מינימלי ל-performed_by (FK)."""
    from app.constants import UserRole
    from app.models.user import User

    user = User(
        email=f"test-{datetime.now(timezone.utc).timestamp()}@example.com",
        name="בודקת",
        role=UserRole.OWNER.value,
        password_hash="x",
    )
    db.add(user)
    await db.flush()
    return user.id


# ===================== ניקוי פגישות שפג מועדן =====================


async def test_expire_stale_keeps_lead_booked_when_a_future_meeting_remains(db):
    """הרגרסיה שהאינדקס הישן הפך לבלתי אפשרית.

    `_expire_stale_bookings` הוריד ליד מ-BOOKED ללא תנאי, בהסתמך על
    כך שאינדקס ייחודי מבטיח פגישה פעילה אחת לכל היותר. מרגע שליד יכול
    להחזיק שתיים, ליד עם פגישה שעברה ועוד אחת עתידית היה יוצא מ-BOOKED
    בזמן שהפגישה העתידית עומדת ביומן.
    """
    from sqlalchemy import select

    from app.constants import BookingStatus, LeadStatus
    from app.models.booking import Booking
    from app.models.lead import Lead
    from app.services import booking as booking_service

    lead = await _mk_lead(db)

    # פגישה עתידית — נקבעת דרך ה-flow האמיתי.
    future_start, future_end = _next_workday_slot()
    await booking_service.create_booking_request(
        db, token=lead.booking_token, slot_start=future_start,
        slot_end=future_end, contact_phone="052-1234567",
    )

    # פגישה שכבר עברה — מוזרקת ישירות, כי ה-flow לא מאפשר לקבוע בעבר.
    past = datetime.now(timezone.utc) - timedelta(days=2)
    stale = Booking(
        lead_id=lead.id,
        requested_slot_start=past,
        requested_slot_end=past + timedelta(hours=1),
        status=BookingStatus.APPROVED.value,
    )
    db.add(stale)
    await db.flush()

    canceled = await booking_service._expire_stale_bookings(db, lead.id)
    assert canceled == 1

    refreshed = (
        await db.execute(
            select(Lead)
            .where(Lead.id == lead.id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    assert refreshed.status == LeadStatus.BOOKED.value, (
        "ליד עם פגישה עתידית לא אמור לצאת מ-BOOKED"
    )


async def test_expire_stale_releases_lead_when_nothing_remains(db):
    """בלי פגישה עתידית — הליד כן משוחרר."""
    from sqlalchemy import select

    from app.constants import BookingStatus, LeadStatus, WaitingOn
    from app.models.booking import Booking
    from app.models.lead import Lead
    from app.services import booking as booking_service

    lead = await _mk_lead(db)
    await db.execute(
        Lead.__table__.update()
        .where(Lead.id == lead.id)
        .values(status=LeadStatus.BOOKED.value)
    )

    past = datetime.now(timezone.utc) - timedelta(days=2)
    db.add(
        Booking(
            lead_id=lead.id,
            requested_slot_start=past,
            requested_slot_end=past + timedelta(hours=1),
            status=BookingStatus.APPROVED.value,
        )
    )
    await db.flush()

    await booking_service._expire_stale_bookings(db, lead.id)

    refreshed = (
        await db.execute(
            select(Lead)
            .where(Lead.id == lead.id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    assert refreshed.status == LeadStatus.IN_PROGRESS.value
    assert refreshed.waiting_on == WaitingOn.NOAH.value


async def test_finished_meeting_still_listed_when_another_is_upcoming(db):
    """כפתור "סמני שהפגישה התקיימה" מופיע גם כשיש פגישה נוספת בהמשך.

    הגרסה הקודמת החזירה פגישה אחת, וה-fallback לפגישה שהסתיימה רץ רק
    כשלא הייתה אף פגישה עתידית — כלומר הכפתור פשוט לא הופיע.
    """
    from app.constants import BookingStatus, LeadStatus
    from app.models.booking import Booking
    from app.models.lead import Lead
    from app.services import booking as booking_service

    lead = await _mk_lead(db)
    future_start, future_end = _next_workday_slot()
    await booking_service.create_booking_request(
        db, token=lead.booking_token, slot_start=future_start,
        slot_end=future_end, contact_phone="052-1234567",
    )
    await db.execute(
        Lead.__table__.update()
        .where(Lead.id == lead.id)
        .values(status=LeadStatus.BOOKED.value)
    )

    just_ended = datetime.now(timezone.utc) - timedelta(hours=2)
    db.add(
        Booking(
            lead_id=lead.id,
            requested_slot_start=just_ended,
            requested_slot_end=just_ended + timedelta(hours=1),
            status=BookingStatus.APPROVED.value,
        )
    )
    await db.flush()

    rows = await booking_service.get_bookings_for_lead(db, lead.id)
    assert len(rows) == 2
    # ממוין בסדר עולה — שהסתיימה קודם, העתידית אחריה.
    assert rows[0].requested_slot_start < rows[1].requested_slot_start
    assert rows[0].requested_slot_end < datetime.now(timezone.utc)


# ===================== מסלול חלופי: פגישה בלי אירוע ביומן =====================


async def test_booking_without_calendar_is_marked_as_such(db):
    """פגישה שנקבעה כשהיומן לא מחובר — מסומנת, לא שקטה.

    זה המסלול שרץ בפרודקשן כשנועה עדיין לא חיברה יומן: הפגישה נשמרת,
    הלקוח רואה "הפגישה נקבעה", ונועה — שעובדת מהיומן — לא יודעת שיש
    לה פגישה. הדגל `calendar_event_created` הוא מה שמאפשר לדעת, גם
    ב-UI וגם בכל ניתוח downstream.
    """
    from sqlalchemy import select

    from app.constants import ActivityType
    from app.models.activity import Activity
    from app.models.booking import Booking
    from app.services.booking import create_booking_request

    lead = await _mk_lead(db, name="ללא יומן")
    start, end = _next_workday_slot(1)
    await create_booking_request(
        db, lead.booking_token, start, end, contact_phone="052-1234567"
    )

    booking = (
        await db.execute(select(Booking).where(Booking.lead_id == lead.id))
    ).scalar_one()
    # אין credentials בטסטים → אין אירוע, וגם אין יומן לשמור.
    assert booking.google_calendar_event_id is None
    assert booking.google_calendar_id is None

    activity = (
        await db.execute(
            select(Activity).where(
                Activity.lead_id == lead.id,
                Activity.type == ActivityType.MEETING_APPROVED.value,
            )
        )
    ).scalar_one()
    assert activity.activity_metadata["calendar_event_created"] is False
    # הדגל נוסף ולא החליף — שאר הצרכנים ממשיכים לעבוד.
    assert activity.activity_metadata["auto_confirmed"] is True
    assert activity.activity_metadata["booking_id"] == str(booking.id)


async def test_whitespace_note_does_not_reach_the_booking_row(db):
    """הנרמול בגבול מגיע עד ה-DB, לא רק עד התיאור."""
    from sqlalchemy import select

    from app.models.booking import Booking
    from app.schemas.booking_page import CreateBookingRequest
    from app.services.booking import create_booking_request

    lead = await _mk_lead(db, name="הערה ריקה")
    start, end = _next_workday_slot(1)
    payload = CreateBookingRequest(
        slot_start=start,
        slot_end=end,
        contact_phone="052-1234567",
        notes="   ",
    )
    await create_booking_request(
        db,
        lead.booking_token,
        payload.slot_start,
        payload.slot_end,
        contact_phone=payload.contact_phone,
        notes=payload.notes,
    )

    booking = (
        await db.execute(select(Booking).where(Booking.lead_id == lead.id))
    ).scalar_one()
    assert booking.notes is None
