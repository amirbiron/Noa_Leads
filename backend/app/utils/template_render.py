"""
רינדור תבניות הודעה עם משתנים מתוך כרטיס הליד.

מטרת המודול: לקבל body של תבנית עם placeholders מהסוג {customer_name},
ולהחזיר טקסט עם הערכים האמיתיים. בלי תלות בספריית templating חיצונית
כדי שלא נאפשר בטעות הזרקת קוד.
"""

import re
from typing import Mapping

from app.models.lead import Lead


# שמות משתנים נתמכים → מה שולפים מהליד.
# שינוי מפתחות = שינוי חוזי. אי-הוספת מפתח לא נסמך = לא ניתן לשימוש בתבנית.
SUPPORTED_VARIABLES: dict[str, str] = {
    "customer_name": "שם הלקוח/ה",
    "service_category": "קטגוריית השירות",
    "service_subtype": "סוג השירות הספציפי",
    "organization": "ארגון",
    "phone": "טלפון",
    "email": "מייל",
}


# תרגום קטגוריות לעברית — להצגה אנושית בתבניות
_SERVICE_CATEGORY_HE: dict[str, str] = {
    "clinic": "קליניקה",
    "workshops": "סדנאות והרצאות",
    "production": "ליווי והפקות",
    "digital_course": "קורס דיגיטלי",
}

_SERVICE_SUBTYPE_HE: dict[str, str] = {
    "voice_development": "פיתוח קול",
    "public_speaking": "עמידה מול קהל",
    "voice_rehab": "שיקום קול",
    "workshop_speaking": "סדנת דיבור/הופעה",
    "stage_arts": "אומניות הבמה",
    "lecture_organization": "הרצאה לארגון",
    "lecture_academic": "הרצאה אקדמית",
    "production_guidance": "ליווי הפקה אישית",
    "production_directing": "בימוי הפקה",
    "digital_course": "קורס דיגיטלי",
}


# רק שמות ASCII — לא מאפשרים placeholders עם רווחים או תווי שליטה
_PLACEHOLDER_RE = re.compile(r"\{([a-z_][a-z0-9_]*)\}")


def build_variable_context(lead: Lead) -> dict[str, str]:
    """בונה את ה-context לרינדור — כל הערכים כ-str (גם כשחסרים)."""
    return {
        "customer_name": lead.full_name or "",
        "service_category": _SERVICE_CATEGORY_HE.get(
            lead.service_category, lead.service_category or ""
        ),
        "service_subtype": _SERVICE_SUBTYPE_HE.get(
            lead.service_subtype or "", lead.service_subtype or ""
        ),
        "organization": lead.organization_name or "",
        "phone": lead.phone or "",
        "email": lead.email or "",
    }


def render_template(body: str, context: Mapping[str, str]) -> str:
    """
    מחליף {var} ב-context[var]. placeholder לא מוכר נשאר כמו שהוא
    כדי שלא נאבד טקסט בטעות אם נועה כתבה משהו אחר בסוגריים.
    """

    def _replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key in context:
            return context[key]
        # placeholder לא מוכר — משאירים את הטקסט המקורי
        return match.group(0)

    return _PLACEHOLDER_RE.sub(_replace, body)


def render_for_lead(body: str, lead: Lead) -> str:
    return render_template(body, build_variable_context(lead))
