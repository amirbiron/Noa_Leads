"""
מסגרת קטנה להרצת cron jobs אסינכרוניים מ-CLI.

אחראית על: logging, dispose של engine, ו-exit code.
כל job ייעבר כ-coroutine ללא ארגומנטים.
"""

import asyncio
import logging
import sys
from typing import Awaitable, Callable


logger = logging.getLogger("jobs")


def run_job(
    name: str,
    fn: Callable[[], Awaitable[None]],
    *,
    requires_encryption: bool = False,
) -> None:
    """מריץ async job, סוגר engine בסוף, exit 1 אם נכשל.

    `requires_encryption=True` מפעיל eager encryption check לפני שה-job
    רץ — fail-fast אם SECRETS_ENCRYPTION_KEY חסר/invalid או APP_ENV לא
    תקין. בלי זה cron שאמור לקרוא tokens מ-DB מגלה את הבעיה רק שם,
    בלב הריצה, עם stack trace קשה לקריאה. ה-flag opt-in כדי שcrons שלא
    נוגעים ב-encryption (mark_overdue, daily_summary וכו') לא ידרשו
    SECRETS_ENCRYPTION_KEY בענן.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logger.info("Starting job: %s", name)
    if requires_encryption:
        try:
            from app.utils.encryption import assert_encryption_ready

            assert_encryption_ready()
        except RuntimeError as e:
            logger.error("Job %s aborting: encryption misconfigured — %s", name, e)
            sys.exit(1)
    try:
        asyncio.run(_run_with_cleanup(fn))
        logger.info("Job %s completed successfully", name)
    except Exception:
        logger.exception("Job %s failed", name)
        sys.exit(1)


async def _run_with_cleanup(fn: Callable[[], Awaitable[None]]) -> None:
    # import עצל — קוראים ל-engine רק כשמריצים job אמיתי
    from app.db.session import engine

    try:
        await fn()
    finally:
        await engine.dispose()
