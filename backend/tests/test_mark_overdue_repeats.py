"""בדיקות ללוגיקת התזכורת החוזרת ב-mark_overdue cron (§17.1).

קוראות ל-`process_overdue_tasks(db, now)` במקום `mark_overdue()` כדי
לעבוד עם conftest db (rollback-based) ולא session נפרד שדורש cleanup.

integration: דורש Postgres (followup_rules seeded ב-migration 0029).
"""

from datetime import datetime, timedelta, timezone

from app.constants import LeadStatus, SourceChannel, TaskStatus, TaskType
from app.models.followup_rule import FollowupRule
from app.models.lead import Lead
from app.models.task import Task
from jobs.mark_overdue import process_overdue_tasks


async def _mk_lead(db, **kw) -> Lead:
    defaults = dict(
        full_name="ליד בדיקה",
        source_channel=SourceChannel.MANUAL.value,
        status=LeadStatus.IN_PROGRESS.value,
        waiting_on="NOAH",
    )
    defaults.update(kw)
    lead = Lead(**defaults)
    db.add(lead)
    await db.flush()
    return lead


async def _mk_task(db, lead, due_at, type_=TaskType.FIRST_RESPONSE.value, **kw):
    task = Task(
        lead_id=lead.id,
        type=type_,
        status=TaskStatus.OPEN.value,
        due_at=due_at,
        **kw,
    )
    db.add(task)
    await db.flush()
    return task


async def _set_rule(db, rule_key, repeat_count, repeat_interval_value=24, repeat_interval_unit="hours"):
    """משנה rule קיים (seeded ב-migration). conftest rollback מנקה."""
    rule = await db.get(FollowupRule, rule_key)
    assert rule is not None, f"rule {rule_key} לא seeded"
    rule.repeat_count = repeat_count
    rule.repeat_interval_value = repeat_interval_value
    rule.repeat_interval_unit = repeat_interval_unit
    await db.flush()


async def test_first_alert_increments_iteration_and_schedules_next(db):
    """rule עם repeat_count=3 + repeat_interval=24h, iteration=0:
    cron מעלה ל-1 וקובע due_at = now+24h."""
    await _set_rule(db, TaskType.FIRST_RESPONSE.value, repeat_count=3,
                    repeat_interval_value=24, repeat_interval_unit="hours")
    now = datetime.now(timezone.utc)
    lead = await _mk_lead(db)
    task = await _mk_task(db, lead, due_at=now - timedelta(hours=1))
    assert task.current_iteration == 0

    seen, fired, leads = await process_overdue_tasks(db, now)
    await db.refresh(task)

    assert seen == 1
    assert fired == 1
    assert leads == 1
    assert task.current_iteration == 1
    # due_at מקודם ל-now+24h (±5 שניות).
    assert abs((task.due_at - (now + timedelta(hours=24))).total_seconds()) < 5


async def test_last_repeat_leaves_due_at_at_now(db):
    """repeat_count=2, iteration=1 (החזרה האחרונה): cron מעלה ל-2 ולא
    מתזמן עוד (due_at נשאר ב-now → anchor ל-7d stuck)."""
    await _set_rule(db, TaskType.FIRST_RESPONSE.value, repeat_count=2,
                    repeat_interval_value=12, repeat_interval_unit="hours")
    now = datetime.now(timezone.utc)
    lead = await _mk_lead(db)
    task = await _mk_task(
        db, lead, due_at=now - timedelta(minutes=1), current_iteration=1
    )

    seen, fired, _ = await process_overdue_tasks(db, now)
    await db.refresh(task)

    assert fired == 1
    assert task.current_iteration == 2
    # due_at לא קודם — נשאר בעבר הקרוב (now ± 1min).
    assert task.due_at <= now


async def test_no_iteration_beyond_repeat_count(db):
    """iteration כבר שווה ל-repeat_count: cron לא מעלה יותר, due_at לא משתנה.
    הליד עדיין נסמן needs_attention (לא מסתיר מ-pending)."""
    await _set_rule(db, TaskType.FIRST_RESPONSE.value, repeat_count=2)
    now = datetime.now(timezone.utc)
    lead = await _mk_lead(db)
    original_due = now - timedelta(days=2)
    task = await _mk_task(
        db, lead, due_at=original_due, current_iteration=2
    )

    seen, fired, _ = await process_overdue_tasks(db, now)
    await db.refresh(task)

    assert seen == 1  # ה-task נראה...
    assert fired == 0  # ...אבל לא נורה אלרט חדש.
    assert task.current_iteration == 2
    assert task.due_at == original_due  # לא השתנה


async def test_no_rule_falls_back_to_single_alert(db):
    """task מ-type שאין לו rule (FOLLOWUP גנרי): cron מסמן needs_attention,
    iteration ו-due_at לא משתנים."""
    now = datetime.now(timezone.utc)
    lead = await _mk_lead(db)
    original_due = now - timedelta(hours=1)
    task = await _mk_task(
        db, lead, due_at=original_due, type_=TaskType.FOLLOWUP.value
    )

    seen, fired, _ = await process_overdue_tasks(db, now)
    await db.refresh(task)
    await db.refresh(lead)

    assert seen == 1
    assert fired == 0  # אין rule = לא "אלרט חדש"
    assert task.current_iteration == 0
    assert task.due_at == original_due
    assert lead.needs_attention is True


async def test_touchpoint_cancels_repeats(db):
    """task שהוגדר ל-repeats אבל סטטוס DONE (touchpoint): cron מסנן
    אותו, אין increment."""
    await _set_rule(db, TaskType.FIRST_RESPONSE.value, repeat_count=3)
    now = datetime.now(timezone.utc)
    lead = await _mk_lead(db)
    task = await _mk_task(db, lead, due_at=now - timedelta(hours=1))
    # touchpoint סוגר את ה-task.
    task.status = TaskStatus.DONE.value
    await db.flush()

    seen, fired, leads = await process_overdue_tasks(db, now)
    await db.refresh(task)

    assert seen == 0  # task DONE לא ב-SELECT
    assert fired == 0
    assert leads == 0
    assert task.current_iteration == 0


async def test_sync_cache_after_repeat(db):
    """אחרי שה-cron מעלה iteration ומתזמן due_at חדש:
    Lead.next_action_due_at מסתנכרן ל-due_at החדש."""
    await _set_rule(db, TaskType.FIRST_RESPONSE.value, repeat_count=2,
                    repeat_interval_value=6, repeat_interval_unit="hours")
    now = datetime.now(timezone.utc)
    lead = await _mk_lead(db)
    task = await _mk_task(db, lead, due_at=now - timedelta(hours=1))

    await process_overdue_tasks(db, now)
    await db.refresh(task)
    await db.refresh(lead)

    # next_action_due_at של הליד = due_at החדש של ה-task (= now+6h).
    assert lead.next_action_due_at is not None
    expected = now + timedelta(hours=6)
    assert abs((lead.next_action_due_at - expected).total_seconds()) < 5
