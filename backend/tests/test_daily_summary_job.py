"""בדיקות ל-cron `jobs.daily_summary` — חיווט סטטיסטי + AI.

אחרי השלמת סבב ז' של C.1/C.2 (`docs/c1-c2-summaries-spec.md`), ה-job
מריץ שני סיכומים: סטטיסטי (`daily_summaries`) ו-AI נרטיבי (`ai_summaries`).
הבדיקות מאמתות:
- gating ע"י `should_skip_daily_summary` חל על שניהם.
- ריצה רגילה — שני הסיכומים נוצרים.
- כשל ב-AI לא מבטל את הסטטיסטי (sessions נפרדים).

**הערה מתודולוגית:** ה-job פותח `AsyncSessionLocal()` משלו ומבצע commit.
ה-commit הזה *לא* מתגלגל ע"י ה-conftest rollback fixture (שמגלגל רק את
ה-session של הבדיקה). לכן כל בדיקה שמריצה את ה-job חייבת לעשות cleanup
ידני של השורות שנכתבו ל-`daily_summaries` (ל-`ai_summaries` ה-job
משתמש בפונקציה שאנו monkey-patch, אז אין שם כתיבה אמיתית).
"""

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock

from sqlalchemy import delete, select

from app.models.ai_summary import AiSummary
from app.models.daily_summary import DailySummary
from app.utils.work_hours import to_israel_tz
from jobs import daily_summary as daily_summary_job


async def _cleanup_today_daily_summary(db) -> None:
    """מוחק את ה-row של daily_summaries לתאריך ישראל של עכשיו.

    ה-job פותח session משלו ומבצע commit; conftest rollback לא מטפל בזה.
    קוראים ל-helper הזה לפני ואחרי כל בדיקה שמריצה את ה-job, כדי שריצות
    חוזרות יראו DB ריק לאותו תאריך.
    """
    today_israel = to_israel_tz(datetime.now(timezone.utc)).date()
    await db.execute(
        delete(DailySummary).where(DailySummary.summary_date == today_israel)
    )
    await db.commit()


async def test_daily_cron_skips_when_should_skip(monkeypatch, db):
    """should_skip_daily_summary=True → לא נוצרים rows גם בסטטיסטי גם ב-AI."""
    await _cleanup_today_daily_summary(db)

    monkeypatch.setattr(
        daily_summary_job, "should_skip_daily_summary", lambda _now: True
    )
    fake_generate = AsyncMock()
    monkeypatch.setattr(
        daily_summary_job.summaries_service,
        "generate_and_store_daily_summary",
        fake_generate,
    )

    await daily_summary_job.daily_summary()

    # ה-AI לא נקרא (gating חתך בתחילה)
    fake_generate.assert_not_called()

    # אין row חדש ב-daily_summaries
    today_israel = to_israel_tz(datetime.now(timezone.utc)).date()
    row = (
        await db.execute(
            select(DailySummary).where(
                DailySummary.summary_date == today_israel
            )
        )
    ).scalar_one_or_none()
    assert row is None


async def test_daily_cron_generates_both_summaries(monkeypatch, db):
    """ריצה רגילה — סטטיסטי נכתב, ה-AI נקרא ומקבל commit."""
    await _cleanup_today_daily_summary(db)
    try:
        monkeypatch.setattr(
            daily_summary_job, "should_skip_daily_summary", lambda _now: False
        )

        placeholder = AiSummary(
            type="daily",
            date_range_start=date(2026, 5, 30),
            date_range_end=date(2026, 5, 30),
            input_data={},
            output={},
            model_used="fake",
        )
        fake_generate = AsyncMock(return_value=placeholder)
        monkeypatch.setattr(
            daily_summary_job.summaries_service,
            "generate_and_store_daily_summary",
            fake_generate,
        )

        await daily_summary_job.daily_summary()

        fake_generate.assert_awaited_once()

        # סטטיסטי קיים לתאריך ישראל של עכשיו
        today_israel = to_israel_tz(datetime.now(timezone.utc)).date()
        row = (
            await db.execute(
                select(DailySummary).where(
                    DailySummary.summary_date == today_israel
                )
            )
        ).scalar_one_or_none()
        assert row is not None
    finally:
        await _cleanup_today_daily_summary(db)


async def test_daily_cron_ai_failure_does_not_undo_statistical(monkeypatch, db):
    """ה-AI מחזיר None (כשל) → הסטטיסטי עדיין נכתב ל-DB."""
    await _cleanup_today_daily_summary(db)
    try:
        monkeypatch.setattr(
            daily_summary_job, "should_skip_daily_summary", lambda _now: False
        )
        fake_generate = AsyncMock(return_value=None)
        monkeypatch.setattr(
            daily_summary_job.summaries_service,
            "generate_and_store_daily_summary",
            fake_generate,
        )

        # לא אמור לזרוק חריגה למרות שה-AI החזיר None
        await daily_summary_job.daily_summary()

        # סטטיסטי כן נשמר (sessions נפרדים — commit ב-1 לפני ש-2 רץ)
        today_israel = to_israel_tz(datetime.now(timezone.utc)).date()
        row = (
            await db.execute(
                select(DailySummary).where(
                    DailySummary.summary_date == today_israel
                )
            )
        ).scalar_one_or_none()
        assert row is not None, (
            "סטטיסטי חייב להישמר גם כשה-AI נכשל"
        )
    finally:
        await _cleanup_today_daily_summary(db)
