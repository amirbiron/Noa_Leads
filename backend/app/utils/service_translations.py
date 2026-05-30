"""
תרגום ערכי enum של שירות לעברית — לשימוש בכל מקום שמעביר אותם ל-AI.

ה-enums (ServiceCategory / service_subtype) נשמרים באנגלית ב-DB, אבל כשמעבירים
אותם ל-prompt של AI (§19.3 D.1, וגם D.2 / summaries בעתיד) צריך עברית — כדי
שהקלט יהיה עקבי עם ה-few-shot examples בעברית ועם המונחים של נועה (spec §1).

הערכים זהים לתצוגה ב-frontend ובאפיון §1. enum שלא במיפוי → המחרוזת המקורית
(לא "לא ידוע" — fallback למחרוזת לא מבלבל את ה-AI פחות מתווית גנרית).
"""

# קטגוריות (ServiceCategory)
_CATEGORY_HE: dict[str, str] = {
    "clinic": "קליניקה",
    "workshops": "סדנאות והרצאות",
    "production": "ליווי והפקות",
    "digital_course": "קורס דיגיטלי",
}

# סאב-טייפים (service_subtype)
_SUBTYPE_HE: dict[str, str] = {
    "voice_development": "פיתוח קול",
    "public_speaking": "עמידה מול קהל",
    "voice_rehab": "שיקום קול",
    "workshop_speaking": "סדנת דיבור",
    "stage_arts": "אומניות הבמה",
    "lecture_organization": "הרצאה לארגון",
    "lecture_academic": "הרצאה לאוניברסיטה",
    "production_guidance": "ליווי הפקה אישית",
    "production_directing": "בימוי הפקה בתיאטרון",
    "digital_course": "קורס דיגיטלי",
}


def category_to_hebrew(value: str | None) -> str | None:
    """קטגוריה → עברית. None נשאר None; enum לא ידוע → המחרוזת המקורית."""
    if value is None:
        return None
    return _CATEGORY_HE.get(value, value)


def subtype_to_hebrew(value: str | None) -> str | None:
    """סאב-טייפ → עברית. None נשאר None; enum לא ידוע → המחרוזת המקורית."""
    if value is None:
        return None
    return _SUBTYPE_HE.get(value, value)
