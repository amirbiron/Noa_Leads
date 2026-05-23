"""
detect_dormant_leads — רץ פעם ביום ב-03:00.

מסמן dormant_flag=True לכל ליד פתוח שלא הייתה ממנו אינטראקציה ב-60+ ימים.
מתאים ל-AI ב-pass עתידי להציע "חידוש קשר עדין / ארכוב".
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_, update

from app.constants import CLOSED_LEAD_STATUSES
from app.db.session import AsyncSessionLocal
from app.models.lead import Lead
from jobs._runner import run_job

logger = logging.getLogger("jobs.detect_dormant")


DORMANT_THRESHOLD_DAYS = 60


async def detect_dormant() -> None:
    threshold = datetime.now(timezone.utc) - timedelta(days=DORMANT_THRESHOLD_DAYS)
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
        ids = list(result.scalars().all())
        await db.commit()

    logger.info("Marked %d leads as dormant", len(ids))


if __name__ == "__main__":
    run_job("detect_dormant_leads", detect_dormant)
