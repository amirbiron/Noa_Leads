"""
daily_summary — רץ ב-19:00 כל יום (לפי TZ ישראל; מתוזמן ב-UTC ב-render.yaml).

מחשב סיכום יומי קצר ושומר ב-DB (טבלת `daily_summaries`) כ-snapshot קבוע.
הדשבורד שולף ומציג. *לא* נשלח לטלגרם — לפי Spec §16.3 + Changelog v2.1:
טלגרם הוא ערוץ ייחודי לליד חדש בלבד. ראה F-07 ב-docs/spec-deviations.md.

מודל החלון (Spec §5.12):
- מטריקות רטרוספקטיביות (לידים חדשים, משימות שהושלמו) נספרות בחלון של
  24 שעות אחורה מרגע הריצה (`now-24h → now`), *לא* לפי גבולות חצות. כך
  ליד שנכנס אחרי שעת הריצה (למשל 20:00) נכנס לסיכום של *מחר* — מחר ב-19:00
  הוא בתוך 24h אחורה. אין פער 19:00–חצות שבו ליד נופל בין הכיסאות.
- `tasks_for_tomorrow` (צופה קדימה) נשאר יום-לוח מלא של מחר.
- first-write-wins: ה-snapshot של היום נכתב פעם אחת; re-run באותו תאריך
  לא משכתב (ON CONFLICT DO NOTHING) — הסיכום קבוע אחרי הריצה הראשונה.
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


def _tomorrow_bounds_israel(
    now_utc: datetime,
) -> tuple[datetime, datetime]:
    """
    מחזיר (start_of_tomorrow_utc, end_of_tomorrow_utc) — גבולות יום-הלוח
    של מחר בישראל, ל-`tasks_for_tomorrow` (המטריקה הצופה קדימה).

    כל boundary נבנה עצמאית כ-midnight של ה-date המתאים, ולא כ-start+1d.
    הסיבה: datetime+timedelta מוסיף שעות אבסולוטיות (24/48), ובימי מעבר
    שעון (אביב/סתיו) זה היה גורם לגבול ליפול ב-01:00 או 23:00 במקום חצות,
    ומשימות היו נספרות ביום הלא נכון בסיכום. אותו פתרון כמו ב-
    services/dashboard._current_week_bounds.
    """
    local = to_israel_tz(now_utc)
    tomorrow = local.date() + timedelta(days=1)
    day_after = local.date() + timedelta(days=2)
    start_tomorrow = datetime.combine(tomorrow, time(0, 0, tzinfo=ISRAEL_TZ))
    end_tomorrow = datetime.combine(day_after, time(0, 0, tzinfo=ISRAEL_TZ))
    return (
        start_tomorrow.astimezone(timezone.utc),
        end_tomorrow.astimezone(timezone.utc),
    )


async def _gather_stats(db: AsyncSession) -> dict[str, int]:
    now_utc = datetime.now(timezone.utc)
    # חלון רטרוספקטיבי: 24 שעות אחורה מרגע הריצה (לא גבולות חצות). מבטיח
    # שליד/משימה שנכנס אחרי שעת הריצה ייכנס לסיכום של מחר ולא ייפול בין
    # הכיסאות. ריצות יומיות הן בדיוק 24h זו מזו ב-UTC → gapless גם בחורף.
    window_start = now_utc - timedelta(hours=24)
    start_tomorrow, end_tomorrow = _tomorrow_bounds_israel(now_utc)
    closed = [s.value for s in CLOSED_LEAD_STATUSES]

    new_leads_today = (
        await db.execute(
            select(func.count())
            .select_from(Lead)
            .where(Lead.created_at >= window_start, Lead.created_at < now_utc)
        )
    ).scalar_one()

    tasks_done_today = (
        await db.execute(
            select(func.count())
            .select_from(Task)
            .where(
                Task.status == TaskStatus.DONE.value,
                Task.completed_at >= window_start,
                Task.completed_at < now_utc,
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
    מחשב את ה-stats ושומר row חדש ב-`daily_summaries` לתאריך הנוכחי בישראל.

    first-write-wins: ON CONFLICT (summary_date) DO NOTHING — אם כבר קיים
    snapshot של היום, הוא *לא* משוכתב, כך שהסיכום קבוע אחרי הריצה הראשונה.
    אם ריצת 19:00 נכשלה ואין עדיין row — ריצה מאוחרת יותר באותו יום תכתוב
    (אין conflict), עם חלון 24h מאותו רגע (recovery). בטוח גם אם שתי ריצות
    מתנגשות — ה-DO NOTHING על summary_date UNIQUE הוא אטומי ברמת ה-DB.
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
        # first-write-wins: snapshot קבוע — re-run באותו יום לא משכתב
        insert_stmt = stmt.on_conflict_do_nothing(index_elements=["summary_date"])
        await db.execute(insert_stmt)
        await db.commit()

    logger.info("Daily summary snapshot for %s: %s", today_israel, stats)


if __name__ == "__main__":
    run_job("daily_summary", daily_summary)
