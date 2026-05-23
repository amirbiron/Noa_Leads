"""
תעריפי שירות ברירת מחדל לפי service_subtype — לפי product-spec.md
("תעריפי ברירת מחדל"). ערכים מומלצים בלבד; ניתנים לעריכה בכרטיס.

משמשים:
- ב-CloseLeadModal: כברירת מחדל לערך/שעות בסגירה כ-WON
- ב-GET /settings/service-rates: לתצוגה במסך ההגדרות
- בעתיד: לאיפוס ערכי תוכנית מתמשכת חדשה
"""

from decimal import Decimal


# כל ערך: (price_ils, hours) — מחיר ה-deal הצפוי + שעות עבודה צפויות.
# None = "לבירור" כפי שצוין באפיון (בימוי הפקה, קורס דיגיטלי).
SERVICE_RATES: dict[str, dict] = {
    "voice_development": {
        "label": "פיתוח קול",
        "category": "clinic",
        "default_price": Decimal("300"),
        "default_hours": Decimal("1"),
    },
    "public_speaking": {
        "label": "עמידה מול קהל",
        "category": "clinic",
        "default_price": Decimal("2400"),
        "default_hours": Decimal("8"),
    },
    "voice_rehab": {
        "label": "שיקום קול",
        "category": "clinic",
        "default_price": Decimal("2400"),
        "default_hours": Decimal("8"),
    },
    "workshop_speaking": {
        "label": "סדנת דיבור / הופעה",
        "category": "workshops",
        "default_price": Decimal("2000"),
        "default_hours": Decimal("2"),
    },
    "stage_arts": {
        "label": "אומניות הבמה",
        "category": "workshops",
        # האפיון נקב 6,000–8,000 ל-3-4 מפגשים; לוקחים midpoint
        "default_price": Decimal("7000"),
        "default_hours": Decimal("4"),
    },
    "lecture_organization": {
        "label": "הרצאה לארגון",
        "category": "workshops",
        "default_price": Decimal("2000"),
        "default_hours": Decimal("2"),
    },
    "lecture_academic": {
        "label": "הרצאה אקדמית",
        "category": "workshops",
        "default_price": Decimal("2000"),
        "default_hours": Decimal("2"),
    },
    "production_guidance": {
        "label": "ליווי הפקה אישית",
        "category": "production",
        # 3.5 חודשים × 2 ש"ש × 4 שב' = ~28 שעות
        "default_price": Decimal("9600"),
        "default_hours": Decimal("28"),
    },
    "production_directing": {
        "label": "בימוי הפקה",
        "category": "production",
        # "לבירור" באפיון
        "default_price": None,
        "default_hours": None,
    },
    "digital_course": {
        "label": "קורס דיגיטלי",
        "category": "digital_course",
        # "לבירור" באפיון
        "default_price": None,
        "default_hours": None,
    },
}


def get_rate_for_subtype(subtype: str | None) -> dict | None:
    """
    מחזיר את ערכי ברירת המחדל לסאב-טייפ, או None אם לא ידוע.
    מחזיר עותק רדוד — מונע מ-callers לדרוס את ה-defaults הגלובליים.
    """
    if not subtype:
        return None
    entry = SERVICE_RATES.get(subtype)
    return entry.copy() if entry is not None else None
