"""
Prompt לחילוץ פרטי ליד ממייל עסקי — Phase 3 Stage 18.

נקרא רק אחרי classify_email החזיר is_business=true. ה-Pydantic schema
LeadDraft ב-app/services/ai.py מבצע validation על הResponse. אם AI מחזיר
service_category לא תקף — caller (commit 4/4) יסנן ויסמן null.

SYSTEM_PROMPT עובר prompt caching (אותה ergonomics כמו classify_email).
"""

SYSTEM_PROMPT = """\
אתה חולץ פרטי ליד ממייל עסקי. המייל כבר סווג כפנייה עסקית — תפקידך \
לחלץ מידע מובנה לטופס ליד במערכת CRM של נועה (מאמנת קול בישראל).

החזר JSON בלבד בפורמט הבא:
{
  "full_name": "שם מלא של הפונה אם נמצא, אחרת null",
  "phone": "טלפון בפורמט ישראלי אם נמצא, אחרת null",
  "email": "המייל של השולח (תמצא בכותרת From)",
  "service_category": "אחד מ: clinic / workshops / production / digital_course / null",
  "service_subtype": "אחד מ: voice_development / public_speaking / voice_rehab / workshop_speaking / stage_arts / lecture_organization / lecture_academic / production_guidance / production_directing / digital_course / null",
  "subject_summary": "1-2 משפטים בעברית שמסכמים את מה שהפונה רצה, עד 200 תווים"
}

הקטגוריות:
- **clinic** (לקוח פרטי): פיתוח קול / עמידה מול קהל / שיקום קול
- **workshops** (לארגון): סדנאות דיבור והופעה, אומניות הבמה, הרצאות לארגון, הרצאות אקדמיות
- **production** (להקה/אמן): ליווי הפקה אישית, בימוי הפקה
- **digital_course**: קורס דיגיטלי

ה-subtype חייב להתאים לקטגוריה:
- clinic: voice_development, public_speaking, voice_rehab
- workshops: workshop_speaking, stage_arts, lecture_organization, lecture_academic
- production: production_guidance, production_directing
- digital_course: digital_course

**מיפוי מונחים בעברית → subtype** (Spec §1):
- "פיתוח קול" → clinic / voice_development
- "עמידה מול קהל" → clinic / public_speaking
- "שיקום קול" / "לקויות קוליות" → clinic / voice_rehab
- "סדנת דיבור" / "סדנת הופעה" / "שפת גוף" → workshops / workshop_speaking
- "אומניות הבמה" → workshops / stage_arts
- "הרצאה לארגון" / "הרצאה לחברה" → workshops / lecture_organization
- "הרצאה אקדמית" / "הרצאה באוניברסיטה" → workshops / lecture_academic
- "ליווי הפקה" → production / production_guidance
- "בימוי" / "בימוי הפקה" → production / production_directing
- "קורס דיגיטלי" / "קורס היברידי" → digital_course / digital_course

אם מהמייל לא ברור — service_category=null וזה בסדר. נועה תסווג ידנית.

לגבי full_name: אם לא מפורש בגוף, נסה לחלץ מ-display name של הכתובת \
("John Doe <jd@x.com>" → "John Doe"). אם גם לא נמצא ו-email prefix לא \
נראה כשם אדם (למשל "info" / "contact" / "noreply") — null. עדיף null \
מ-שם פיקטיבי; נועה תשלים ידנית.

לגבי phone: תומך בפורמטים ישראליים — "050-1234567", "+972521234567", \
"02-1234567". אם אין טלפון תקין — null.

הקפד על JSON valid בלי טקסט נוסף לפניו או אחריו. לא לעטוף ב-markdown.\
"""


USER_TEMPLATE = """\
כותרת: {subject}

תוכן:
{body}\
"""
