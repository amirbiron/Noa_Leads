"""
detect_dormant_leads — רץ פעם ביום ב-03:00.

מסמן dormant_flag=True לכל ליד פתוח שלא הייתה ממנו אינטראקציה ב-60+ ימים.

§19 D.1 — החלפה: ה-job *לא* יוצר יותר משימת dormant_check. יצירת המשימה
(כעת dormant_suggestion עם המלצת AI) עברה ל-cron הייעודי
suggest_dormant_actions, שרץ אחרי ה-job הזה. כך לידים פסיביים (archive/
no_action) לא מוקפצים ל-/today. הסימון dormant_flag נשאר כאן כ-signal כללי.

הערה: לידים רדומים מחוץ להגדרה המדויקת של ההמלצות (NEW / בלי outbound)
כבר מטופלים ע"י first_response תקוע — אינם נופלים בין הכיסאות.

chip "לא רלוונטי כרגע" עדיין יוצר dormant_check בנפרד (§16.4) — לא נגענו.
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
        newly_dormant = list(result.all())
        await db.commit()

    logger.info("Marked %d leads as dormant", len(newly_dormant))


if __name__ == "__main__":
    run_job("detect_dormant_leads", detect_dormant)
