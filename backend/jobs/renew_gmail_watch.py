"""
renew_gmail_watch — רץ פעם ביום (מומלץ 02:00, 2h אחרי calendar renewal).

Gmail watch מקסימום ~7 ימים — חידוש יומי בודק אם expires תוך 24h
ומחדש. אם GMAIL_PUBSUB_TOPIC לא מוגדר — דילוג שקט.
אם Gmail לא מחובר — דילוג שקט.
"""

import logging

from app.db.session import AsyncSessionLocal
from app.services import gmail as gmail_service
from jobs._runner import run_job

logger = logging.getLogger("jobs.renew_gmail_watch")


async def renew_watch() -> None:
    async with AsyncSessionLocal() as db:
        try:
            renewed = await gmail_service.renew_watch_if_needed(db)
        except gmail_service.GmailNotConnectedError:
            logger.info("Gmail not connected — skipping watch renewal")
            return
        except gmail_service.GmailAuthInvalidError:
            logger.warning(
                "Gmail auth invalid — watch renewal skipped (owner already alerted)"
            )
            return
        except gmail_service.GmailWatchNotConfiguredError:
            logger.info(
                "Skipping Gmail watch renewal: GMAIL_PUBSUB_TOPIC not configured"
            )
            return

        if renewed:
            logger.info("Gmail watch renewed")
        else:
            logger.info("Gmail watch still valid — no renewal needed")


if __name__ == "__main__":
    # requires_encryption=True — מפענח refresh_token של Gmail מ-DB.
    run_job("renew_gmail_watch", renew_watch, requires_encryption=True)
