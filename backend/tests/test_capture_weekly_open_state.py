"""בדיקות ל-cron `jobs.capture_weekly_open_state`.

integration מול Postgres אמיתי — מדלגות אם אין DB (כמו test_summary_inputs).
מאמת: snapshot נכתב עם השדות הנכונים, first-write-wins, חישוב week_end_date
robust ל-DST.
"""

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.constants import LeadStatus, SourceChannel
from app.models.lead import Lead
from app.models.weekly_open_state_snapshot import WeeklyOpenStateSnapshot
from jobs.capture_weekly_open_state import _resolve_week_end_date


# ===== בדיקות pure (ללא DB) =====


def test_resolve_week_end_idt_sunday_post_midnight():
    """IDT (קיץ): cron ב-Sat 22:30 UTC → Sun 01:30 IDT. weekday=Sun, day-back=1.

    זמן ההרצה הוא 1.5h אחרי capture_time (Sun 00:00 IDT), בשטח של "אחרי
    מוצ"ש לפני בוקר ראשון".
    """
    # Sat 2026-08-29 22:30 UTC == Sun 2026-08-30 01:30 IDT (UTC+3)
    now_utc = datetime(2026, 8, 29, 22, 30, tzinfo=timezone.utc)
    week_end_date, capture_time = _resolve_week_end_date(now_utc)
    # השבת האחרונה בישראל = אתמול בישראל = Sat 2026-08-29
    assert week_end_date == date(2026, 8, 29)
    # capture_time = חצות ראשון בישראל בקיץ = Sat 21:00 UTC
    assert capture_time == datetime(2026, 8, 29, 21, 0, tzinfo=timezone.utc)


def test_resolve_week_end_ist_sunday_post_midnight():
    """IST (חורף): cron ב-Sat 22:30 UTC → Sun 00:30 IST. weekday=Sun, day-back=1.

    זמן ההרצה הוא 30min אחרי capture_time (Sun 00:00 IST). פער מינימלי.
    """
    # Sat 2026-12-26 22:30 UTC == Sun 2026-12-27 00:30 IST (UTC+2)
    now_utc = datetime(2026, 12, 26, 22, 30, tzinfo=timezone.utc)
    week_end_date, capture_time = _resolve_week_end_date(now_utc)
    # השבת האחרונה בישראל = אתמול בישראל = Sat 2026-12-26
    assert week_end_date == date(2026, 12, 26)
    # capture_time = חצות ראשון בישראל בחורף = Sat 22:00 UTC
    assert capture_time == datetime(2026, 12, 26, 22, 0, tzinfo=timezone.utc)


def test_resolve_week_end_mid_week_returns_most_recent_saturday():
    """לא רץ ב-cron, אבל helper צריך להיות חסין: שלישי → שבת שלפניו."""
    # Tue 2026-09-01 12:00 UTC; Tuesday=1; days_back = (1-5)%7 = 3
    now_utc = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
    week_end_date, _ = _resolve_week_end_date(now_utc)
    # שבת לפני שלישי 09-01 = 2026-08-29
    assert week_end_date == date(2026, 8, 29)


# ===== בדיקות integration (DB) =====


async def test_snapshot_writes_with_correct_fields(db):
    """ה-job כותב snapshot עם 5 השדות + generated_at."""
    from jobs.capture_weekly_open_state import _resolve_week_end_date

    now_utc = datetime.now(timezone.utc)
    week_end_date, _ = _resolve_week_end_date(now_utc)

    # ליד פתוח רגיל כדי שיהיה מה לספור (משתמש ב-conftest db שעושה rollback).
    ten_days_ago = now_utc - timedelta(days=10)
    db.add(Lead(
        full_name="ליד בדיקה",
        source_channel=SourceChannel.MANUAL.value,
        status=LeadStatus.IN_PROGRESS.value,
        created_at=ten_days_ago,
    ))
    await db.flush()

    # מבצעים את כתיבת ה-snapshot ישירות באותה session כדי לעבוד עם
    # ה-rollback fixture (אחרת ה-cron פותח session חדש שלא מתגלגל).
    from app.services import summary_inputs

    state = await summary_inputs._open_state(db, now_utc)
    dormant = await summary_inputs._dormant_with_recommendation_count(db, now_utc)

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
    await db.flush()

    row = (
        await db.execute(
            select(WeeklyOpenStateSnapshot).where(
                WeeklyOpenStateSnapshot.week_end_date == week_end_date
            )
        )
    ).scalar_one_or_none()
    assert row is not None
    assert row.open_leads_total >= 1  # הליד שיצרנו
    assert row.generated_at is not None


async def test_first_write_wins_no_overwrite(db):
    """re-run של ה-cron באותו שבוע לא דורס את ה-row הקיים."""
    target_date = date(2026, 5, 23)  # תאריך קבוע, לא תלוי בריצה

    # כתיבה ראשונה
    stmt1 = (
        pg_insert(WeeklyOpenStateSnapshot)
        .values(
            week_end_date=target_date,
            open_leads_total=42,
            stuck_leads_count=3,
            stale_proposals_count=1,
            overdue_tasks_count=5,
            dormant_with_recommendation_count=2,
        )
        .on_conflict_do_nothing(index_elements=["week_end_date"])
    )
    await db.execute(stmt1)
    await db.flush()

    row_first = (
        await db.execute(
            select(WeeklyOpenStateSnapshot).where(
                WeeklyOpenStateSnapshot.week_end_date == target_date
            )
        )
    ).scalar_one()
    first_generated_at = row_first.generated_at

    # כתיבה שניה עם ערכים שונים — אסור לדרוס
    stmt2 = (
        pg_insert(WeeklyOpenStateSnapshot)
        .values(
            week_end_date=target_date,
            open_leads_total=99,
            stuck_leads_count=99,
            stale_proposals_count=99,
            overdue_tasks_count=99,
            dormant_with_recommendation_count=99,
        )
        .on_conflict_do_nothing(index_elements=["week_end_date"])
    )
    await db.execute(stmt2)
    await db.flush()

    row_second = (
        await db.execute(
            select(WeeklyOpenStateSnapshot).where(
                WeeklyOpenStateSnapshot.week_end_date == target_date
            )
        )
    ).scalar_one()
    # ערכים ראשונים נשמרו, generated_at לא השתנה
    assert row_second.open_leads_total == 42
    assert row_second.stuck_leads_count == 3
    assert row_second.generated_at == first_generated_at
