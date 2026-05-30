"""
capture_weekly_open_state — צילום קבוע של "מצב פתוח בסוף השבוע".

מתוזמן: Saturday 21:00 UTC ב-`render.yaml`. בשעון ישראל:
- IDT (קיץ, UTC+3): Sunday 00:00 — בדיוק חצות ראשון.
- IST (חורף, UTC+2): Saturday 23:00 — שעה לפני חצות ראשון.

שני המקרים הם **נקודה מתה** — מוצ"ש כבר עבר (~20:00 IDT / ~17:30 IST),
ופעילות ראשון-בבוקר עוד לא התחילה. זוהי הזדמנות לחתום על המצב לפני
שפעילות ראשון מזהמת את הסטטיסטיקות "בסוף השבוע".

הסיבה הארכיטקטונית: שחזור עבר מתוך שדות mutable (`Lead.status`,
`Task.due_at` שנדרס ב-snooze, `Lead.closed_at` שמתאפס ב-reopen, וכו')
הוא מטבעו לא אמין — 7 ממצאי cursor bugbot על `_open_state` הוכיחו זאת.
צילום ברגע הנכון פותר את כל הגרסאות של הבעיה. דפוס מועתק מ-F-26/F-07
(`daily_summaries` + `jobs/daily_summary.py`).

first-write-wins (`ON CONFLICT (week_end_date) DO NOTHING`): re-run של ה-cron
באותו שבוע לא דורס. הצילום קבוע אחרי הריצה הראשונה.

חישוב week_end_date robust ל-DST: מציאת השבת האחרונה בישראל מה-now של
ההרצה — מטפל בשני המצבים (IDT שמראה Sun, IST שמראה Sat) זהה.
"""

import logging
from datetime import datetime, time, timedelta, timezone

from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db.session import AsyncSessionLocal
from app.models.weekly_open_state_snapshot import WeeklyOpenStateSnapshot
from app.services import summary_inputs
from app.utils.work_hours import ISRAEL_TZ, to_israel_tz
from jobs._runner import run_job

logger = logging.getLogger("jobs.capture_weekly_open_state")


def _resolve_week_end_date(now_utc: datetime):
    """
    מחזיר את התאריך של השבת האחרונה בישראל (כולל היום אם היום שבת),
    + capture_time UTC = חצות ראשון בישראל (סיום השבוע exclusive).

    מטפל DST-safe בשני המצבים של זמני ה-cron:
    - IDT (Sat 21:00 UTC → Sun 00:00 IL): weekday=Sun=6, days_back=1, אתמול.
    - IST (Sat 21:00 UTC → Sat 23:00 IL): weekday=Sat=5, days_back=0, היום.
    שני המקרים מחזירים את אותה שבת — סוף השבוע שהסתיים.
    """
    local = to_israel_tz(now_utc)
    # weekday: Mon=0..Sat=5..Sun=6. שבת=5; ימי אחורה ממנו (=0 אם היום שבת):
    days_back = (local.weekday() - 5) % 7
    week_end_date = local.date() - timedelta(days=days_back)
    # capture_time = חצות ראשון בישראל = יום אחרי שבת ב-00:00 ישראל,
    # מתורגם UTC. משמש כ-anchor של `_open_state` במקום `now_utc` — כך
    # cron מאוחר (חודר לראשון) לא מזהם את ה-snapshot.
    capture_local = datetime.combine(
        week_end_date + timedelta(days=1), time(0, 0, tzinfo=ISRAEL_TZ)
    )
    capture_time_utc = capture_local.astimezone(timezone.utc)
    return week_end_date, capture_time_utc


async def capture_weekly_open_state() -> None:
    """
    מחשב את 5 השדות של "מצב פתוח בסוף השבוע" ושומר row חדש.

    `_open_state(db, capture_time)` משתמש ב-anchor הקבוע (חצות ראשון
    בישראל), לא ב-`now_utc` — כך גם cron שרץ באיחור (חודר לראשון) לא
    יזהם את ה-snapshot עם פעילות ראשון.

    `_dormant_with_recommendation_count(db)` עדיין מבוסס על current state
    (D.1 §3.6). ה-snapshot לוכד אותו ברגע ההרצה — אם cron בזמן, current
    state == state ב-week_end. cron מאוחר → drift קל, אבל ה-snapshot
    עדיין קבוע פר-שבוע (first-write-wins).
    """
    now_utc = datetime.now(timezone.utc)
    week_end_date, capture_time = _resolve_week_end_date(now_utc)

    async with AsyncSessionLocal() as db:
        state = await summary_inputs._open_state(db, capture_time)
        dormant = await summary_inputs._dormant_with_recommendation_count(db)

        stmt = (
            pg_insert(WeeklyOpenStateSnapshot)
            .values(
                week_end_date=week_end_date,
                open_leads_total=state["open_leads_total"],
                stuck_leads_count=state["stuck_leads_count"],
                stale_proposals_count=state["stale_proposals_count"],
                overdue_tasks_count=state["overdue_tasks_count"],
                dormant_with_recommendation_count=dormant,
            )
            .on_conflict_do_nothing(index_elements=["week_end_date"])
        )
        await db.execute(stmt)
        await db.commit()

    logger.info(
        "Weekly open-state snapshot for week ending %s: open=%s stuck=%s "
        "stale_proposals=%s overdue_tasks=%s dormant=%s",
        week_end_date,
        state["open_leads_total"],
        state["stuck_leads_count"],
        state["stale_proposals_count"],
        state["overdue_tasks_count"],
        dormant,
    )


if __name__ == "__main__":
    run_job("capture_weekly_open_state", capture_weekly_open_state)
