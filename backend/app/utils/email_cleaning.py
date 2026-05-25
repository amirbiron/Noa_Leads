"""
ניקוי תוכן מייל לפני שליחה ל-AI — Phase 3 Stage 16.

לקח קריטי מ-EmailFlow: מיילים גולמיים עם HTML inline (Smoove/Mailchimp,
טפסים אוטומטיים) שיכלו לצרוך 10-12K input tokens במקום ~1.5K המצופה.
פי 8 מהנדרש = חריגת TPM, דחיות 429, ולידים שלא סווגו.

מפרט מלא: docs/phase-3-ai-token-management.md.

**אסור** להעביר HTML גולמי ישירות ל-classify_email/summarize_*/extract_*.
כל מסלול שמעביר תוכן מייל ל-AI חייב לעבור דרך הפונקציה הזו קודם.
"""

import logging
import re
from typing import Literal

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


# תקרות per-purpose. ל-classifier 1,200 תווים מספיקים (AI יכול
# להחליט אם מייל עסקי מ-800-1,000 תווים ראשונים). לסיכום/חילוץ —
# יותר context.
_MAX_CHARS_BY_PURPOSE: dict[str, int] = {
    "classification": 1_200,
    "summary": 2_000,
    "extraction": 2_500,
}

# elements ב-HTML שאינם תוכן — מוסרים תמיד.
_NON_CONTENT_TAGS = ("script", "style", "head", "meta", "link", "noscript")

# class/id substrings שמעידים על noise (footer, unsubscribe, וכו') — מוסרים best-effort.
_NOISE_PATTERNS = (
    "footer",
    "unsubscribe",
    "tracking",
    "social-links",
    "preheader",
    "header-logo",
)

# URL ארוך (100+ תווים) → "[link]". חוסך 30-40% מהטוקנים בניוזלטרים
# שמלאים ב-UTM tags ו-tracking IDs.
_LONG_URL_RE = re.compile(r"https?://[^\s]{100,}")

# רצף whitespace → רווח יחיד.
_WS_RE = re.compile(r"\s+")

# שורה ריקה / רק רווחים / רק תווי בקרה.
_EMPTY_LINE_RE = re.compile(r"^[\s​-‏]*$")

# שאריות URL (זנבות אחרי [link]) או רעש encoding.
_URL_TAIL_RE = re.compile(r"^[?&][\w=&.%-]+$")

_TRUNCATED_SUFFIX = "\n\n[הטקסט קוצר]"


def clean_email_body_for_ai(
    raw_content: str,
    purpose: Literal["classification", "summary", "extraction"] = "classification",
) -> tuple[str, dict]:
    """
    מנקה תוכן מייל גולמי (HTML או טקסט) להעברה ל-AI.

    מחזיר tuple של (טקסט נקי, metadata) — ה-metadata כולל raw_len,
    cleaned_len, ratio, truncated, purpose. ה-caller יכול לרשום אותו
    ב-log או ב-`email_messages.cleaning_metadata` (כשתיווצר הטבלה ב-Stage 18).

    raw_content יכול להיות None/ריק — מחזיר ('', metadata עם ratio=0).
    """
    if not raw_content:
        return "", _build_metadata(0, 0, False, purpose)

    max_chars = _MAX_CHARS_BY_PURPOSE.get(purpose, 1_200)
    raw_len = len(raw_content)

    # 1. פרסור HTML — lxml מהיר, אבל לא תמיד מותקן; fallback ל-html.parser.
    soup = _parse_html(raw_content)

    # 2. הסרת tags שאינם תוכן.
    for tag_name in _NON_CONTENT_TAGS:
        for tag in soup.find_all(tag_name):
            tag.decompose()

    # 3. הסרת elements לפי class/id (best-effort — לא לזרוק אם לא נמצא).
    for noise in _NOISE_PATTERNS:
        for el in soup.find_all(class_=re.compile(noise, re.IGNORECASE)):
            el.decompose()
        for el in soup.find_all(id=re.compile(noise, re.IGNORECASE)):
            el.decompose()

    # 4. חילוץ טקסט.
    text = soup.get_text(separator=" ", strip=True)

    # 5. URLs ארוכים → [link].
    text = _LONG_URL_RE.sub("[link]", text)

    # 6. קריסת whitespace.
    text = _WS_RE.sub(" ", text)

    # 7. הסרת שורות שהן רק רעש (תווי בקרה / זנב URL / encoding מוזר).
    #    אחרי קריסת ה-whitespace כל הטקסט בשורה אחת, אז זה גם מסנן
    #    sequences כמו "?utm_source=&utm_medium=" שנשארו תלושים.
    lines = [ln for ln in text.split("\n") if not _is_noise_line(ln)]
    text = "\n".join(lines).strip()

    # 8. truncation בטיחותי.
    truncated = False
    if len(text) > max_chars:
        text = text[: max_chars - len(_TRUNCATED_SUFFIX)] + _TRUNCATED_SUFFIX
        truncated = True

    cleaned_len = len(text)
    metadata = _build_metadata(raw_len, cleaned_len, truncated, purpose)

    # לוג מובנה לזיהוי אם יש סוגי מיילים שהניקוי לא מטפל בהם טוב.
    # email_id מתווסף ע"י ה-caller (אנחנו לא יודעים אותו פה).
    logger.info(
        "email_clean purpose=%s raw_len=%d cleaned_len=%d ratio=%.2f truncated=%s",
        purpose,
        raw_len,
        cleaned_len,
        metadata["ratio"],
        truncated,
    )

    return text, metadata


def _parse_html(raw_content: str) -> BeautifulSoup:
    """lxml אם זמין, אחרת html.parser. לא מפיל את האפליקציה אם lxml חסר."""
    try:
        return BeautifulSoup(raw_content, "lxml")
    except Exception:
        return BeautifulSoup(raw_content, "html.parser")


def _is_noise_line(line: str) -> bool:
    """שורה שהיא בעיקר רעש — תווי בקרה ריקים / שאריות URL / רווחים."""
    stripped = line.strip()
    if not stripped:
        return True
    if _EMPTY_LINE_RE.match(stripped):
        return True
    if _URL_TAIL_RE.match(stripped):
        return True
    return False


def _build_metadata(
    raw_len: int, cleaned_len: int, truncated: bool, purpose: str
) -> dict:
    ratio = cleaned_len / raw_len if raw_len > 0 else 0.0
    return {
        "purpose": purpose,
        "raw_len": raw_len,
        "cleaned_len": cleaned_len,
        "ratio": round(ratio, 4),
        "truncated": truncated,
    }
