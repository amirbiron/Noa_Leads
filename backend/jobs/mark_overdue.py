"""mark_overdue_leads — רץ כל 15 דקות.

המנגנון (§17.1 — תזכורת חוזרת):
1. שולפים כל task פעיל (OPEN/SNOOZED) שעבר את due_at, של ליד פתוח, surfaceable.
2. לכל task — lookup live ב-FollowupRule לפי task.type:
   - אם אין rule, או repeat_count <= 1: התנהגות "התראה אחת" — מסמנים
     `lead.needs_attention=True` אם עוד לא, ומשאירים את ה-task כמו שהוא.
   - אם current_iteration >= repeat_count: כל החזרות נגמרו. מסמנים
     needs_attention, אבל לא מעלים iteration ולא משנים due_at (anchor
     ל-7d stuck countdown).
   - אחרת: זה moment של אלרט. מעלים iteration ב-1, ואם עוד יש חזרות
     קובעים `due_at = now + interval`. אם זו האחרונה — משאירים due_at=now.
3. מסנכרנים את ה-cache `Lead.next_action_due_at` לכל ליד מושפע.

idempotency: task עם iteration<repeat_count + due_at בעתיד → SELECT
לא יחזיר (due_at > now). task עם iteration>=repeat_count → SELECT כן
יחזיר (due_at <= now), אבל הלולאה מדלגת מבלי לשנות.
"""

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select, update

from app.constants import CLOSED_LEAD_STATUSES, TaskStatus
from app.db.session import AsyncSessionLocal
from app.models.followup_rule import FollowupRule
from app.models.lead import Lead
from app.models.task import Task
from app.services.followup_rules import rule_interval_seconds
from app.services.tasks import surfaceable_task_condition, sync_lead_next_action_cache
from jobs._runner import run_job

logger = logging.getLogger("jobs.mark_overdue")


async def process_overdue_tasks(
    db, now: datetime
) -> tuple[int, int, int]:
    """הלוגיקה של mark_overdue — הופרדה לפונקציה כדי שניתן יהיה לבדוק
    עם conftest db (rollback-based). הקוראת (cron) אחראית על commit.

    מחזירה: (tasks_seen, alerts_fired, leads_affected).
    """
    closed = [s.value for s in CLOSED_LEAD_STATUSES]
    fired = 0

    stmt = (
        select(Task)
        .join(Lead, Task.lead_id == Lead.id)
        .where(
            Task.due_at <= now,
            Task.status.in_(
                [TaskStatus.OPEN.value, TaskStatus.SNOOZED.value]
            ),
            Lead.status.notin_(closed),
            surfaceable_task_condition(),
        )
    )
    tasks = list((await db.execute(stmt)).scalars().all())

    # rules cache בתוך הסשן — SQLAlchemy identity-map ימנע lookups כפולים,
    # אבל explicit dict זול ויפה לקריאה.
    rules_cache: dict[str, FollowupRule | None] = {}

    async def _get_rule(task_type: str) -> FollowupRule | None:
        if task_type not in rules_cache:
            rules_cache[task_type] = await db.get(FollowupRule, task_type)
        return rules_cache[task_type]

    affected_lead_ids: set[UUID] = set()

    for task in tasks:
        affected_lead_ids.add(task.lead_id)
        rule = await _get_rule(task.type)

        # אין rule, או רק התראה אחת — sticky needs_attention יוטל בהמשך.
        if rule is None or rule.repeat_count <= 1:
            continue

        # כל החזרות נגמרו — anchor ל-stuck נשאר, לא מעלים יותר.
        if task.current_iteration >= rule.repeat_count:
            continue

        # זה moment של אלרט.
        task.current_iteration += 1
        if task.current_iteration < rule.repeat_count:
            # יש עוד חזרה — נתזמן אותה.
            interval_sec = rule_interval_seconds(
                rule.repeat_interval_value, rule.repeat_interval_unit
            )
            task.due_at = now + timedelta(seconds=interval_sec)
        # else: זו האחרונה. due_at נשאר ב-now → 7d stuck countdown יפעל ממנו.
        fired += 1

    # סימון leads — race-safe (closed leads מוחרגים אטומית ב-WHERE).
    await _mark_leads_needs_attention(db, affected_lead_ids)

    # flush לפני sync cache — sync_lead_next_action_cache קורא את
    # task.due_at הנוכחי, וצריך לראות את העדכון.
    await db.flush()

    for lead_id in affected_lead_ids:
        await sync_lead_next_action_cache(db, lead_id)

    return len(tasks), fired, len(affected_lead_ids)


async def _mark_leads_needs_attention(db, lead_ids: set[UUID]) -> None:
    """Bulk UPDATE — needs_attention=True ללידים שעבר due_at של ה-tasks
    שלהם.

    Race guard: ה-WHERE כולל `status NOT IN (closed)` כדי שליד שנסגר בין
    SELECT ה-tasks ל-UPDATE הזה (close_lead שרץ במקביל ב-route אחר) לא
    יקבל את הדגל. ה-SELECT של mark_overdue מסנן סגורים, אבל
    `affected_lead_ids` עובר stale ל-UPDATE — בלי ה-guard, ליד שנסגר
    במקביל היה מקבל needs_attention=True (סותר §6.5: ליד סגור לעולם לא
    live).

    `needs_attention.is_(False)` נשאר — לא מבמפים updated_at של רשומות
    שכבר מסומנות.

    תואם כלל 2 (TOCTOU אטומי) וכלל 8 (race scenarios) ב-CLAUDE.md.
    """
    if not lead_ids:
        return
    closed = [s.value for s in CLOSED_LEAD_STATUSES]
    await db.execute(
        update(Lead)
        .where(
            Lead.id.in_(lead_ids),
            Lead.needs_attention.is_(False),
            Lead.status.notin_(closed),
        )
        .values(needs_attention=True, updated_at=func.now())
    )


async def mark_overdue() -> None:
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as db:
        seen, fired, leads = await process_overdue_tasks(db, now)
        await db.commit()
    logger.info(
        "Processed %d overdue tasks (%d new alerts fired) for %d leads",
        seen,
        fired,
        leads,
    )


if __name__ == "__main__":
    run_job("mark_overdue_leads", mark_overdue)
