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
            # גילוי יומי של פקיעת חיבור: אימות מפורש של ה-credentials לפני
            # החידוש. אם ה-refresh token פג (Google מבטל אחרי 7 ימים ב-Testing
            # mode), get_credentials_or_404 זורק GmailAuthInvalidError ו-
            # _mark_auth_invalid שולח את התראת הטלגרם הקיימת — תוך ≤24h, ולא
            # רק על מייל נכנס או חידוש watch (~כל 7 ימים). owner_alert_sent_at
            # מונע ספאם.
            await gmail_service.get_credentials_or_404(db)
            renewed = await gmail_service.renew_watch_if_needed(db)
        except gmail_service.GmailNotConfiguredError:
            # env vars חסרים על cron service (web+cron parity — ראה
            # SETUP-CHECKLIST §3.A.3). לא graceful skip שקט.
            logger.error(
                "Gmail env vars missing on cron service — Gmail sync is "
                "BROKEN until GOOGLE_CLIENT_ID/SECRET + GMAIL_* are configured "
                "on the cron service in Render. See SETUP-CHECKLIST §3.A.3."
            )
            return
        except gmail_service.GmailNotConnectedError:
            logger.info("Gmail not connected — skipping watch renewal")
            return
        except gmail_service.GmailAuthInvalidError:
            # get_credentials_or_404 כבר שלח התראת טלגרם בגילוי הראשון.
            logger.warning(
                "Gmail auth invalid — owner alerted via Telegram, "
                "watch renewal skipped until reconnect"
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
