"""
weekly_summary — רץ ביום ראשון בבוקר (מתוזמן ב-UTC ב-render.yaml).

מייצר סיכום שבועי נרטיבי (C.2) ושומר ב-ai_summaries. *לא* נשלח לטלגרם —
לפי c1-c2-summaries-spec §3.1 + §7 ("TL;DR לטלגרם נשלל. רק במערכת").
הסיכום מוצג בעמוד "היום" של נועה (UI — סבב נפרד).

דילוג בחג: אם יום ראשון עצמו נופל בחג יהודי (§6.7) — נועה לא עובדת אז,
וסיכום של שבוע ריק יטעה. should_skip_weekly_summary מטפל בזה.
"""

import logging
from datetime import datetime, timezone

from app.db.session import AsyncSessionLocal
from app.services import summaries as summaries_service
from app.utils.work_hours import should_skip_weekly_summary
from jobs._runner import run_job

logger = logging.getLogger("jobs.weekly_summary")


async def weekly_summary() -> None:
    now_utc = datetime.now(timezone.utc)
    if should_skip_weekly_summary(now_utc):
        logger.info("Weekly summary skipped (holiday/Saturday in Israel)")
        return

    async with AsyncSessionLocal() as db:
        summary = await summaries_service.generate_and_store_weekly_summary(
            db, now_utc=now_utc
        )

    if summary is not None:
        logger.info("Weekly summary generated and stored")
    else:
        logger.warning("Weekly summary not generated (AI unavailable)")


if __name__ == "__main__":
    run_job("weekly_summary", weekly_summary)
