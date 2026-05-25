"""
retry_pending_classification — F-16, Spec §23.

רץ כל דקה. מוצא email_messages שעדיין לא קושרו לליד
(`lead_id IS NULL`) ושעדיין לא הגיעו למקסימום ניסיונות
(`classification_retry_count < AI_MAX_CLASSIFICATION_RETRIES`),
ומנסה שוב לסווג + לחלץ + ליצור ליד.

כשהמונה מגיע למקסימום (default 10) — נוצר ליד עם
`manual_review_needed=True` (לוגיקה ב-`gmail_intake.retry_pending_email`)
כדי שנועה תוכל לטפל ידנית.

batch size מוגבל ל-10 — לא לעמוס על Anthropic API.
"""

import logging

from sqlalchemy import select

from app.config import get_settings
from app.db.session import AsyncSessionLocal
from app.models.email_message import PROCESSING_STATUS_PENDING, EmailMessage
from app.services import gmail_intake
from jobs._runner import run_job

logger = logging.getLogger("jobs.retry_pending_classification")

# מספר רשומות מקסימלי בריצה. כל ריצה רצה כל דקה — לא לעמוס Anthropic.
# 10 הוא tradeoff: מספיק לטפל בbacklog קטן, לא מספיק לגרום ל-429.
_BATCH_SIZE = 10


async def retry_pending() -> None:
    settings = get_settings()
    max_retries = settings.ai_max_classification_retries

    async with AsyncSessionLocal() as db:
        # processing_status='pending' מבדיל בין רשומות שצריכות retry של AI
        # לבין רשומות סופיות (heuristic_spam, not_business, lead_created,
        # manual_review). בלי הדגל הזה ה-cron היה סורק גם spam-skip ו-
        # not_business — כל מייל ניוזלטר היה הופך אחרי 10 דקות לליד עם
        # manual_review_needed. תיקון bugbot Phase 3 Stage 18 commit 4/4.
        result = await db.execute(
            select(EmailMessage)
            .where(
                EmailMessage.processing_status == PROCESSING_STATUS_PENDING,
                EmailMessage.classification_retry_count < max_retries,
            )
            .order_by(EmailMessage.created_at.asc())
            .limit(_BATCH_SIZE)
        )
        pending = result.scalars().all()

        if not pending:
            logger.info("No pending email_messages to retry")
            return

        logger.info(
            "Retrying %d pending email_messages (max_retries=%d)",
            len(pending),
            max_retries,
        )

        for email_msg in pending:
            try:
                await gmail_intake.retry_pending_email(db, email_msg)
            except Exception:
                logger.exception(
                    "Retry failed for email_message %s", email_msg.id
                )


if __name__ == "__main__":
    run_job("retry_pending_classification", retry_pending)
