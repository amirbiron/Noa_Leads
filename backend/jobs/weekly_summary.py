"""
weekly_summary — רץ ביום ראשון בבוקר.

משתמש ב-get_weekly_insights הקיים מ-services/dashboard.
שולח לטלגרם את 3 התובנות המרכזיות מהאפיון.
"""

import logging

from app.db.session import AsyncSessionLocal
from app.services import dashboard as dashboard_service
from app.services import telegram as telegram_service
from jobs._runner import run_job

logger = logging.getLogger("jobs.weekly_summary")


def _format_insights(stats) -> str:
    # שיעור מענה בזמן — שימושי כעיני המקרו
    pct = ""
    if stats.new_leads_count > 0:
        ratio = round(100 * stats.responded_in_time_count / stats.new_leads_count)
        pct = f" ({ratio}%)"

    lines = [
        "📈 <b>סיכום שבועי</b>",
        "",
        f"📥 לידים השבוע: <b>{stats.new_leads_count}</b>",
        f"⚡ מענה בזמן: <b>{stats.responded_in_time_count}</b>{pct}",
        f"🔒 פתוחים בלי צעד הבא: <b>{stats.stuck_count}</b>",
        f"📋 סה\"כ פתוחים: <b>{stats.total_open}</b>",
    ]
    return "\n".join(lines)


async def weekly_summary() -> None:
    async with AsyncSessionLocal() as db:
        stats = await dashboard_service.get_weekly_insights(db)

    text = _format_insights(stats)
    sent = await telegram_service.send_message(text)
    if sent:
        logger.info("Weekly summary sent")
    else:
        logger.info("Weekly summary not sent (telegram not configured)")


if __name__ == "__main__":
    run_job("weekly_summary", weekly_summary)
