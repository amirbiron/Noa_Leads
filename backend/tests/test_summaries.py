"""
בדיקות שכבת ה-orchestration של סיכומי AI — C.1/C.2 §6.4+§6.6
(app/services/summaries.py).

- unit: ולידציה + regen (§6.6) עם mock של שכבת ה-AI (בלי קריאת Claude אמיתית).
- integration: שמירה ב-ai_summaries מול Postgres — מדלגות אם אין DB (fixture `db`).
"""

from datetime import date, datetime, timezone

from app.constants import LeadStatus, SourceChannel, SummaryType
from app.models.ai_summary import AiSummary  # רישום הטבלה ב-Base.metadata
from app.models.lead import Lead
from app.services import ai, summaries
from app.services.ai import (
    AIError,
    AIRateLimitError,
    DailySummaryResult,
    WeeklySummaryResult,
)

# ===================== עזרי mock =====================

_USAGE = {"model": "claude-sonnet-4-6", "input_tokens": 100, "output_tokens": 50}


def _daily_result(**over) -> DailySummaryResult:
    defaults = dict(
        bottom_line="שורה תחתונה קצרה.",
        today="תיאור היום בקצרה.",
        highlights=[],
        needs_attention=[],
        tomorrow=None,
        omitted_sections=[],
    )
    defaults.update(over)
    return DailySummaryResult(**defaults)


def _make_fake_generate(results, usage=None):
    """
    fake generate_fn שמחזיר את results לפי הסדר (לכל קריאה). פריט שהוא
    Exception — נזרק (לסימולציית כשל/regen). usage ברירת מחדל = _USAGE.
    """
    calls = {"n": 0}
    seq = list(results)

    async def _fake(user_prompt: str):
        item = seq[calls["n"]]
        calls["n"] += 1
        if isinstance(item, Exception):
            raise item
        return item, (usage or _USAGE)

    _fake.calls = calls
    return _fake


# ===================== unit: ולידציה + regen (§6.6) =====================


async def test_regen_on_first_aierror_then_success():
    """כשל JSON ראשון (AIError) → regen → הצלחה. validation_warning=False."""
    fake = _make_fake_generate([AIError("bad json"), _daily_result()])
    out = await summaries._generate_validated(
        generate_fn=fake,
        user_prompt="prompt",
        input_names=set(),
        word_caps=summaries._DAILY_WORD_CAPS,
    )
    assert out is not None
    result, _usage, warning = out
    assert isinstance(result, DailySummaryResult)
    assert warning is False
    assert fake.calls["n"] == 2  # ניסיון + regen


async def test_double_aierror_returns_none():
    """כשל JSON גם אחרי regen → None (§6.6#1)."""
    fake = _make_fake_generate([AIError("bad"), AIError("bad again")])
    out = await summaries._generate_validated(
        generate_fn=fake,
        user_prompt="p",
        input_names=set(),
        word_caps=summaries._DAILY_WORD_CAPS,
    )
    assert out is None
    assert fake.calls["n"] == 2


async def test_rate_limit_returns_none_without_regen():
    """AIRateLimitError → None מיד, בלי regen (עקבי עם dormant)."""
    fake = _make_fake_generate([AIRateLimitError("429"), _daily_result()])
    out = await summaries._generate_validated(
        generate_fn=fake,
        user_prompt="p",
        input_names=set(),
        word_caps=summaries._DAILY_WORD_CAPS,
    )
    assert out is None
    assert fake.calls["n"] == 1  # לא היה regen


async def test_unknown_name_sets_validation_warning():
    """
    שם בפלט שלא בקלט → regen; אם נמשך → נשמר עם validation_warning=True (§6.6#3).
    """
    bad = _daily_result(today="דיברתי עם דנה על העסקה.")  # "דנה" לא בקלט
    fake = _make_fake_generate([bad, bad])  # נמשך גם אחרי regen
    out = await summaries._generate_validated(
        generate_fn=fake,
        user_prompt="prompt without that name",
        input_names={"מירב כהן"},
        word_caps=summaries._DAILY_WORD_CAPS,
    )
    assert out is not None
    _result, _usage, warning = out
    assert warning is True
    assert fake.calls["n"] == 2  # ניסה regen


async def test_known_name_no_warning():
    """שם בפלט שכן בקלט → אין warning, אין regen."""
    good = _daily_result(today="חזרתי למירב כהן בנוגע להצעה.")
    fake = _make_fake_generate([good])
    out = await summaries._generate_validated(
        generate_fn=fake,
        user_prompt="p",
        input_names={"מירב כהן"},
        word_caps=summaries._DAILY_WORD_CAPS,
    )
    assert out is not None
    _r, _u, warning = out
    assert warning is False
    assert fake.calls["n"] == 1


async def test_shel_possessive_does_not_trigger_false_positive():
    """
    regression: יחס הקניין "של" בעברית נפוץ לפני שמות עצם רגילים
    (לא רק לפני שמות אנשים), ולכן הוצא מתבנית "שמות חשודים". סיכום
    תקין שמשתמש ב"של" בהקשרים רגילים לא יקבל validation_warning כשיש
    שמות-קלט אמיתיים.
    """
    # "של החודש", "של השבוע" — שניהם פוסיביים תקינים שאינם שמות אנשים.
    valid = _daily_result(
        today="זו הייתה ההצעה של החודש, ופייסבוק שמרה על המקום של השבוע."
    )
    fake = _make_fake_generate([valid])
    out = await summaries._generate_validated(
        generate_fn=fake,
        user_prompt="p",
        input_names={"מירב כהן"},  # יש שמות-קלט → ה-validator פעיל
        word_caps=summaries._DAILY_WORD_CAPS,
    )
    assert out is not None
    _r, _u, warning = out
    assert warning is False  # ה"של" החוקיים לא הופכים את הסיכום ל"חשוד"
    assert fake.calls["n"] == 1  # אין regen על קניין תקין


async def test_grossly_over_limit_triggers_regen_then_kept():
    """
    סקציה שחרגה פי-3+ ממכסה → regen; אם נמשך → נשמר בלי חיתוך (§6.6#2).
    """
    # bottom_line מכסה 40 מילים → פי-3 = 120. ניצור 130 מילים בנות תו אחד כדי
    # לחרוג בספירת-מילים בלי לחרוג ממגבלת 280 התווים של Pydantic (259 תווים).
    long_text = " ".join(["א"] * 130)
    over = _daily_result(bottom_line=long_text)
    fake = _make_fake_generate([over, over])
    out = await summaries._generate_validated(
        generate_fn=fake,
        user_prompt="p",
        input_names=set(),
        word_caps=summaries._DAILY_WORD_CAPS,
    )
    assert out is not None
    result, usage, _w = out
    # לא נחתך — הטקסט הארוך נשמר כמו שהוא (§6.6: "חיתוך טקסט: לעולם לא").
    assert result.bottom_line == long_text
    assert fake.calls["n"] == 2  # ניסה regen פעם אחת
    # טוקנים נצברים על פני שתי הקריאות (regen לא מאבד את טוקני הקריאה הראשונה).
    assert usage["input_tokens"] == 200  # 2 × 100
    assert usage["output_tokens"] == 100  # 2 × 50
    assert usage["model"] == "claude-sonnet-4-6"  # model מהקריאה האחרונה


async def test_single_call_usage_not_doubled():
    """קריאה אחת מוצלחת — הטוקנים נשארים כפי שהם (בלי צבירה מיותרת)."""
    fake = _make_fake_generate([_daily_result()])
    out = await summaries._generate_validated(
        generate_fn=fake,
        user_prompt="p",
        input_names=set(),
        word_caps=summaries._DAILY_WORD_CAPS,
    )
    assert out is not None
    _r, usage, _w = out
    assert usage["input_tokens"] == 100
    assert usage["output_tokens"] == 50


def test_extract_input_names():
    """חילוץ שמות מהבלוקים בקלט (§6.6#3)."""
    prompt = (
        "לידים בולטים שזוהו בקוד:\n"
        "- שם: מירב כהן | קטגוריה: שיקום קול | אירוע: ענתה\n"
        "פריטים שדורשים תשומת לב:\n"
        "- סוג: הצעה ללא מענה | ליד: דניאל מהבימה | ימים מאז שליחה: 5\n"
        "הצעת פוקוס למחר:\n"
        "- ליד שדורש פוקוס: מאיה מאולפני הצליל (ארגוני)\n"
    )
    names = summaries._extract_input_names(prompt)
    assert "מירב כהן" in names
    assert "דניאל מהבימה" in names
    assert "מאיה מאולפני הצליל" in names
    assert "-" not in names
    assert "ללא" not in names


# ===================== integration (DB) =====================


async def _mk_lead(db, **kw) -> Lead:
    defaults = dict(
        full_name="ליד בדיקה",
        source_channel=SourceChannel.MANUAL.value,
        status=LeadStatus.IN_PROGRESS.value,
    )
    defaults.update(kw)
    lead = Lead(**defaults)
    db.add(lead)
    await db.flush()
    return lead


_NOW = datetime(2026, 5, 30, 16, 0, tzinfo=timezone.utc)


async def test_store_daily_summary_persists(db, monkeypatch):
    """generate_and_store_daily_summary שומר row ב-ai_summaries עם type/range."""
    await _mk_lead(db, created_at=_NOW)

    monkeypatch.setattr(
        ai, "generate_daily_summary_text", _make_fake_generate([_daily_result()])
    )
    summary = await summaries.generate_and_store_daily_summary(db, now_utc=_NOW)

    assert summary is not None
    assert summary.type == SummaryType.DAILY.value
    assert summary.date_range_start == date(2026, 5, 30)
    assert summary.date_range_end == date(2026, 5, 30)
    assert summary.model_used == "claude-sonnet-4-6"
    assert summary.tokens_in == 100
    assert summary.output["bottom_line"] == "שורה תחתונה קצרה."
    assert summary.input_data["user_prompt"]  # נשמר ה-prompt המבושל


async def test_store_daily_summary_first_write_wins(db, monkeypatch):
    """ריצה שנייה באותו תאריך לא יוצרת כפילות ולא דורסת inaccurate_count."""
    from sqlalchemy import func, select

    await _mk_lead(db, created_at=_NOW)
    monkeypatch.setattr(
        ai, "generate_daily_summary_text", _make_fake_generate([_daily_result()])
    )
    first = await summaries.generate_and_store_daily_summary(db, now_utc=_NOW)

    # מדמים לחיצת "לא מדויק" → מעלים את ה-counter (flush בלבד; ה-fixture
    # מנקה ב-rollback, וה-service עצמו עושה flush ולא commit):
    first.inaccurate_count = 5
    await db.flush()

    # ריצה שנייה — ה-idempotency check אמור לדלג על ה-AI לגמרי. נתקין fake
    # שמתפוצץ אם נקרא, כדי להוכיח שלא בוזבזה קריאת generation:
    second_fake = _make_fake_generate([_daily_result(bottom_line="גרסה חדשה.")])
    monkeypatch.setattr(ai, "generate_daily_summary_text", second_fake)
    second = await summaries.generate_and_store_daily_summary(db, now_utc=_NOW)

    assert second_fake.calls["n"] == 0  # ה-AI לא נקרא בריצה השנייה (idempotency)
    count = (
        await db.execute(select(func.count()).select_from(AiSummary))
    ).scalar_one()
    assert count == 1  # בלי כפילות
    assert second.id == first.id
    assert second.inaccurate_count == 5  # לא נדרס
    assert second.output["bottom_line"] == "שורה תחתונה קצרה."  # הגרסה המקורית


async def test_store_daily_summary_none_on_ai_failure(db, monkeypatch):
    """כשל AI סופי → None, ושום row לא נשמר."""
    from sqlalchemy import func, select

    await _mk_lead(db, created_at=_NOW)
    monkeypatch.setattr(
        ai,
        "generate_daily_summary_text",
        _make_fake_generate([AIError("x"), AIError("y")]),
    )
    out = await summaries.generate_and_store_daily_summary(db, now_utc=_NOW)

    assert out is None
    count = (
        await db.execute(select(func.count()).select_from(AiSummary))
    ).scalar_one()
    assert count == 0


async def test_store_weekly_summary_range(db, monkeypatch):
    """generate_and_store_weekly_summary — טווח השבוע הקודם (ראשון→שבת)."""
    weekly = WeeklySummaryResult(
        bottom_line="סיכום שבועי.",
        week_overview="מבט-על על השבוע.",
        trends_vs_last_week=None,
        what_worked=[],
        what_stuck=[],
        next_week_focus=None,
        omitted_sections=[],
    )
    monkeypatch.setattr(
        ai, "generate_weekly_summary_text", _make_fake_generate([weekly])
    )
    # ריצת ראשון 2026-05-31 → מסכמת את השבוע 2026-05-24..2026-05-30.
    sunday = datetime(2026, 5, 31, 5, 0, tzinfo=timezone.utc)
    summary = await summaries.generate_and_store_weekly_summary(db, now_utc=sunday)

    assert summary is not None
    assert summary.type == SummaryType.WEEKLY.value
    assert summary.date_range_start == date(2026, 5, 24)
    assert summary.date_range_end == date(2026, 5, 30)
    assert summary.output["week_overview"] == "מבט-על על השבוע."
