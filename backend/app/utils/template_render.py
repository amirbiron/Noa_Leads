"""
רינדור תבניות הודעה עם משתנים מתוך כרטיס הליד.

מטרת המודול: לקבל body של תבנית עם placeholders מהסוג {customer_name},
ולהחזיר טקסט עם הערכים האמיתיים. בלי תלות בספריית templating חיצונית
כדי שלא נאפשר בטעות הזרקת קוד.
"""

import re
from typing import Mapping

from app.models.lead import Lead
from app.utils.labels import SERVICE_CATEGORY_HE, SERVICE_SUBTYPE_HE


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


# רק שמות ASCII — לא מאפשרים placeholders עם רווחים או תווי שליטה
_PLACEHOLDER_RE = re.compile(r"\{([a-z_][a-z0-9_]*)\}")


def extract_placeholders(body: str) -> list[str]:
    """מחזיר את שמות ה-placeholders המופיעים ב-body (סדר שמירת הופעה)."""
    return _PLACEHOLDER_RE.findall(body)


def build_variable_context(lead: Lead) -> dict[str, str]:
    """בונה את ה-context לרינדור — כל הערכים כ-str (גם כשחסרים)."""
    return {
        "customer_name": lead.full_name or "",
        "service_category": SERVICE_CATEGORY_HE.get(
            lead.service_category, lead.service_category or ""
        ),
        "service_subtype": SERVICE_SUBTYPE_HE.get(
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
