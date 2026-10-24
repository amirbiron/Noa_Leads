"""בדיקות ל-inbound chokepoint (`register_inbound` + `close_touchpoint_tasks`).

השורש שתוקן: מסלולי inbound לא-שקולים — inbound דרך perform_action סגר
warm_followup ("הלקוח לא חזר"), אבל inbound דרך UPDATE ישיר (booking) דילג.
הצ'וקפוינט מאחד את הלוגיקה: כל inbound על ליד קיים סוגר את ה-tasks
מ-AUTO_CLOSE_TASK_TYPES + מבצע את כל ה-side-effects.

integration: דורש Postgres. מדלגות אם אין DB (fixture `db`).
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.constants import (
    ActivityType,
    LeadStatus,
    SourceChannel,
    TaskStatus,
    TaskType,
    WaitingOn,
)
from app.core.exceptions import InvalidStateTransitionError
from app.models.activity import Activity
from app.models.lead import Lead
from app.models.task import Task
from app.schemas.lead import LeadCreate
from app.services import lead_actions
from app.services.leads import create_lead

_NOW = datetime.now(timezone.utc)


async def _mk_lead(db, **kw) -> Lead:
    defaults = dict(
        full_name="ליד בדיקה",
        source_channel=SourceChannel.MANUAL.value,
        status=LeadStatus.IN_PROGRESS.value,
        waiting_on=WaitingOn.CLIENT.value,
    )
    defaults.update(kw)
    lead = Lead(**defaults)
    db.add(lead)
    await db.flush()
    return lead


async def _mk_warm_followup(db, lead, **kw) -> Task:
    task = Task(
        lead_id=lead.id,
        type=TaskType.WARM_FOLLOWUP.value,
        status=TaskStatus.OPEN.value,
        due_at=_NOW - timedelta(hours=1),
        **kw,
    )
    db.add(task)
    await db.flush()
    return task


async def test_register_inbound_closes_warm_followup(db):
    """ליד IN_PROGRESS עם warm_followup פתוח → register_inbound → ה-task
    נסגר + כל ה-side-effects (last_inbound_at / reply_boost / waiting_on=NOAH)."""
    lead = await _mk_lead(db, waiting_on=WaitingOn.CLIENT.value)
    task = await _mk_warm_followup(db, lead)

    await lead_actions.register_inbound(db, lead.id, content="הלקוח חזר")
    await db.refresh(lead)
    await db.refresh(task)

    assert task.status == TaskStatus.DONE.value
    assert task.completed_at is not None
    assert lead.last_inbound_at is not None
    assert lead.reply_boost_until is not None
    assert lead.waiting_on == WaitingOn.NOAH.value
    assert lead.last_activity_type == "inbound_message"


async def test_register_inbound_logs_activity(db):
    """register_inbound רושם INBOUND_MESSAGE_LOGGED activity עם ה-content."""
    lead = await _mk_lead(db)

    await lead_actions.register_inbound(db, lead.id, content="שלום, אשמח לפרטים")
    result = await db.execute(
        Activity.__table__.select().where(Activity.lead_id == lead.id)
    )
    types = [row.type for row in result]
    assert ActivityType.INBOUND_MESSAGE_LOGGED.value in types


async def test_register_inbound_auto_progresses_new(db):
    """ליד NEW → register_inbound → IN_PROGRESS (auto-progress) + status_changed
    activity ב-timeline."""
    lead = await _mk_lead(db, status=LeadStatus.NEW.value)

    await lead_actions.register_inbound(db, lead.id)
    await db.refresh(lead)

    assert lead.status == LeadStatus.IN_PROGRESS.value
    result = await db.execute(
        Activity.__table__.select().where(Activity.lead_id == lead.id)
    )
    types = [row.type for row in result]
    assert "status_changed" in types
    assert ActivityType.INBOUND_MESSAGE_LOGGED.value in types


async def test_register_inbound_rejects_closed_lead(db):
    """inbound על ליד סגור (WON) → InvalidStateTransitionError. אי אפשר
    'להחיות' ליד סגור דרך inbound."""
    lead = await _mk_lead(db, status=LeadStatus.WON.value)
    with pytest.raises(InvalidStateTransitionError):
        await lead_actions.register_inbound(db, lead.id)


async def test_close_touchpoint_tasks_closes_warm_followup(db):
    """Layer 1 ישירות: close_touchpoint_tasks סוגר warm_followup + מסנכרן
    cache. זה ה-shared layer ש-booking.create_booking_request קורא לו
    (ה-bypass שתוקן — בקשת תור סוגרת warm_followup)."""
    lead = await _mk_lead(db)
    task = await _mk_warm_followup(db, lead)

    await lead_actions.close_touchpoint_tasks(db, lead.id, _NOW)
    await db.refresh(task)
    await db.refresh(lead)

    assert task.status == TaskStatus.DONE.value
    # cache סונכרן — אין יותר task פתוח, next_action_due_at התאפס.
    assert lead.next_action_due_at is None


async def test_perform_action_inbound_still_closes_warm(db):
    """regression: המסלול הקיים (UI ידני, perform_action 'log_inbound_message')
    עדיין סוגר warm_followup אחרי ה-delegation ל-register_inbound."""
    lead = await _mk_lead(db)
    task = await _mk_warm_followup(db, lead)

    await lead_actions.perform_action(
        db,
        lead.id,
        "log_inbound_message",
        current_user_id=None,
        content="תיעוד ידני",
    )
    # perform_action עושה commit פנימי — re-fetch.
    refetched = await db.get(Task, task.id)
    await db.refresh(refetched)
    assert refetched.status == TaskStatus.DONE.value


async def test_create_lead_set_last_inbound_true(db):
    """create_lead(set_last_inbound=True) → last_inbound_at נקבע (קטגוריה B:
    ליד שנוצר מ-inbound של הלקוח, whatsapp/gmail)."""
    payload = LeadCreate(
        full_name="ליד מ-whatsapp",
        source_channel=SourceChannel.WHATSAPP,
    )
    lead = await create_lead(
        db,
        payload,
        current_user_id=None,
        create_first_response_task=False,
        commit=False,
        set_last_inbound=True,
    )
    await db.refresh(lead)
    assert lead.last_inbound_at is not None


async def test_create_lead_default_no_last_inbound(db):
    """ברירת מחדל set_last_inbound=False → last_inbound_at NULL (ליד רגיל
    שנוצר ידנית / מטופס, לא מ-inbound ישיר)."""
    payload = LeadCreate(
        full_name="ליד ידני",
        source_channel=SourceChannel.MANUAL,
    )
    lead = await create_lead(
        db,
        payload,
        current_user_id=None,
        create_first_response_task=False,
        commit=False,
    )
    await db.refresh(lead)
    assert lead.last_inbound_at is None
