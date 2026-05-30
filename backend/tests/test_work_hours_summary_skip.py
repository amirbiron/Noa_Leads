"""
בדיקות לגייטינג של סיכומי ה-AI בשבת/חגים (C.1/C.2 §6.7).

pure — לא דורשות DB. בודקות את should_skip_daily_summary /
should_skip_weekly_summary ב-app/utils/work_hours.py.

כל הזמנים ב-UTC; ההמרה לישראל (IDT +3 בקיץ) נעשית בתוך הפונקציות.
"""

from datetime import datetime, timezone

from app.utils import work_hours as wh

# 2026-06-01 = יום שני, 2026-06-05 = שישי, 2026-06-06 = שבת.
# 16:00 UTC ≈ 19:00 IDT (שעת ה-cron היומי).
_MON_19 = datetime(2026, 6, 1, 16, 0, tzinfo=timezone.utc)
_FRI_19 = datetime(2026, 6, 5, 16, 0, tzinfo=timezone.utc)
_FRI_10 = datetime(2026, 6, 5, 7, 0, tzinfo=timezone.utc)   # ≈10:00 IDT (לפני 16:00)
_SAT_12 = datetime(2026, 6, 6, 9, 0, tzinfo=timezone.utc)   # שבת
_SUN_08 = datetime(2026, 6, 7, 5, 0, tzinfo=timezone.utc)   # ראשון ≈08:00 IDT


def test_daily_runs_on_regular_weekday():
    assert wh.should_skip_daily_summary(_MON_19) is False


def test_daily_skips_friday_after_cutoff():
    assert wh.should_skip_daily_summary(_FRI_19) is True


def test_daily_runs_friday_before_cutoff():
    # לפני 16:00 בשישי עדיין יום עבודה (אם כי ה-cron בפועל רץ ב-19:00).
    assert wh.should_skip_daily_summary(_FRI_10) is False


def test_daily_skips_saturday():
    assert wh.should_skip_daily_summary(_SAT_12) is True


def test_daily_skips_on_holiday(monkeypatch):
    # מאלצים is_holiday=True ליום שני הרגיל → דילוג.
    monkeypatch.setattr(wh, "is_holiday", lambda d: True)
    assert wh.should_skip_daily_summary(_MON_19) is True


def test_daily_skips_holiday_eve_after_cutoff(monkeypatch):
    # ערב חג (is_holiday_eve=True) ב-19:00 → דילוג (כמו ערב שבת).
    monkeypatch.setattr(wh, "is_holiday", lambda d: False)
    monkeypatch.setattr(wh, "is_holiday_eve", lambda d: True)
    assert wh.should_skip_daily_summary(_MON_19) is True


def test_weekly_runs_on_regular_sunday():
    assert wh.should_skip_weekly_summary(_SUN_08) is False


def test_weekly_skips_when_sunday_is_holiday(monkeypatch):
    monkeypatch.setattr(wh, "is_holiday", lambda d: True)
    assert wh.should_skip_weekly_summary(_SUN_08) is True


def test_weekly_does_not_skip_on_saturday_manual_run(monkeypatch):
    """§6.7 + cursor bugbot: דילוג רק כשראשון (יום ה-cron) הוא חג.
    ריצה ידנית בשבת (לבדיקה) אסור שתדלג — `is_saturday` הוסר מהתנאי."""
    monkeypatch.setattr(wh, "is_holiday", lambda d: False)
    assert wh.should_skip_weekly_summary(_SAT_12) is False
