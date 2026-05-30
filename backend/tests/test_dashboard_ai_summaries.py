"""
בדיקות ל-service של סיכומי AI בדשבורד (C.1/C.2 §6.8) —
get_latest_ai_summary + increment_inaccurate_count
(app/services/dashboard.py).

integration מול Postgres — מדלגות אם אין DB (fixture `db`). אין HTTP infra
בריפו, לכן בודקים את שכבת ה-service ישירות (עקבי עם test_summaries.py).
"""

from datetime import date, datetime, timezone

import pytest

from app.constants import SummaryType
from app.core.exceptions import NotFoundError
from app.models.ai_summary import AiSummary
from app.services import dashboard as dashboard_service

_NOW = datetime(2026, 5, 30, 16, 0, tzinfo=timezone.utc)


async def _mk_ai_summary(db, **kw) -> AiSummary:
    defaults = dict(
        type=SummaryType.WEEKLY.value,
        date_range_start=date(2026, 5, 24),
        date_range_end=date(2026, 5, 30),
        input_data={"user_prompt": "p"},
        output={"bottom_line": "סיכום.", "week_overview": "מבט-על."},
        model_used="claude-sonnet-4-6",
    )
    defaults.update(kw)
    summary = AiSummary(**defaults)
    db.add(summary)
    await db.flush()
    return summary


async def test_get_latest_ai_summary_by_type(db):
    """מחזיר את הסיכום הטרי ביותר מהסוג המבוקש; סוג אחר לא מתערב."""
    await _mk_ai_summary(
        db,
        type=SummaryType.WEEKLY.value,
        date_range_start=date(2026, 5, 17),
        date_range_end=date(2026, 5, 23),
    )
    newer = await _mk_ai_summary(
        db,
        type=SummaryType.WEEKLY.value,
        date_range_start=date(2026, 5, 24),
        date_range_end=date(2026, 5, 30),
    )
    # סיכום יומי קיים — לא אמור לחזור בשאילתת weekly:
    await _mk_ai_summary(
        db,
        type=SummaryType.DAILY.value,
        date_range_start=date(2026, 5, 30),
        date_range_end=date(2026, 5, 30),
    )

    got = await dashboard_service.get_latest_ai_summary(
        db, SummaryType.WEEKLY.value
    )
    assert got is not None
    assert got.id == newer.id  # הטרי ביותר לפי date_range_end


async def test_get_latest_ai_summary_none_when_empty(db):
    """אין סיכום מהסוג → None (לא שגיאה)."""
    got = await dashboard_service.get_latest_ai_summary(
        db, SummaryType.DAILY.value
    )
    assert got is None


async def test_increment_inaccurate_count_atomic(db):
    """לחיצה אחת מעלה את ה-counter ב-1."""
    summary = await _mk_ai_summary(db)
    assert summary.inaccurate_count == 0

    await dashboard_service.increment_inaccurate_count(db, summary.id)

    await db.refresh(summary)
    assert summary.inaccurate_count == 1


async def test_increment_inaccurate_count_accumulates(db):
    """ריבוי לחיצות מצטבר נכון."""
    summary = await _mk_ai_summary(db)
    for _ in range(3):
        await dashboard_service.increment_inaccurate_count(db, summary.id)

    await db.refresh(summary)
    assert summary.inaccurate_count == 3


async def test_increment_inaccurate_count_not_found(db):
    """id לא קיים → NotFoundError (הודעה גנרית בעברית, כלל 3)."""
    import uuid

    with pytest.raises(NotFoundError):
        await dashboard_service.increment_inaccurate_count(db, uuid.uuid4())
