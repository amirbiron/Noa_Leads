"""
summaries — שכבת ה-orchestration לסיכומי AI (C.1 יומי / C.2 שבועי, §6.4).

מחברת בין שלוש שכבות קיימות:
1. שכבת חישוב — build_daily_user_prompt / build_weekly_user_prompt (summary_inputs).
2. שכבת AI — generate_daily_summary_text / generate_weekly_summary_text (ai).
3. שכבת DB — טבלת ai_summaries (§6.5).

הזרימה (§6.4): אסוף קלט מבושל → קרא ל-Claude → ולידציה (§6.6) → regen פעם
אחת בכשל → שמור ב-DB. כשל סופי → None ("סיכום לא זמין כרגע" ב-UI).

עיקרון "AI מפרש, לא מחשב" — כל הנתונים כבר חושבו בשכבת summary_inputs; כאן
רק קוראים ל-AI ושומרים.
"""

import logging
import re
from datetime import date, datetime, timedelta, timezone

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import SummaryType
from app.models.ai_summary import AiSummary
from app.services import ai
from app.services.ai import AIError, AIRateLimitError
from app.services.summary_inputs import (
    _last_week_bounds,
    build_daily_user_prompt,
    build_weekly_user_prompt,
    to_israel_tz,
)

logger = logging.getLogger("services.summaries")

# יום אחד — לחישוב שבת (end inclusive) מתוך ה-end exclusive (ראשון הבא).
_ONE_DAY = timedelta(days=1)

# מכסות-מילים פר-סקציה (§3.4). הולידציה (§6.6#2) עושה regen רק בחריגה של פי-3+,
# ולעולם לא חותכת טקסט. ערכי list הם מכסה *לכל פריט* ברשימה.
_DAILY_WORD_CAPS: dict[str, int] = {
    "bottom_line": 40,
    "highlights": 40,
    "needs_attention": 30,
    "tomorrow": 50,
}
_WEEKLY_WORD_CAPS: dict[str, int] = {
    "bottom_line": 50,
    "week_overview": 100,
    "trends_vs_last_week": 120,
    "what_worked": 40,
    "what_stuck": 40,
    "next_week_focus": 60,
}

# חריגה שמעליה עושים regen (§6.6#2: "פי 3+ מהמכסה").
_WORD_CAP_REGEN_FACTOR = 3


def _count_words(text: str) -> int:
    return len(text.split())


def _section_grossly_over_limit(
    result: BaseModel, caps: dict[str, int]
) -> bool:
    """
    True אם איזושהי סקציה חרגה פי-3+ ממכסת-המילים שלה (§6.6#2). שדות None
    מדולגים; שדות list נבדקים פר-פריט מול אותה מכסה.
    """
    data = result.model_dump()
    for field, cap in caps.items():
        value = data.get(field)
        if value is None:
            continue
        threshold = cap * _WORD_CAP_REGEN_FACTOR
        if isinstance(value, list):
            if any(_count_words(item) > threshold for item in value):
                return True
        elif isinstance(value, str):
            if _count_words(value) > threshold:
                return True
    return False


# תבניות לחילוץ "שמות חשודים" מהפלט (§6.6#3). פרשנות פרקטית: אין NER עברי,
# לכן מזהים את קבוצת השמות שהוזרקו לקלט (מהבלוקים) ובודקים שכל שם שמופיע
# בפלט קיים גם בה. שמרני בכוונה — עדיף לא לחסום (false-negative) על regen מיותר.
# מחלצים מהקלט את הערכים שאחרי "שם:", "ליד:", ו-"ליד שדורש פוקוס:".
#
# pattern 3 (`ליד שדורש פוקוס:`) עוצר ב-`|` *או* `(`, defense-in-depth:
# `lead_id:` של פיצ'ר ההיפר-קישור מתווסף עם separator `|` ולא היה עוצר את
# pattern 3 הישן שעצר רק ב-`(`. ה-format ב-summary_inputs.py מציב כעת את
# ה-`(kind)` לפני ה-`| lead_id:`, אז גם ה-regex *וגם* ה-format שלוחים את
# התלות, ולא רק אחד מהם.
_INPUT_NAME_PATTERNS = (
    re.compile(r"שם:\s*([^|\n]+?)\s*(?:\||$)", re.MULTILINE),
    re.compile(r"ליד:\s*([^|\n]+?)\s*(?:\||$)", re.MULTILINE),
    re.compile(r"ליד שדורש פוקוס:\s*([^(|\n]+?)\s*(?:[(|]|$)", re.MULTILINE),
)


def _extract_input_names(user_prompt: str) -> set[str]:
    """
    קבוצת ה-display-names שהוזרקו לקלט (מהבלוקים של highlighted/attention/
    tomorrow). משמשת לולידציית-שמות (§6.6#3): שם בפלט שאינו כאן = חשד להזיה.
    """
    names: set[str] = set()
    for pattern in _INPUT_NAME_PATTERNS:
        for match in pattern.findall(user_prompt):
            name = match.strip()
            # מסננים placeholders ריקים/גנריים שאינם שמות אמיתיים.
            if name and name not in {"-", "ללא", "(ריק)"}:
                names.add(name)
    return names


# שמות "חשודים" בפלט: רצף מילים בעברית אחרי תבנית התייחסות לליד. שמרני —
# תופס את המקרים הברורים ("הליד דניאל", "עם מירב כהן") בלי לנסות NER מלא.
# הוצא "של" מהתבנית: יחס הקניין בעברית נפוץ מאוד לפני שמות עצם רגילים
# ("של החודש", "של הלקוחות", "של השבוע") → false positives על כל סיכום
# שמכיל שמות-קלט אמיתיים בקבוצת ה-input_names. עדיף לפספס "שם חשוד" אחרי
# "של" (כיסוי חלקי) על להעלות validation_warning על סיכומים תקינים.
_OUTPUT_NAME_PATTERN = re.compile(
    r"(?:הליד|הלקוח|הלקוחה|עם)\s+([א-ת]+(?:\s+[א-ת]+){0,2})"
)


def _output_has_unknown_name(result: BaseModel, input_names: set[str]) -> bool:
    """
    True אם בפלט מופיע "שם חשוד" שאינו תת-מחרוזת של אף שם-קלט (§6.6#3).
    בדיקה שמרנית: רק אם השם החשוד אינו מוכל באף שם מהקלט נחשיב כהזיה.
    """
    if not input_names:
        return False  # אין שמות בקלט → אין מול מה להשוות (לא חוסמים).
    data = result.model_dump()
    texts: list[str] = []
    for value in data.values():
        if isinstance(value, str):
            texts.append(value)
        elif isinstance(value, list):
            texts.extend(v for v in value if isinstance(v, str))

    for text in texts:
        for candidate in _OUTPUT_NAME_PATTERN.findall(text):
            cand = candidate.strip()
            # מוכר אם ה-candidate מוכל באחד משמות-הקלט (או ההפך — שם-קלט בו).
            known = any(
                cand in name or name in cand for name in input_names
            )
            if not known:
                return True
    return False


async def _generate_validated(
    *,
    generate_fn,
    user_prompt: str,
    input_names: set[str],
    word_caps: dict[str, int],
) -> tuple[BaseModel, dict, bool] | None:
    """
    מריץ generate_fn עם ולידציה ו-regen פעם אחת (§6.6). מחזיר
    (result, usage, validation_warning) או None בכשל סופי.

    regen מתבצע פעם אחת בלבד (max 2 קריאות) על כל אחד מ:
    1. JSON/schema לא תקין (generate_fn זורק AIError).
    2. סקציה שחרגה פי-3+ ממכסה.
    3. שם בפלט שלא בקלט.
    אם הבעיה נמשכת אחרי regen: שמות → validation_warning=True (שומרים); אורך →
    שומרים בלי חיתוך; JSON → None. AIRateLimitError → None בלי regen.

    טוקנים: ה-usage המוחזר צובר את הטוקנים של *כל* הקריאות (כולל regen מבוזבז),
    כדי ש-tokens_in/out ב-ai_summaries ישקפו את העלות המלאה. השדה model נשאר
    מהקריאה הסופית (זו שתוצאתה נשמרת).
    """
    last_result: BaseModel | None = None
    # צובר טוקנים על פני כל הקריאות (כולל regen מבוזבז) — finding: regen drops
    # first call tokens. ה-usage הסופי מוחזר עם הסכום, model מהקריאה האחרונה.
    cumulative_in = 0
    cumulative_out = 0
    last_usage: dict | None = None

    for attempt in range(2):  # ניסיון ראשון + regen אחד
        try:
            result, usage = await generate_fn(user_prompt)
        except AIRateLimitError:
            logger.warning("summary generation hit rate limit — skipping")
            return None
        except AIError as e:
            if attempt == 0:
                logger.warning("summary generation invalid, regen: %s", e)
                continue
            logger.error("summary generation failed after regen: %s", e)
            return None

        cumulative_in += usage.get("input_tokens") or 0
        cumulative_out += usage.get("output_tokens") or 0
        merged_usage = {
            **usage,
            "input_tokens": cumulative_in,
            "output_tokens": cumulative_out,
        }
        last_result, last_usage = result, merged_usage

        over_limit = _section_grossly_over_limit(result, word_caps)
        unknown_name = _output_has_unknown_name(result, input_names)

        if not over_limit and not unknown_name:
            return result, merged_usage, False  # נקי

        if attempt == 0:
            logger.warning(
                "summary validation issue (over_limit=%s unknown_name=%s), regen",
                over_limit,
                unknown_name,
            )
            continue

        # אחרי regen הבעיה נמשכת — §6.6: לא חותכים. שם לא מוכר → warning.
        return last_result, last_usage, unknown_name

    # לא אמור להגיע לכאן (הלולאה תמיד מחזירה), אך ליתר ביטחון:
    if last_result is not None and last_usage is not None:
        return last_result, last_usage, False
    return None


async def _get_existing_summary(
    db: AsyncSession,
    *,
    summary_type: str,
    range_start: date,
    range_end: date,
) -> AiSummary | None:
    """
    מחזיר סיכום קיים לטווח (אם יש), אחרת None. נקרא *לפני* הקריאה ל-AI כדי
    לא לבזבז generation על טווח שכבר סוכם (first-write-wins ב-DB ממילא לא
    ידרוס, אבל הקריאה ל-Claude עולה כסף וזמן). idempotency אמיתי = דילוג מוקדם.
    """
    return (
        await db.execute(
            select(AiSummary).where(
                AiSummary.type == summary_type,
                AiSummary.date_range_start == range_start,
                AiSummary.date_range_end == range_end,
            )
        )
    ).scalar_one_or_none()


async def _store_summary(
    db: AsyncSession,
    *,
    summary_type: str,
    range_start: date,
    range_end: date,
    user_prompt: str,
    result: BaseModel,
    usage: dict,
    validation_warning: bool,
) -> AiSummary:
    """
    שומר את הסיכום ב-ai_summaries עם first-write-wins (ON CONFLICT DO NOTHING
    על הטווח). אם כבר קיים row לאותו טווח — מחזיר אותו בלי לדרוס (שומר על
    inaccurate_count של נועה). מחזיר את ה-AiSummary (חדש או קיים).

    עושה flush בלבד — ה-commit באחריות ה-caller (ה-job שבעל ה-session). כך
    גבול הטרנזקציה נשלט במקום אחד, וגם בדיקות יכולות לרוץ תחת rollback fixture.
    """
    stmt = (
        pg_insert(AiSummary)
        .values(
            type=summary_type,
            date_range_start=range_start,
            date_range_end=range_end,
            input_data={"user_prompt": user_prompt},
            output=result.model_dump(),
            model_used=usage.get("model") or "unknown",
            tokens_in=usage.get("input_tokens"),
            tokens_out=usage.get("output_tokens"),
            validation_warning=validation_warning,
        )
        .on_conflict_do_nothing(
            constraint="uq_ai_summaries_type_range"
        )
    )
    await db.execute(stmt)
    await db.flush()

    # טוענים מחדש (בין אם נכתב עכשיו ובין אם כבר היה קיים) — מקור אמת יחיד.
    existing = (
        await db.execute(
            select(AiSummary).where(
                AiSummary.type == summary_type,
                AiSummary.date_range_start == range_start,
                AiSummary.date_range_end == range_end,
            )
        )
    ).scalar_one()
    return existing


async def generate_and_store_daily_summary(
    db: AsyncSession, now_utc: datetime | None = None
) -> AiSummary | None:
    """
    מייצר סיכום יומי (C.1) ושומר ב-ai_summaries. הטווח = יום-הלוח בישראל.
    מחזיר את ה-AiSummary, או None בכשל AI (UI יציג "סיכום לא זמין כרגע").

    עושה flush בלבד — ה-caller אחראי על ה-commit (גבול טרנזקציה אחד).
    """
    now_utc = now_utc or datetime.now(timezone.utc)
    day = to_israel_tz(now_utc).date()

    # idempotency: אם כבר קיים סיכום ליום הזה — מחזירים אותו בלי לקרוא ל-AI
    # (חוסך generation מבוזבז; first-write-wins ב-DB ממילא לא היה דורס).
    existing = await _get_existing_summary(
        db, summary_type=SummaryType.DAILY.value, range_start=day, range_end=day
    )
    if existing is not None:
        logger.info("daily summary already exists for %s — skipping AI", day)
        return existing

    user_prompt = await build_daily_user_prompt(db, now_utc)

    validated = await _generate_validated(
        generate_fn=ai.generate_daily_summary_text,
        user_prompt=user_prompt,
        input_names=_extract_input_names(user_prompt),
        word_caps=_DAILY_WORD_CAPS,
    )
    if validated is None:
        logger.error("daily summary unavailable (AI failure)")
        return None
    result, usage, warning = validated

    summary = await _store_summary(
        db,
        summary_type=SummaryType.DAILY.value,
        range_start=day,
        range_end=day,
        user_prompt=user_prompt,
        result=result,
        usage=usage,
        validation_warning=warning,
    )
    logger.info(
        "daily summary stored: date=%s model=%s tokens_in=%s tokens_out=%s warning=%s",
        day,
        usage.get("model"),
        usage.get("input_tokens"),
        usage.get("output_tokens"),
        warning,
    )
    return summary


async def generate_and_store_weekly_summary(
    db: AsyncSession, now_utc: datetime | None = None
) -> AiSummary | None:
    """
    מייצר סיכום שבועי (C.2) ושומר ב-ai_summaries. הטווח = השבוע הקודם המלא
    (ראשון→שבת). מחזיר את ה-AiSummary, או None בכשל AI.

    עושה flush בלבד — ה-caller אחראי על ה-commit (גבול טרנזקציה אחד).
    """
    now_utc = now_utc or datetime.now(timezone.utc)

    # טווח התצוגה זהה ל-build_weekly_user_prompt: ראשון (start) עד שבת
    # (end exclusive פחות יום). _last_week_bounds מחזיר UTC; ממירים לתאריך ישראל.
    week_start_utc, week_end_utc = _last_week_bounds(now_utc)
    range_start = to_israel_tz(week_start_utc).date()
    range_end = to_israel_tz(week_end_utc).date() - _ONE_DAY

    # idempotency: אם כבר קיים סיכום לשבוע הזה — מחזירים אותו בלי לקרוא ל-AI.
    existing = await _get_existing_summary(
        db,
        summary_type=SummaryType.WEEKLY.value,
        range_start=range_start,
        range_end=range_end,
    )
    if existing is not None:
        logger.info(
            "weekly summary already exists for %s..%s — skipping AI",
            range_start,
            range_end,
        )
        return existing

    user_prompt = await build_weekly_user_prompt(db, now_utc)

    validated = await _generate_validated(
        generate_fn=ai.generate_weekly_summary_text,
        user_prompt=user_prompt,
        input_names=_extract_input_names(user_prompt),
        word_caps=_WEEKLY_WORD_CAPS,
    )
    if validated is None:
        logger.error("weekly summary unavailable (AI failure)")
        return None
    result, usage, warning = validated

    summary = await _store_summary(
        db,
        summary_type=SummaryType.WEEKLY.value,
        range_start=range_start,
        range_end=range_end,
        user_prompt=user_prompt,
        result=result,
        usage=usage,
        validation_warning=warning,
    )
    logger.info(
        "weekly summary stored: range=%s..%s model=%s tokens_in=%s tokens_out=%s warning=%s",
        range_start,
        range_end,
        usage.get("model"),
        usage.get("input_tokens"),
        usage.get("output_tokens"),
        warning,
    )
    return summary
