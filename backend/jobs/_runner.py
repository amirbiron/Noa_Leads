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


def run_job(name: str, fn: Callable[[], Awaitable[None]]) -> None:
    """מריץ async job, סוגר engine בסוף, exit 1 אם נכשל."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logger.info("Starting job: %s", name)
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
