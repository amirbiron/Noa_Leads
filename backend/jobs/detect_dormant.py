"""
detect_dormant_leads — רץ פעם ביום ב-03:00.

מסמן dormant_flag=True לכל ליד פתוח שלא הייתה ממנו אינטראקציה ב-60+ ימים,
ויוצר אוטומטית משימת dormant_check כדי שהליד יופיע ב-/today (Spec §17.1 +
F-08).

idempotent: רק לידים שעוברים *עכשיו* מ-dormant_flag=False ל-True מקבלים
טיפול. אם chip "לא רלוונטי כרגע" כבר יצר dormant_check task — לא מייצרים
שני.
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import CLOSED_LEAD_STATUSES, TaskStatus, TaskType
from app.db.session import AsyncSessionLocal
from app.models.lead import Lead
from app.models.task import Task
from jobs._runner import run_job

logger = logging.getLogger("jobs.detect_dormant")


DORMANT_THRESHOLD_DAYS = 60


async def _has_any_open_task(db: AsyncSession, lead_id) -> bool:
    """
    True אם יש כבר open/snoozed task כלשהו לליד. בודק כל type, לא רק
    dormant_check — אחרת ליד עם FIRST_RESPONSE/RETRY_CALL תקוע מ-60+
    ימים היה מצטבר עם dormant_check חדש = שני reminders למצב אחד.
    עקבי עם check_warm_followups שמדלג על כל ליד עם task פתוח.
    """
    result = await db.execute(
        select(Task.id).where(
            Task.lead_id == lead_id,
            Task.status.in_(
                [TaskStatus.OPEN.value, TaskStatus.SNOOZED.value]
            ),
        ).limit(1)
    )
    return result.scalar_one_or_none() is not None


async def detect_dormant() -> None:
    threshold = datetime.now(timezone.utc) - timedelta(days=DORMANT_THRESHOLD_DAYS)
    now_utc = datetime.now(timezone.utc)
    closed = [s.value for s in CLOSED_LEAD_STATUSES]

    async with AsyncSessionLocal() as db:
        stmt = (
            update(Lead)
            .where(
                Lead.status.notin_(closed),
                Lead.dormant_flag.is_(False),
                Lead.created_at <= threshold,
                # ליד נחשב רדום רק אם אין אינטראקציה בשני הכיוונים.
                # אם נועה שלחה outbound לאחרונה (גם בלי תגובה) זה לא רדום —
                # היא בעיצומו של ניסיון יצירת קשר.
                or_(
                    Lead.last_inbound_at.is_(None),
                    Lead.last_inbound_at <= threshold,
                ),
                or_(
                    Lead.last_outbound_at.is_(None),
                    Lead.last_outbound_at <= threshold,
                ),
            )
            .values(dormant_flag=True, updated_at=func.now())
            .returning(Lead.id)
        )
        result = await db.execute(stmt)
        newly_dormant_ids = list(result.scalars().all())

        # יצירת dormant_check task לכל ליד חדש שנדלק, idempotent כנגד
        # *כל* task פתוח (chip "לא רלוונטי כרגע" שיצר dormant_check, או
        # FIRST_RESPONSE/RETRY_CALL ישנים שנשארו תקועים). ה-task נוצר עם
        # due_at=now כי הליד כבר 60 יום רדום.
        from app.services.tasks import sync_lead_next_action_cache

        tasks_created = 0
        for lead_id in newly_dormant_ids:
            if await _has_any_open_task(db, lead_id):
                continue
            task = Task(
                lead_id=lead_id,
                type=TaskType.DORMANT_CHECK.value,
                status=TaskStatus.OPEN.value,
                due_at=now_utc,
                origin_rule="auto_detect_dormant",
            )
            db.add(task)
            tasks_created += 1

        if tasks_created > 0:
            await db.flush()  # נדרש כדי שה-sync יראה את ה-tasks החדשים
            for lead_id in newly_dormant_ids:
                await sync_lead_next_action_cache(db, lead_id)

        await db.commit()

    logger.info(
        "Marked %d leads as dormant, created %d dormant_check tasks",
        len(newly_dormant_ids),
        tasks_created,
    )


if __name__ == "__main__":
    run_job("detect_dormant_leads", detect_dormant)
