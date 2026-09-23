"""
retry_pending_classification — F-16, Spec §23.

רץ כל דקה. מוצא email_messages עם `processing_status='pending'` ומעביר
ל-`gmail_intake.retry_pending_email`, שמחליט מה לעשות לפי
`classification_retry_count`:
- count < MAX → retry AI classify+extract.
- count >= MAX → יוצר ליד עם `manual_review_needed=True` (בלי קריאה ל-AI).

חשוב: ה-cron *לא* מסנן לפי count. אם `_create_manual_review_lead` נכשל
פעם אחת (DB error, race), ה-row היה מסומן כ-pending עם count==MAX —
אילו הסיננו `count < MAX`, ה-row היה תקוע לעד (bugbot finding). עכשיו
ה-cron מנסה שוב; manual_review_needed לא קורא ל-AI, אז אין עלות חוזרת.

batch size מוגבל ל-10 — לא לעמוס על Anthropic API.
"""

import logging

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.email_message import PROCESSING_STATUS_PENDING, EmailMessage
from app.services import gmail_intake
from jobs._runner import run_job

logger = logging.getLogger("jobs.retry_pending_classification")

# מספר רשומות מקסימלי בריצה. כל ריצה רצה כל דקה — לא לעמוס Anthropic.
# 10 הוא tradeoff: מספיק לטפל בbacklog קטן, לא מספיק לגרום ל-429.
_BATCH_SIZE = 10


async def retry_pending() -> None:
    async with AsyncSessionLocal() as db:
        # processing_status='pending' מבדיל בין רשומות שצריכות retry של AI
        # לבין רשומות סופיות (heuristic_spam, not_business, lead_created,
        # manual_review). בלי הדגל הזה ה-cron היה סורק גם spam-skip ו-
        # not_business — כל מייל ניוזלטר היה הופך אחרי 10 דקות לליד עם
        # manual_review_needed. תיקון bugbot Phase 3 Stage 18 commit 4/4.
        #
        # אין סינון לפי `classification_retry_count` — האחריות על MAX עברה
        # ל-`retry_pending_email`. ראה docstring למעלה.
        result = await db.execute(
            select(EmailMessage)
            .where(EmailMessage.processing_status == PROCESSING_STATUS_PENDING)
            .order_by(EmailMessage.created_at.asc())
            .limit(_BATCH_SIZE)
        )
        pending = result.scalars().all()

        if not pending:
            logger.info("No pending email_messages to retry")
            return

        logger.info("Retrying %d pending email_messages", len(pending))

        for email_msg in pending:
            try:
                await gmail_intake.retry_pending_email(db, email_msg)
            except Exception:
                logger.exception(
                    "Retry failed for email_message %s", email_msg.id
                )


if __name__ == "__main__":
    # requires_encryption=True — apply_filter_label דורש refresh_token
    # מפוענח של Gmail.
    run_job("retry_pending_classification", retry_pending, requires_encryption=True)
