"""
mark_overdue_leads — רץ כל 15 דקות.

מסמן needs_attention=True לכל ליד פתוח שעבר את next_action_due_at.
ה-UPDATE אטומי ומסונן ל-leads שעדיין לא סומנו, כדי לא לכתוב שוב ושוב
ולטרגד את updated_at של רשומות שלא השתנו (כלל 2 ב-CLAUDE.md).
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import func, update

from app.constants import CLOSED_LEAD_STATUSES
from app.db.session import AsyncSessionLocal
from app.models.lead import Lead
from jobs._runner import run_job

logger = logging.getLogger("jobs.mark_overdue")


async def mark_overdue() -> None:
    now = datetime.now(timezone.utc)
    closed = [s.value for s in CLOSED_LEAD_STATUSES]

    async with AsyncSessionLocal() as db:
        stmt = (
            update(Lead)
            .where(
                Lead.next_action_due_at.is_not(None),
                Lead.next_action_due_at <= now,
                Lead.needs_attention.is_(False),
                Lead.status.notin_(closed),
            )
            .values(needs_attention=True, updated_at=func.now())
            .returning(Lead.id)
        )
        result = await db.execute(stmt)
        ids = list(result.scalars().all())
        await db.commit()

    logger.info("Marked %d leads as needing attention", len(ids))


if __name__ == "__main__":
    run_job("mark_overdue_leads", mark_overdue)
