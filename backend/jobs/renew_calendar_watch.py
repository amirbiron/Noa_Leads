"""
renew_calendar_watch — רץ פעם ביום (מומלץ 04:00).

מחדש את watch channel של Google Calendar אם הוא פג תוך 24 שעות, או
אם אין channel קיים בכלל (למשל אחרי deploy חדש שבו backend_url רק עתה
הוגדר).

אם BACKEND_URL לא מוגדר — הג'וב לא יוצר watch (warn + exit 0).
אם Google לא מחובר — דילוג שקט.
אם Google env vars חסרים על ה-cron service — error log מפורש, **לא**
דילוג שקט (אחרת drift בתשתית הופך את הסנכרון לשבור בשקט). ראה
SETUP-CHECKLIST §3.A.3 ו-recurring-bug-patterns Pattern 5.
"""

import logging

from app.db.session import AsyncSessionLocal
from app.services import google_calendar as gc_service
from jobs._runner import run_job

logger = logging.getLogger("jobs.renew_calendar_watch")


async def renew_watch() -> None:
    async with AsyncSessionLocal() as db:
        try:
            # גילוי יומי של פקיעת חיבור: אימות מפורש של ה-credentials לפני
            # החידוש. אם ה-refresh token פג (Google מבטל אחרי 7 ימים ב-Testing
            # mode — ראה docs/google-calendar-setup.md), get_credentials_or_404
            # זורק GoogleAuthInvalidError ו-_mark_auth_invalid שולח את התראת
            # הטלגרם הקיימת — תוך ≤24h, ולא רק כש-renew_watch_if_needed במקרה
            # מגיע ל-create_watch (כל ~7 ימים). owner_alert_sent_at מונע ספאם.
            await gc_service.get_credentials_or_404(db)
            renewed = await gc_service.renew_watch_if_needed(db)
        except gc_service.GoogleNotConfiguredError:
            # env vars חסרים על cron service. זה drift לטנטי: ה-OAuth flow
            # רץ ב-web service (שיש לו env), נוצרת שורה ב-DB, ואז ה-cron
            # מנסה לקרוא ל-`_client_config()` ונופל. עד היצירה של ה-row
            # ה-cron היה עושה early return ב-`_load_row(db) is None` —
            # ולכן הdrift התחבא חודשים.
            #
            # logger.error (לא info/warning) כדי שהאלרט יהיה גלוי ב-logs
            # aggregator. **לא graceful skip שקט** — הסנכרון של הלקוחה
            # שבור עד שהאדמין מוסיף את ה-env לcron service ב-Render.
            logger.error(
                "Google env vars missing on cron service — calendar sync "
                "is BROKEN until GOOGLE_CLIENT_ID/SECRET/REDIRECT_URI "
                "are configured on the cron service in Render. "
                "See SETUP-CHECKLIST §3.A.3 (web+cron parity)."
            )
            return
        except gc_service.GoogleNotConnectedError:
            logger.info("Google Calendar not connected — skipping watch renewal")
            return
        except gc_service.GoogleAuthInvalidError:
            # get_credentials_or_404 כבר שלח התראת טלגרם בגילוי הראשון
            # (_mark_auth_invalid). ריצות הבאות רואות auth_invalid_at מסומן
            # ולא שולחות שוב.
            logger.warning(
                "Google auth invalid — owner alerted via Telegram, "
                "watch renewal skipped until reconnect"
            )
            return

        if renewed:
            logger.info("Calendar watch channel renewed")
        else:
            logger.info("Calendar watch still valid — no renewal needed")


if __name__ == "__main__":
    # requires_encryption=True — ה-cron קורא ל-decrypt_secret על refresh_token
    # ב-DB. eager validation ב-_runner נכשל ב-startup אם SECRETS_ENCRYPTION_KEY
    # חסר/invalid, במקום לחכות שמגיע ל-קריאה.
    run_job("renew_calendar_watch", renew_watch, requires_encryption=True)
