"""
check_stuck_proposals — רץ כל שעה.

מאתר הצעות פתוחות שעברו את ה-threshold מ-FollowupRule (`proposal_followup`)
ואין להן משימת פולואפ פתוחה, ויוצר עבורן proposal_followup task ליום
העבודה הבא.

הסמנטיקה: ה-rule מגדיר *מתי להתעורר* (selection threshold). ה-due_at של
ה-task נקבע ל-`next_working_day_start(now)` — בוקר יום עבודה הבא — לא
נגזר מהכלל. זה כך כי ה-cron עצמו רץ כל שעה: ברגע שה-threshold עבר,
ה-task צריך לקפוץ ב-/today ביום העבודה הבא, לא להיבחר שוב interval
שלם קדימה.
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import LeadStatus, TaskStatus, TaskType
from app.db.session import AsyncSessionLocal
from app.models.lead import Lead
from app.models.task import Task
from app.services.followup_rules import get_rule_interval_seconds
from app.utils.work_hours import next_working_day_start
from jobs._runner import run_job

logger = logging.getLogger("jobs.check_stuck_proposals")


# fallback ל-selection threshold (3 ימים, §17.1) אם FollowupRule
# לא seeded. הערך ניתן לעריכה ב-UI הגדרות (proposal_followup rule).
STUCK_THRESHOLD_DAYS = 3


async def _stuck_proposal_leads(
    db: AsyncSession, threshold_seconds: int
) -> list[Lead]:
    """
    שולף PROPOSAL_SENT שעברו threshold_seconds מאז שליחת ההצעה,
    ואין להם משימה פתוחה.

    משתמש ב-COALESCE(proposal_sent_at, last_outbound_at) — לידים שנוצרו
    לפני migration 0002 לא יקבלו אף פעם proposal_sent_at, ובלי הfallback
    הם נשארים שקופים לעד מבחינת ה-cron הזה ו-dashboard סנכרוני זה עם זה.
    """
    threshold = datetime.now(timezone.utc) - timedelta(seconds=threshold_seconds)
    effective_sent_at = func.coalesce(Lead.proposal_sent_at, Lead.last_outbound_at)

    # subquery של "יש task פתוח לליד הזה"
    has_open_task = (
        select(Task.id)
        .where(
            Task.lead_id == Lead.id,
            Task.status.in_([TaskStatus.OPEN.value, TaskStatus.SNOOZED.value]),
        )
        .exists()
    )

    stmt = (
        select(Lead)
        .where(
            Lead.status == LeadStatus.PROPOSAL_SENT.value,
            effective_sent_at.is_not(None),
            effective_sent_at <= threshold,
            ~has_open_task,
        )
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def check_stuck_proposals() -> None:
    due_at_utc = next_working_day_start(datetime.now(timezone.utc)).astimezone(
        timezone.utc
    )

    async with AsyncSessionLocal() as db:
        from app.services.tasks import sync_lead_next_action_cache

        # live lookup לselection threshold. ה-due_at הנקבע ל-task הוא
        # עדיין next_working_day_start — סמנטיקה זו לא משתנה (ראה docstring).
        threshold_sec = await get_rule_interval_seconds(
            db,
            TaskType.PROPOSAL_FOLLOWUP.value,
            default_seconds=STUCK_THRESHOLD_DAYS * 86400,
        )

        leads = await _stuck_proposal_leads(db, threshold_sec)
        for lead in leads:
            task = Task(
                lead_id=lead.id,
                type=TaskType.PROPOSAL_FOLLOWUP.value,
                assigned_to=lead.owner_id,
                due_at=due_at_utc,
                status=TaskStatus.OPEN.value,
                origin_rule="check_stuck_proposals",
            )
            db.add(task)
        await db.flush()  # נדרש כדי שה-sync יראה את ה-tasks החדשים

        # סנכרון cache בליד: בלי זה lead.next_action_* נשאר NULL/ישן,
        # ו-derive_state_color/sorting בדשבורד לא יראו את ה-task החדש.
        for lead in leads:
            await sync_lead_next_action_cache(db, lead.id)

        await db.commit()

    logger.info("Created %d proposal followup tasks", len(leads))


if __name__ == "__main__":
    run_job("check_stuck_proposals", check_stuck_proposals)
