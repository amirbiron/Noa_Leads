"""
אימות וניהול של מספרי טלפון ישראליים.

מבוסס על: docs/Skills/israeli-phone-formatter/SKILL.md +
docs/Skills/israeli-phone-formatter/scripts/validate_phone.py

מה הסקיל מספק:
- patterns לכל סוגי המספרים בישראל (נייד, קווי, VoIP, 1-800, *XXXX)
- נירמול בין מקומי לבינלאומי (+972 ↔ 0)
- זיהוי 056/059 כפלסטיניים (נקבל, אבל מסומן)

מה אנחנו עושים פה (יותר רך מהסקיל):
- אם המספר נראה ישראלי (מתחיל ב-0 או +972) — אימות תבנית מלאה
- אחרת — מקבלים כמו שהוא (CRM יכול לקבל מספרים מחו"ל לסדנה לארגון)
"""

import re

# ----- patterns ראשיים, מעוטקים ישירות מ-validate_phone.py בסקיל -----
_PATTERNS = {
    # נייד: 10 ספרות, קידומת 050-056, 058, 059. 057 לא בשימוש.
    "mobile": re.compile(r"^0(5[012345689])\d{7}$"),
    # קווי: 9 ספרות, אזור 02-04, 08, 09
    "landline": re.compile(r"^0([2-4]|[89])\d{7}$"),
    # לא גיאוגרפי / VoIP: 10 ספרות, קידומת 072-079
    "voip": re.compile(r"^07[2-9]\d{7}$"),
    # חינם / פרימיום / שירות כוכבית — לא קורה לרוב ב-CRM, אבל תומכים.
    "toll_free": re.compile(r"^1800\d{6}$"),
    "premium": re.compile(r"^1700\d{6}$"),
    "star": re.compile(r"^\*\d{4,6}$"),
}

def _clean(phone: str) -> str:
    """הסר רווחים, מקפים, סוגריים, נקודות. ננרמל +972/972 ל-0 מוביל."""
    cleaned = re.sub(r"[\s\-\(\)\.]", "", phone)
    if cleaned.startswith("+972"):
        cleaned = "0" + cleaned[4:]
    elif cleaned.startswith("972") and len(cleaned) > 9:
        cleaned = "0" + cleaned[3:]
    return cleaned


def classify_israeli(phone: str) -> str | None:
    """
    מחזיר את סוג המספר אם הוא ישראלי תקין, אחרת None.
    הסוגים: "mobile" / "landline" / "voip" / "toll_free" / "premium" / "star".
    """
    cleaned = _clean(phone)
    for phone_type, pattern in _PATTERNS.items():
        if pattern.match(cleaned):
            return phone_type
    return None


def looks_like_israeli(phone: str) -> bool:
    """
    האם הקלט מתיימר להיות מספר ישראלי? כלומר מתחיל ב-0 / +972 / 972 / *.
    משמש להחלטה אם להחיל ולידציה מחמירה או לקבל את הקלט כפי שהוא.
    """
    s = re.sub(r"[\s\-\(\)\.]", "", phone)
    return (
        s.startswith("0")
        or s.startswith("+972")
        or s.startswith("972")
        or s.startswith("*")
    )


def format_for_display(phone: str) -> str:
    """
    מפרמט מספר ישראלי לתצוגה אחידה (`052-1234567`, `02-6251111`, `*2421`).
    אם המספר לא ישראלי — מחזיר אותו אחרי ניקוי תווים בלבד.
    """
    cleaned = _clean(phone)
    phone_type = classify_israeli(phone)
    if phone_type is None:
        # לא ישראלי — מחזירים כפי שהוא אחרי הניקוי הבסיסי
        return cleaned

    if phone_type == "landline":
        # 9 ספרות: 0X-XXXXXXX
        return f"{cleaned[:2]}-{cleaned[2:]}"
    if phone_type in ("mobile", "voip"):
        # 10 ספרות: 0XX-XXXXXXX
        return f"{cleaned[:3]}-{cleaned[3:]}"
    if phone_type == "toll_free":
        # 1-800-XXXXXX
        return f"1-800-{cleaned[4:]}"
    if phone_type == "premium":
        # 1-700-XXXXXX
        return f"1-700-{cleaned[4:]}"
    # star — אין hyphen
    return cleaned


def normalize_for_storage(phone: str | None) -> str | None:
    """
    הפונקציה המרכזית לאחסון במסד הנתונים:
    - None / "" → None
    - מספר ישראלי תקין → פורמט אחיד עם hyphen
    - מתיימר להיות ישראלי אבל לא תקין → ValueError בעברית
    - לא ישראלי → מחזיר אחרי ניקוי תווים, ללא כפיית פורמט (מאפשר חו"ל)

    הסדר: קודם classify (כולל 1-800/1-700/*XXXX שלא מזוהים ע"י
    looks_like_israeli המבוסס על prefix קלאסי). אם נכשל וגם נראה
    ישראלי — שגיאה. אחרת — pass-through.
    """
    if phone is None:
        return None
    s = phone.strip()
    if not s:
        return None

    if classify_israeli(s) is not None:
        return format_for_display(s)

    if looks_like_israeli(s):
        raise ValueError(
            "מספר טלפון לא תקין. נייד = 10 ספרות (05X), קווי = 9 ספרות (0X)."
        )

    # לא ישראלי — מקבלים כפי שהוא אחרי ניקוי
    return _clean(s)
