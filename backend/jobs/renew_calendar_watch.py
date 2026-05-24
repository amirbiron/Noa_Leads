"""
renew_calendar_watch — רץ פעם ביום (מומלץ 04:00).

מחדש את watch channel של Google Calendar אם הוא פג תוך 24 שעות, או
אם אין channel קיים בכלל (למשל אחרי deploy חדש שבו backend_url רק עתה
הוגדר).

אם BACKEND_URL לא מוגדר — הג'וב לא יוצר watch (warn + exit 0).
אם Google לא מחובר — דילוג שקט.
"""

import logging

from app.db.session import AsyncSessionLocal
from app.services import google_calendar as gc_service
from jobs._runner import run_job

logger = logging.getLogger("jobs.renew_calendar_watch")


async def renew_watch() -> None:
    async with AsyncSessionLocal() as db:
        try:
            renewed = await gc_service.renew_watch_if_needed(db)
        except gc_service.GoogleNotConnectedError:
            logger.info("Google Calendar not connected — skipping watch renewal")
            return
        except gc_service.GoogleAuthInvalidError:
            logger.warning(
                "Google auth invalid — watch renewal skipped (owner already alerted)"
            )
            return

        if renewed:
            logger.info("Calendar watch channel renewed")
        else:
            logger.info("Calendar watch still valid — no renewal needed")


if __name__ == "__main__":
    run_job("renew_calendar_watch", renew_watch)
