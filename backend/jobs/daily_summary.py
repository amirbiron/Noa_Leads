"""
daily_summary — רץ ב-19:00 כל יום (לפי TZ ישראל; מתוזמן ב-UTC ב-render.yaml).

שולח לנועה בטלגרם סיכום קצר של היום: כמה לידים נכנסו, כמה משימות
בוצעו, וכמה ממתינות למחר. נשמר מינימליסטי לפי האפיון —
"סיכום יומי קצר — מה קרה היום, מה ממתין מחר".
"""

import logging
from datetime import datetime, time, timedelta, timezone

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import CLOSED_LEAD_STATUSES, TaskStatus
from app.db.session import AsyncSessionLocal
from app.models.lead import Lead
from app.models.task import Task
from app.services import telegram as telegram_service
from app.utils.work_hours import ISRAEL_TZ, to_israel_tz
from jobs._runner import run_job

logger = logging.getLogger("jobs.daily_summary")


def _day_bounds_israel(
    now_utc: datetime,
) -> tuple[datetime, datetime, datetime]:
    """
    מחזיר (start_of_today_utc, start_of_tomorrow_utc, end_of_tomorrow_utc).

    כל boundary נבנה עצמאית כ-midnight של ה-date המתאים, ולא כ-start+1d.
    הסיבה: datetime+timedelta מוסיף שעות אבסולוטיות (24/48), ובימי מעבר
    שעון (אביב/סתיו) זה היה גורם לגבול ליפול ב-01:00 או 23:00 במקום חצות,
    ומשימות היו נספרות ביום הלא נכון בסיכום. אותו פתרון כמו ב-
    services/dashboard._current_week_bounds.
    """
    local = to_israel_tz(now_utc)
    today = local.date()
    tomorrow = today + timedelta(days=1)
    day_after = today + timedelta(days=2)
    start_today = datetime.combine(today, time(0, 0, tzinfo=ISRAEL_TZ))
    start_tomorrow = datetime.combine(tomorrow, time(0, 0, tzinfo=ISRAEL_TZ))
    end_tomorrow = datetime.combine(day_after, time(0, 0, tzinfo=ISRAEL_TZ))
    return (
        start_today.astimezone(timezone.utc),
        start_tomorrow.astimezone(timezone.utc),
        end_tomorrow.astimezone(timezone.utc),
    )


async def _gather_stats(db: AsyncSession) -> dict[str, int]:
    now_utc = datetime.now(timezone.utc)
    start_today, start_tomorrow, end_tomorrow = _day_bounds_israel(now_utc)
    closed = [s.value for s in CLOSED_LEAD_STATUSES]

    new_leads_today = (
        await db.execute(
            select(func.count())
            .select_from(Lead)
            .where(Lead.created_at >= start_today, Lead.created_at < start_tomorrow)
        )
    ).scalar_one()

    tasks_done_today = (
        await db.execute(
            select(func.count())
            .select_from(Task)
            .where(
                Task.status == TaskStatus.DONE.value,
                Task.completed_at >= start_today,
                Task.completed_at < start_tomorrow,
            )
        )
    ).scalar_one()

    tasks_for_tomorrow = (
        await db.execute(
            select(func.count())
            .select_from(Task)
            .where(
                or_(
                    Task.status == TaskStatus.OPEN.value,
                    and_(
                        Task.status == TaskStatus.SNOOZED.value,
                        Task.due_at <= end_tomorrow,
                    ),
                ),
                Task.due_at >= start_tomorrow,
                Task.due_at < end_tomorrow,
            )
        )
    ).scalar_one()

    urgent_open = (
        await db.execute(
            select(func.count())
            .select_from(Lead)
            .where(
                Lead.status.notin_(closed),
                Lead.needs_attention.is_(True),
            )
        )
    ).scalar_one()

    return {
        "new_leads_today": new_leads_today,
        "tasks_done_today": tasks_done_today,
        "tasks_for_tomorrow": tasks_for_tomorrow,
        "urgent_open": urgent_open,
    }


def _format_summary(stats: dict[str, int]) -> str:
    lines = ["📊 <b>סיכום יומי</b>", ""]
    lines.append(f"📥 לידים חדשים היום: <b>{stats['new_leads_today']}</b>")
    lines.append(f"✅ משימות שבוצעו: <b>{stats['tasks_done_today']}</b>")
    lines.append(f"📅 משימות מחר: <b>{stats['tasks_for_tomorrow']}</b>")
    if stats["urgent_open"] > 0:
        lines.append("")
        lines.append(
            f"⚠️ <b>{stats['urgent_open']}</b> לידים דחופים ממתינים לטיפול"
        )
    return "\n".join(lines)


async def daily_summary() -> None:
    async with AsyncSessionLocal() as db:
        stats = await _gather_stats(db)

    text = _format_summary(stats)
    sent = await telegram_service.send_message(text)
    if sent:
        logger.info("Daily summary sent: %s", stats)
    else:
        logger.info("Daily summary not sent (telegram not configured)")


if __name__ == "__main__":
    run_job("daily_summary", daily_summary)
