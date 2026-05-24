# ניהול טוקנים ב-AI וניקוי תוכן מיילים

> **שייך ל:** פאזה 3 (AI + Gmail integration)
> **חובה לקרוא ולממש לפני התחלת חיבור Gmail ל-classifier.**

---

## רקע ולקח מ-EmailFlow

ב-EmailFlow זוהתה בעיה קריטית: מיילים נכנסים (במיוחד ניוזלטרים, מערכות שיווק כמו Smoove/Mailchimp, וטפסים אוטומטיים) נשלחו ל-classifier כשהם נושאים את ה-HTML הגולמי שלהם — כולל CSS inline, base64 של תמונות מוטמעות, footer של unsubscribe, ו-tracking links. התוצאה: קריאות AI שצרכו 10,000-12,000 input tokens במקום ~1,500 המצופים — פי 8 מהנדרש.

ההשלכות שהיו ב-EmailFlow ויש למנוע ב-Noa_Leads מראש:

- חריגה מתקרת ה-TPM של Anthropic → דחיית בקשות (429) → לידים שלא סווגו
- עלות מנופחת — ~$0.015 למייל במקום $0.002
- סיווגים גרועים, כי ה-AI מקבל סלט של CSS עם הטקסט האמיתי קבור בתוכו
- אצל נועה — זה ישיר מתרגם לליד שלא הופיע בדשבורד בזמן, או הופיע בקטגוריה הלא נכונה

---

## דרישה למימוש ב-Noa_Leads

**כל מסלול שמעביר תוכן מייל ל-AI חייב לעבור קודם דרך פונקציית ניקוי ייעודית.** אסור להעביר HTML גולמי או טקסט שחולץ ב-regex פשוט.

---

## מפרט הפונקציה `clean_email_body_for_ai`

**מיקום:** `app/utils/email_cleaning.py` (קובץ חדש, נפרד מכל מודול קיים)

הפונקציה מקבלת HTML גולמי או טקסט מעורבב, ופרמטר `purpose` שקובע את אורך הפלט המקסימלי, ומחזירה טקסט נקי מוכן ל-prompt.

### חתימת הפונקציה

```python
def clean_email_body_for_ai(
    raw_content: str,
    purpose: Literal['classification', 'summary', 'extraction'] = 'classification'
) -> str:
```

### תקרת תווים לפי purpose

| Purpose | Max chars | מתי משתמשים |
|---|---|---|
| `classification` | 1,200 | סיווג עסקי/לא עסקי, זיהוי קטגוריה |
| `summary` | 2,000 | סיכום תוכן, חילוץ פרטים |
| `extraction` | 2,500 | חילוץ נתונים מורכבים (שם, טלפון, סוג שירות) |

הסיבה: ל-classifier לא צריך 2,000 תווים כדי להחליט אם מייל הוא עסקי. AI יכול להחליט מ-800-1,000 תווים ראשונים. לסיכום או חילוץ מידע - שם הקונטקסט המלא חשוב יותר.

### שלבי הניקוי (לפי הסדר)

1. **פרסור HTML** עם BeautifulSoup, parser מועדף `lxml` עם נפילה ל-`html.parser`

2. **הסרת תגיות שאינן תוכן:**
   - `script`, `style`, `head`, `meta`, `link`, `noscript`

3. **הסרת אלמנטים לפי class/id** - אם מכילים אחת מהמילים:
   - `footer`, `unsubscribe`, `tracking`, `social-links`, `preheader`, `header-logo`
   - best-effort, לא לזרוק חריגה אם לא נמצא

4. **חילוץ טקסט:** `get_text(separator=' ', strip=True)`

5. **החלפת URLs ארוכים:** רגקס שמחליף URLs מ-100 תווים והלאה ב-`[link]`
   ```python
   re.sub(r'https?://[^\s]{100,}', '[link]', text)
   ```
   זה חוסך 30-40% מהטוקנים בניוזלטרים שמלאים ב-UTM tags ו-tracking IDs.

6. **קריסת רצפי whitespace:** `re.sub(r'\s+', ' ', text)`

7. **הסרת שורות שמכילות רק תווי בקרה / זנב URL / זבל encoding**

8. **Truncation בטיחותי** לפי `purpose`. אם נחתך — להוסיף בסוף `"\n\n[הטקסט קוצר]"`

---

## דרישת לוגינג

בכל קריאה לפונקציה, לתעד שורת לוג מובנית:

```
email_id=<id>, purpose=<classification|summary|extraction>, raw_len=<תווים לפני>, cleaned_len=<תווים אחרי>, ratio=<אחוז>, truncated=<bool>
```

זה יאפשר אחרי שבוע ראשון של פעילות לזהות אם יש סוגי מיילים שהניקוי לא מטפל בהם טוב.

---

## מקומות שחייבים להשתמש בפונקציה

- מסלול קליטת מייל מ-Gmail → classifier
- מסלול קליטת טופס עם שדה body
- כל מקום שמעביר טקסט חופשי ל-AI לצורך סיווג, סיכום, או הצעת תבנית

---

## מה אסור לעשות

- **אסור לקרוא לפונקציה הזו על תוכן שמיועד לתצוגה ב-UI.** ל-UI יש דרישות שונות (שמירת עיצוב, lazy loading של תמונות וכו') — שם משתמשים בפונקציה אחרת או מציגים את ה-HTML המקורי.
- **אסור להעביר את `MAX_BODY_CHARS` כפתרון לבד בלי BeautifulSoup.** truncation גס חותך לפני שהטקסט האמיתי מתחיל.

---

## מנגנון retry על קריאות Anthropic

לקח שני מ-EmailFlow: ה-retry decorator ניסה 3 פעמים על כל שגיאה, כולל `RateLimitError`. זה רק החמיר את הספירה כי כל מייל גדול אחד נחשב 3 דחיות.

ב-Noa_Leads, ה-Anthropic client חייב:

- **retry על שגיאות רשת זמניות** (`APIConnectionError`, `APITimeoutError`, `InternalServerError`) — כן
- **retry על `RateLimitError` — לא.** במקום זה:
  1. לתפוס את השגיאה
  2. להחזיר 503 ל-caller
  3. לשמור את הליד עם דגל `pending_classification=true`
  4. ב-job חוזר אחרי 60 שניות יטופל

---

## סינון לפני AI — חיסכון של 40%+ מהקריאות

לפני שמייל מגיע ל-classifier בכלל, לבדוק heuristically:

### 1. סינון לפי `From` header

אם השדה מכיל אחת מהמילים → לסמן כ-spam ולא לקרוא ל-AI:
- `noreply`, `no-reply`
- `notifications@`
- `newsletter@`
- `donotreply`

### 2. סינון לפי domain שולח

רשימה שחורה של domains של מערכות שיווק אוטומטיות:
- `mailchimp.com`
- `smoove.io`
- `sendgrid.net`
- `constantcontact.com`
- `hubspot.com`
- `mandrillapp.com`

### 3. סינון לפי `List-Unsubscribe` header

קיום ה-header הזה = סימן כמעט ודאי לניוזלטר אוטומטי.

### 4. Double-check על false positives

**זהירות:** יש לקוחות לגיטימיים שעוברים דרך מערכות אוטומטיות —
- מייל אישי שמוגדר עם From של "no-reply@..." בטעות (קורה בטפסי אתר).
- לקוח שמשתמש ב-mailchimp/sendgrid לעסק שלו ופונה דרכם.
- ניוזלטר שכולל בתוכו פנייה אישית בגוף.

**הפתרון:** ה-override של מילות-מפתח אישיות חל על **כל 3 ה-heuristics**
לעיל (§1 From, §2 domain, §3 List-Unsubscribe). אם אחד מהם פסל את
המייל, *אבל* בגוף המייל יש מילים שמעידות על פנייה אישית — לשלוח ל-AI
בכל זאת. ההפסד של AI call אחד מיותר זול בהרבה מאובדן ליד אמיתי.

ה-pipeline:
```
1. is_likely_personal_inquiry(body) ← בודק מילות מפתח (להלן)
2. is_heuristic_spam = from_spam OR domain_spam OR list_unsubscribe
3. if is_heuristic_spam AND NOT is_likely_personal_inquiry: skip AI, mark spam
4. else: send to AI classifier
```

מילות מפתח שמעידות על פנייה אישית (regex case-insensitive):
- `פנייה`, `מעוניין`, `מעוניינת`
- `אשמח לקבוע`, `אשמח לתאם`, `אשמח להבין`
- `יש לי שאלה`, `אני מחפש`, `אני מחפשת`
- `רוצה לדעת`, `רוצה להתייעץ`

זה רק כמה שורות קוד, אבל מונע אובדן של לידים אמיתיים מכל אחד משלושת
המסלולים — לא רק domain.

### 5. הערה לגבי לקוחות פרטיים

נועה מקבלת פניות מתיבות מייל אישיות (Gmail, Walla, Hotmail). הסינון הזה הוא **רק לשולחים אוטומטיים מובהקים**, ולא יכלול false positive על תיבות מייל אישיות.

---

## מדידה והפקת לקחים

אחרי שבוע ראשון של פעילות אצל נועה, להריץ דוח:

- כמה מיילים סוננו לפני AI
- ממוצע tokens לקריאת classifier
- מקסימום tokens שנצפה
- שיעור שגיאות 429 (אמור להיות 0)
- עלות AI יומית

**יעדים:**
- ממוצע מתחת ל-1,500 input tokens לקריאה
- אפס דחיות rate limit
- עלות AI יומית מתחת ל-$0.50 בנפחי הלידים של נועה

---

## רשימת משימות לפני תחילת פאזה 3

1. ⬜ יצירת `app/utils/email_cleaning.py` עם `clean_email_body_for_ai`
2. ⬜ unit tests לפונקציה - HTML מורכב, ניוזלטר, מייל אישי, edge cases
3. ⬜ הוספת לוגינג מובנה
4. ⬜ יצירת `app/utils/email_filtering.py` עם הסינון ה-heuristic
5. ⬜ הגדרת רשימת domains כקבועים ב-`constants.py`
6. ⬜ עדכון ה-Anthropic client לא לעשות retry על RateLimitError
7. ⬜ הוספת שדה `pending_classification` ל-Lead model
8. ⬜ Job שמעבד מחדש לידים עם `pending_classification=true`
9. ⬜ dashboard פנימי לניטור עלויות AI (אופציונלי לפאזה ראשונה)

---

## הערה לגבי שמירת הטקסט המקורי

חשוב: גם אחרי הניקוי, **לשמור את ה-HTML המקורי במסד הנתונים** (בשדה נפרד). זה לתצוגה למשתמש, debug, ולמקרה שנרצה לעבד מחדש בעתיד עם אלגוריתם משופר.

מבנה מומלץ ב-DB:
```
email_messages:
  - raw_html (לתצוגה ול-debug)
  - cleaned_text (מה שנשלח ל-AI)
  - cleaning_metadata (purpose, ratio, truncated, timestamp)
```
