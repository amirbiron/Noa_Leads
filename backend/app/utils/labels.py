"""
תרגומים בעברית לערכים מבוססי enum — לתצוגה בהודעות/UI.

מודול משותף כדי להימנע מ-drift בין שירותים שמציגים את אותו ערך.
לדוגמה: telegram notify_new_lead ו-template_render משתמשים שניהם
במיפוי service_category → עברית. שכפול היה מסכן את הקונסיסטנטיות.
"""


# קטגוריות שירות → תווית עברית להצגה
SERVICE_CATEGORY_HE: dict[str, str] = {
    "clinic": "קליניקה",
    "workshops": "סדנאות והרצאות",
    "production": "ליווי והפקות",
    "digital_course": "קורס דיגיטלי",
}


# סאב-טייפים → תווית עברית להצגה
SERVICE_SUBTYPE_HE: dict[str, str] = {
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


# מקורות פנייה → תווית עברית
SOURCE_CHANNEL_HE: dict[str, str] = {
    "form": "טופס באתר",
    "email": "מייל",
    "manual": "הזנה ידנית",
    "referral": "המלצה",
    "facebook": "פייסבוק",
    "instagram": "אינסטגרם",
    "whatsapp": "וואטסאפ",
    "other": "אחר",
}
