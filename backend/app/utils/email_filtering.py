"""
סינון heuristic של מיילים לפני AI classifier — Phase 3 Stage 16.

לפי docs/phase-3-ai-token-management.md §"סינון לפני AI":
חוסך 40%+ קריאות AI ע"י זיהוי שולחים אוטומטיים (noreply, ניוזלטרים)
לפני שמשלמים על call ל-Anthropic.

**override:** אם בגוף המייל יש מילים שמעידות על פנייה אישית
(`PERSONAL_INQUIRY_KEYWORDS`), לא לסנן — שולחים ל-AI בכל זאת. ההפסד
של AI call אחד מיותר זול בהרבה מאובדן ליד אמיתי.
"""

import logging
import re

from app.constants import (
    PERSONAL_INQUIRY_KEYWORDS,
    SPAM_DOMAINS,
    SPAM_FROM_PATTERNS,
)

logger = logging.getLogger(__name__)


def is_likely_personal_inquiry(body: str) -> bool:
    """
    True אם בגוף המייל יש לפחות אחת ממילות המפתח שמעידות על פנייה
    אישית. case-insensitive, אבל עברית (heuristic — לא ב-Hebrew).

    משמש כ-override על שאר הסינון: גם אם השולח נראה אוטומטי, אם הגוף
    מכיל פנייה אישית — לא לסנן.
    """
    if not body:
        return False
    lowered = body.lower()
    for keyword in PERSONAL_INQUIRY_KEYWORDS:
        if keyword.lower() in lowered:
            return True
    return False


def is_heuristic_spam(from_addr: str | None, headers: dict | None) -> bool:
    """
    True אם השולח נראה כמערכת אוטומטית לפי 3 קריטריונים:
    1. from_addr מכיל אחת מ-SPAM_FROM_PATTERNS (noreply, newsletter@, וכו').
    2. domain של from_addr ב-SPAM_DOMAINS (mailchimp, sendgrid, וכו').
    3. headers מכיל `List-Unsubscribe` — סימן כמעט ודאי לניוזלטר.

    headers יכול להיות None (אם ה-caller לא העביר). אז רק 1+2 נבדקים.
    """
    if not from_addr:
        return False
    addr_lower = from_addr.lower()

    # 1. from patterns
    for pattern in SPAM_FROM_PATTERNS:
        if pattern in addr_lower:
            return True

    # 2. domain blacklist
    domain = _extract_domain(addr_lower)
    if domain and domain in SPAM_DOMAINS:
        return True

    # 3. List-Unsubscribe header. headers ב-Gmail API מגיע כ-list of
    # {"name": "...", "value": "..."} אבל לרוב ב-Python אנחנו ממירים
    # ל-dict רגיל. תומכים בשתי הצורות.
    if headers:
        if _has_header(headers, "List-Unsubscribe"):
            return True

    return False


def should_skip_ai_classification(
    from_addr: str | None,
    headers: dict | None,
    body: str,
) -> bool:
    """
    Pipeline: spam AND NOT personal_inquiry → skip AI.

    שימוש typical:
        if should_skip_ai_classification(from_addr, headers, body):
            label_as_spam_in_gmail()
            return  # לא יוצרים ליד, לא קוראים ל-AI
        result = await ai_client.classify_email(...)
    """
    if not is_heuristic_spam(from_addr, headers):
        return False
    if is_likely_personal_inquiry(body):
        # heuristic זיהה כספאם, אבל הגוף נראה אישי — לסמוך על AI.
        logger.info(
            "spam heuristic overridden by personal_inquiry: from=%s",
            from_addr,
        )
        return False
    return True


# תומך בשני פורמטים נפוצים של From header:
# 1. "user@domain.com" — plain
# 2. "Display Name <user@domain.com>" — RFC 2822, נפוץ ב-Gmail API
# הregex מחפש @ ואז את ה-domain עד whitespace/>/סוף, בלי anchor $.
_EMAIL_DOMAIN_RE = re.compile(r"@([\w.-]+?)(?:[>\s]|$)")


def _extract_domain(addr: str) -> str | None:
    """email@example.com → example.com. None אם פורמט לא תקין."""
    match = _EMAIL_DOMAIN_RE.search(addr)
    return match.group(1) if match else None


def _has_header(headers: dict, name: str) -> bool:
    """תומך גם ב-dict רגיל וגם ב-list של {"name": ..., "value": ...} מ-Gmail API."""
    if isinstance(headers, dict):
        # case-insensitive lookup
        name_lower = name.lower()
        return any(k.lower() == name_lower for k in headers.keys())
    if isinstance(headers, list):
        name_lower = name.lower()
        return any(
            isinstance(h, dict) and h.get("name", "").lower() == name_lower
            for h in headers
        )
    return False
