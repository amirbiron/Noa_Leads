"""
daily_summary — רץ ב-19:00 כל יום (לפי TZ ישראל; מתוזמן ב-UTC ב-render.yaml).

מחשב סיכום יומי קצר ושומר ב-DB (טבלת `daily_summaries`). הדשבורד שולף
ומציג. *לא* נשלח לטלגרם — לפי Spec §16.3 + Changelog v2.1: טלגרם הוא
ערוץ ייחודי לליד חדש בלבד. ראה F-07 ב-docs/spec-deviations.md.
"""

import logging
from datetime import datetime, time, timedelta, timezone

from sqlalchemy import and_, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import CLOSED_LEAD_STATUSES, TaskStatus
from app.db.session import AsyncSessionLocal
from app.models.daily_summary import DailySummary
from app.models.lead import Lead
from app.models.task import Task
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


async def daily_summary() -> None:
    """
    מחשב את ה-stats לתאריך הנוכחי בישראל, ושומר/מעדכן את ה-row המתאים
    ב-`daily_summaries`. ON CONFLICT (summary_date) DO UPDATE — בטוח אם
    cron רץ פעמיים באותו יום (recovery / manual re-run).
    """
    async with AsyncSessionLocal() as db:
        stats = await _gather_stats(db)
        today_israel = to_israel_tz(datetime.now(timezone.utc)).date()

        stmt = pg_insert(DailySummary).values(
            summary_date=today_israel,
            new_leads_today=stats["new_leads_today"],
            tasks_done_today=stats["tasks_done_today"],
            tasks_for_tomorrow=stats["tasks_for_tomorrow"],
            urgent_open=stats["urgent_open"],
        )
        # upsert לפי summary_date — re-run באותו יום מעדכן את הקיים
        upsert_stmt = stmt.on_conflict_do_update(
            index_elements=["summary_date"],
            set_={
                "new_leads_today": stmt.excluded.new_leads_today,
                "tasks_done_today": stmt.excluded.tasks_done_today,
                "tasks_for_tomorrow": stmt.excluded.tasks_for_tomorrow,
                "urgent_open": stmt.excluded.urgent_open,
                "generated_at": func.now(),
            },
        )
        await db.execute(upsert_stmt)
        await db.commit()

    logger.info("Daily summary saved to DB for %s: %s", today_israel, stats)


if __name__ == "__main__":
    run_job("daily_summary", daily_summary)
