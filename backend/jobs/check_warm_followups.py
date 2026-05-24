"""
check_warm_followups — רץ כל שעה (Spec §17.1 + §17.2, F-08).

מאתר לידים IN_PROGRESS שעבר 48 שעות מאז ה-outbound האחרון של נועה,
והלקוח לא הגיב — ויוצר עבורם משימת warm_followup. due_at = last_outbound_at
+ 48h, מותאם לשעות עבודה.

idempotency: יוצר רק לידים בלי שום task פתוח. זה מכבד:
- chip שכבר יצר followup task ("מעוניין בשיחה" → followup 2d).
- check_stuck_proposals שיצר proposal_followup.
- detect_dormant שיצר dormant_check.
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import LeadStatus, TaskStatus, TaskType
from app.db.session import AsyncSessionLocal
from app.models.lead import Lead
from app.models.task import Task
from app.utils.work_hours import is_working_time, next_working_day_start
from jobs._runner import run_job

logger = logging.getLogger("jobs.check_warm_followups")


# Spec §17.2: due = last_outbound_at + 48h. ה-Spec §17.1 נותן טווח 48-72h
# — אנחנו לוקחים 48 כסף יחיד; אם נועה תרצה לעדכן בעתיד, להוסיף שדה
# לשולחן שירותים או config.
WARM_FOLLOWUP_DELAY_HOURS = 48


async def _warm_followup_candidates(db: AsyncSession) -> list[Lead]:
    """
    שולף לידים IN_PROGRESS שעוברים את התנאים לcreate warm_followup:
    - last_outbound_at <= now - 48h (כלומר שלחנו ועברו 48h+).
    - אין inbound חדש מאז (לקוח לא ענה).
    - אין task פתוח בכלל (מכבד chip-driven tasks).
    - אין warm_followup task — *בכל סטטוס* — שנוצר אחרי ה-outbound הנוכחי.
      כך, אם נועה השלימה warm_followup ואין outbound חדש, לא נוצר עוד אחד.
      ברגע שיש outbound חדש (Noah שלחה משהו), last_outbound_at קופץ קדימה
      וה-warm_followup הישן "נשאר מאחור" — מותר ליצור חדש.
    """
    threshold = datetime.now(timezone.utc) - timedelta(
        hours=WARM_FOLLOWUP_DELAY_HOURS
    )

    has_open_task = (
        select(Task.id)
        .where(
            Task.lead_id == Lead.id,
            Task.status.in_(
                [TaskStatus.OPEN.value, TaskStatus.SNOOZED.value]
            ),
        )
        .exists()
    )
    # מונע הוצאת hourly של warm_followup ל-loop: ברגע שנוצר warm_followup
    # ל-outbound הזה (פתוח/הושלם/בוטל), לא יוצרים עוד עד שיהיה outbound חדש.
    has_warm_followup_after_outbound = (
        select(Task.id)
        .where(
            Task.lead_id == Lead.id,
            Task.type == TaskType.WARM_FOLLOWUP.value,
            Task.created_at >= Lead.last_outbound_at,
        )
        .exists()
    )

    stmt = select(Lead).where(
        Lead.status == LeadStatus.IN_PROGRESS.value,
        Lead.last_outbound_at.is_not(None),
        Lead.last_outbound_at <= threshold,
        # "לקוח לא ענה": אין inbound כלל, או שה-inbound לפני ה-outbound.
        or_(
            Lead.last_inbound_at.is_(None),
            Lead.last_inbound_at < Lead.last_outbound_at,
        ),
        ~has_open_task,
        ~has_warm_followup_after_outbound,
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


def _calc_due_at(last_outbound_at: datetime) -> datetime:
    """
    due_at = last_outbound_at + 48h, נדחה לתחילת יום עבודה אם נופל מחוץ.
    next_working_day_start מחזיר ISRAEL_TZ — ממירים ל-UTC לעקביות עם
    שאר ה-tasks (מיון/השוואות ב-postgres מצפים tz אחיד).
    """
    due = last_outbound_at + timedelta(hours=WARM_FOLLOWUP_DELAY_HOURS)
    if not is_working_time(due):
        due = next_working_day_start(due).astimezone(timezone.utc)
    return due


async def check_warm_followups() -> None:
    async with AsyncSessionLocal() as db:
        from app.services.tasks import sync_lead_next_action_cache

        leads = await _warm_followup_candidates(db)
        for lead in leads:
            task = Task(
                lead_id=lead.id,
                type=TaskType.WARM_FOLLOWUP.value,
                assigned_to=lead.owner_id,
                due_at=_calc_due_at(lead.last_outbound_at),
                status=TaskStatus.OPEN.value,
                origin_rule="auto_warm_followup",
            )
            db.add(task)
        if leads:
            await db.flush()  # נדרש כדי שה-sync יראה את ה-tasks החדשים
            for lead in leads:
                await sync_lead_next_action_cache(db, lead.id)

        await db.commit()

    logger.info("Created %d warm_followup tasks", len(leads))


if __name__ == "__main__":
    run_job("check_warm_followups", check_warm_followups)
