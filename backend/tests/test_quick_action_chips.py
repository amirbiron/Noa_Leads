"""בדיקות ל-apply_chip (Spec v2.1 §16.4) — בעיקר ה-fix "אין סיגה אחורה".

לפני: chip על ליד PROPOSAL_SENT/BOOKING_PENDING/BOOKED הוריד אותו ל-IN_PROGRESS
ואיבד מידע — הליד נעלם מ"הצעות פתוחות", Booking ממתינה הפכה ל-REJECTED בשקט,
event ביומן הפך יתום.
אחרי: חישוב `effective_status` — אם target מוקדם יותר מ-current ב-_STATUS_PROGRESSION,
שומרים את ה-current ומחילים רק את שאר ה-side effects (waiting_on, touchpoint,
followup task, AUTO_CLOSE). ה-Booking cascade מותנה ב-`effective_status` (לא
ב-target) — כך שאם נמנעת סיגה מ-BOOKING_PENDING, ה-booking לא נדחה.

integration: דורש Postgres. מדלגות אם אין DB.
"""

from datetime import datetime, timedelta, timezone

from app.constants import (
    BookingStatus,
    LeadStatus,
    SourceChannel,
    TaskStatus,
    TaskType,
    WaitingOn,
)
from app.models.booking import Booking
from app.models.lead import Lead
from app.models.quick_action_chip import QuickActionChip
from app.models.task import Task
from app.services import quick_action_chips as chip_service


async def _mk_lead(db, **kw) -> Lead:
    defaults = dict(
        full_name="ליד צ'יפ",
        source_channel=SourceChannel.MANUAL.value,
        status=LeadStatus.IN_PROGRESS.value,
        waiting_on=WaitingOn.CLIENT.value,
    )
    defaults.update(kw)
    lead = Lead(**defaults)
    db.add(lead)
    await db.flush()
    return lead


async def _mk_chip(db, **kw) -> QuickActionChip:
    """צ'יפ קנוני: target IN_PROGRESS (לפי §16.4), follow-up = followup 3d."""
    defaults = dict(
        label="צ'יפ בדיקה",
        target_status=LeadStatus.IN_PROGRESS.value,
        waiting_on=WaitingOn.NOAH.value,
        followup_task_type=TaskType.FOLLOWUP.value,
        auto_followup_days=3,
    )
    defaults.update(kw)
    chip = QuickActionChip(**defaults)
    db.add(chip)
    await db.flush()
    return chip


async def _mk_pending_booking(db, lead) -> Booking:
    """Booking PENDING_APPROVAL — מסמלץ בקשת תור פעילה. ה-slot נגזר מ-
    `lead.id` כדי לבדל בין ריצות (exclusion constraint `ck_bookings_no_overlap`
    הוא גלובלי על ה-טבלה, ופלאקיות ב-rollback של ה-fixture יכולה להשאיר
    bookings קודמים כשמריצים את אותו test כמה פעמים ברצף)."""
    now = datetime.now(timezone.utc)
    # offset במחרוזת השעות לפי 8 ספרות אחרונות של ה-UUID → טווח ~6 שנים, מבדל.
    offset_hours = lead.id.int % (24 * 365 * 6)
    start = now + timedelta(hours=offset_hours + 48)
    booking = Booking(
        lead_id=lead.id,
        requested_slot_start=start,
        requested_slot_end=start + timedelta(hours=1),
        status=BookingStatus.PENDING_APPROVAL.value,
    )
    db.add(booking)
    await db.flush()
    return booking


# ===== הכלל: סיגה נמנעת =====


async def test_chip_preserves_proposal_sent(db):
    """ליד PROPOSAL_SENT + chip target IN_PROGRESS: status נשאר PROPOSAL_SENT;
    waiting_on וה-task כן מתעדכנים; response.preserved_reason='proposal_sent'."""
    lead = await _mk_lead(db, status=LeadStatus.PROPOSAL_SENT.value)
    chip = await _mk_chip(db, label="מעוניין בשיחה")

    response = await chip_service.apply_chip(
        db, lead_id=lead.id, chip_id=chip.id, performed_by=None
    )
    await db.refresh(lead)

    assert lead.status == LeadStatus.PROPOSAL_SENT.value  # נשמר
    assert lead.waiting_on == WaitingOn.NOAH.value  # עודכן
    assert response.status_preserved is True
    assert response.preserved_reason == "proposal_sent"
    # task כן נוצר — chip = תיעוד שיחה גם בסטטוס מתקדם.
    tasks = (await db.execute(Task.__table__.select().where(Task.lead_id == lead.id))).all()
    assert any(t.type == TaskType.FOLLOWUP.value for t in tasks)


async def test_chip_preserves_booking_pending_and_keeps_booking(db):
    """ליד BOOKING_PENDING עם Booking PENDING_APPROVAL: status נשאר,
    הbooking *לא* נדחה (ה-cascade fix). preserved_reason='booking_pending'."""
    lead = await _mk_lead(db, status=LeadStatus.BOOKING_PENDING.value)
    booking = await _mk_pending_booking(db, lead)
    chip = await _mk_chip(db, label="אין מענה")

    response = await chip_service.apply_chip(
        db, lead_id=lead.id, chip_id=chip.id, performed_by=None
    )
    await db.refresh(lead)
    await db.refresh(booking)

    assert lead.status == LeadStatus.BOOKING_PENDING.value
    # ה-cascade הקודם היה משנה ל-REJECTED ומוסיף rejected_at — לא יותר.
    assert booking.status == BookingStatus.PENDING_APPROVAL.value
    assert booking.rejected_at is None
    assert response.status_preserved is True
    assert response.preserved_reason == "booking_pending"


async def test_chip_preserves_booked(db):
    """ליד BOOKED + chip: status נשאר. אין כאן Booking לבדוק כי chip ממילא
    לא נגע בו ב-BOOKED גם בקוד הקיים; הבדיקה היא לכלל ה-preserved_reason."""
    lead = await _mk_lead(db, status=LeadStatus.BOOKED.value)
    chip = await _mk_chip(db, label="לא רלוונטי כרגע")

    response = await chip_service.apply_chip(
        db, lead_id=lead.id, chip_id=chip.id, performed_by=None
    )
    await db.refresh(lead)

    assert lead.status == LeadStatus.BOOKED.value
    assert response.status_preserved is True
    assert response.preserved_reason == "booked"


# ===== ה-flow הרגיל (regression) =====


async def test_chip_normal_flow_in_progress_unchanged(db):
    """ליד IN_PROGRESS + chip target IN_PROGRESS: לא סיגה. status נשאר
    (זהה ל-target), status_preserved=False."""
    lead = await _mk_lead(db, status=LeadStatus.IN_PROGRESS.value)
    chip = await _mk_chip(db)

    response = await chip_service.apply_chip(
        db, lead_id=lead.id, chip_id=chip.id, performed_by=None
    )
    await db.refresh(lead)

    assert lead.status == LeadStatus.IN_PROGRESS.value
    assert lead.waiting_on == WaitingOn.NOAH.value
    assert response.status_preserved is False
    assert response.preserved_reason is None


async def test_chip_new_to_in_progress_is_promotion_not_regression(db):
    """ליד NEW + chip target IN_PROGRESS: זה קידום (NEW → IN_PROGRESS),
    לא סיגה. status מתעדכן ל-IN_PROGRESS, status_preserved=False."""
    lead = await _mk_lead(db, status=LeadStatus.NEW.value)
    chip = await _mk_chip(db)

    response = await chip_service.apply_chip(
        db, lead_id=lead.id, chip_id=chip.id, performed_by=None
    )
    await db.refresh(lead)

    assert lead.status == LeadStatus.IN_PROGRESS.value
    assert response.status_preserved is False


# ===== sanity: ליד עם warm_followup פתוח גם נסגר (touchpoint) =====


async def test_chip_in_preserved_status_still_closes_warm_followup(db):
    """גם כשנמנעת סיגה, ה-touchpoint side-effects רצים. warm_followup פתוח
    נסגר (AUTO_CLOSE_TASK_TYPES) — לא רק status נשמר אלא ה-chip מבצע את
    תפקידו ככלי תיעוד שיחה."""
    lead = await _mk_lead(db, status=LeadStatus.PROPOSAL_SENT.value)
    warm = Task(
        lead_id=lead.id,
        type=TaskType.WARM_FOLLOWUP.value,
        status=TaskStatus.OPEN.value,
        due_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    db.add(warm)
    await db.flush()

    chip = await _mk_chip(db)
    await chip_service.apply_chip(
        db, lead_id=lead.id, chip_id=chip.id, performed_by=None
    )
    await db.refresh(warm)

    assert warm.status == TaskStatus.DONE.value
