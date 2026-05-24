# פאזה 2.5 — תכנון השלמות לפני פאזה 3

> **מטרה:** מסמך עבודה לפיצ'רים והתיקונים שצריך לעשות אחרי שפאזה 2 הושלמה אבל לפני שנעבור ל-AI+Gmail (פאזה 3).
>
> **מבוסס על:** סקירת `product-spec.md` המעודכן, באגים שהמשתמש דיווח, וביקורת bugbot מ-Cursor.
>
> **סטטוס:** בתכנון. **לא להתחיל מימוש לפני אישור התוכנית.**

---

## רקע — למה הפאזה הזו

פאזה 2 הסתיימה בהצלחה (OAuth → booking page → אישור → סנכרון הפוך → post-meeting). תוך כדי, התגלו:

1. **6 פיצ'רים מהאפיון לא ממומשים** (זוהו בביקורת ביניים).
2. **6 באגי UX/לוגיקה** מבדיקה ידנית של המשתמש.
3. **באג קריטי** של "ליד חדש מסומן נתקע".
4. **משימת תוכן** של seed templates (10 תבניות התחלתיות).
5. **`product-spec.md` עודכן** עם דיוקים שלא יושמו.

**העדיפות:** לתקן את הבסיס לפני שמוסיפים שכבת AI, אחרת AI תרוץ מעל מערכת לא יציבה.

---

## 1. תיקון `product-spec.md` ↔ קוד

המשתמש עדכן את ה-spec עם דיוקים שלא היו במסמך המקורי. צריך לוודא שהקוד תואם:

### 1.1 שם התובנה: "נתקעו ללא צעד הבא" → "לא טופלו בזמן"

**ה-spec (שורה 418):** `כמה לא טופלו בזמן`
**הקוד הנוכחי:** `stuck_count: "נתקעו ללא צעד הבא"` ב-`dashboard.py` ו-`page.tsx`.

**שינוי נדרש:**
- `frontend/app/page.tsx`: label `"נתקעו ללא צעד הבא"` → `"לא טופלו בזמן"`
- `backend/app/services/dashboard.py:_calc_weekly_insights` — וודא שהשאילתה משקפת "לא טופלו בזמן" ולא "נתקעו" (ראה גם §3 למטה — באג כללי של מסומן נתקע).

### 1.2 כללי פולואפ per-type (חדש ב-spec, שורות 482-486)

ה-spec הגדיר 5 כללים שונים:

| סוג | זמן |
|---|---|
| ליד חדש שלא טופל | 24 שעות |
| לקוח שהתעניין ולא סגר | 48-72 שעות |
| הצעה לארגון | 3-5 ימי עסקים |
| לקוח שלא חזר | 60-90 יום |
| ארגון שהתעניין בהרצאה | 24 שעות |

**מצב נוכחי:** `FIRST_RESPONSE` = 24h (ע"י grace). שאר ה-types — ברירת מחדל גנרית.

**שינוי נדרש:**
- חוקי `mark_overdue_leads` ו-`detect_dormant_leads` להבחין לפי הקשר (org vs private, proposal type).
- אפשר להגדיר ב-cron — או בעתיד דרך settings (פיצ'ר #2 למטה).

### 1.3 קטגוריות צבע ביומן (חדש בspec, שורות 220-225)

```
🟣 לקוחות   — colorId="3" (אנגייל-purple)
🩷 סדנאות   — colorId="4" (פלמינגו)
🟤 הכנה    — colorId="11" (טומאט)
🟥 ניהול   — colorId="6" (טנג'רין)
🟡 אישי    — colorId="5" (בננה)
⬜ חסום   — colorId="8" (גרפיט)
```

**שינוי נדרש:**
- בקוד שלנו, ל-`create_calendar_event` להוסיף `colorId="3"` (לקוחות) לכל אירוע booking. נועה תוכל לשנות בעצמה ביומן אחר כך.
- 5 הקטגוריות האחרות — נועה מנהלת בעצמה (אנחנו לא יוצרים אירועים מהסוגים האלה).

---

## 2. 6 הפיצ'רים החסרים מהאפיון

| # | פיצ'ר | חיוניות | מורכבות | המלצה |
|---|---|---|---|---|
| 2.1 | צ'יפים editable ב-settings | בינונית | בינונית | ✅ **בוצע** |
| 2.2 | תזכורת חוזרת מתצורת settings | נמוכה | נמוכה | ⏸️ לדחות לפאזה 3 |
| 2.3 | עמוד נפרד "ממתין לטיפול" | בינונית | נמוכה | ✅ לעשות |
| 2.4 | קטגוריות צבע ב-Google Calendar | נמוכה | נמוכה | ✅ לעשות (חלקי — רק לקוחות) |
| 2.5 | דגל "לא עסקי" ידני | נמוכה (עד פאזה 3) | נמוכה | ⏸️ לדחות לפאזה 3 (יחד עם Gmail) |
| 2.6 | תיעוד קולי | אופציונלי | גבוהה | ⏸️ POC נפרד אחרי פאזה 3 |

### 2.1 צ'יפים editable — ✅ הושלם

**ה-spec:** 6 צ'יפים כברירת מחדל, ב-settings אפשר לערוך/להוסיף/למחוק.

**מימוש שבוצע:**
- **DB:** טבלה `quick_action_chips` (id, label, action_type, requires_content, sort_order, is_active). migration 0010 עם seed 6 ברירת מחדל (UUIDs דטרמיניסטיים).
- **Backend:** GET (active_only optional) / POST / PATCH / DELETE על `/chips`. validation שה-action_type מוכר ב-state_machine.ACTIONS.
- **Frontend:** דף חדש `/settings/chips` עם list + edit/add/delete/sort/toggle. QuickActions טוען מ-API במקום hardcoded.

**הבדל מה-spec המקורי:** במקום `target_status + auto_followup_days` המורכבים, ה-chip מצביע ל-`action_type` קיים ב-state_machine — הבחירה של "מה קורה כשלוחצים" מבוקרת מחוץ לטבלה. נשאר flexibility ל-Noa (label, order, active) בלי לכפול logic ב-DB. אם בעתיד תרצה התנהגות חדשה שלא קיימת — נוסיף ל-state_machine.
- **Frontend:** דף `/settings/chips` עם רשימה+עריכה. `QuickActions.tsx` יביא מה-API במקום hardcoded.

### 2.3 עמוד "ממתין לטיפול"

**ה-spec (שורה 80):** "עמוד נפרד (לא בדשבורד הראשי) לפריטים שלא טופלו אחרי כל ההתראות".

**הבדל חשוב:** זה task-level, לא lead-level. כרגע יש לנו `/pending` (לידים) אבל לא view על tasks תקועים.

**מימוש:**
- Endpoint: `GET /tasks/stuck` — מחזיר tasks `OPEN`/`SNOOZED` שעבר 7+ ימים מ-`due_at`.
- Frontend: `/tasks/stuck` page, ממוין לפי וותק, כפתורי "סגירה ידנית" / "ארכוב".
- ניווט מ-/today: link "תקועים מ-7+ ימים" כשיש כאלה.

### 2.4 קטגוריות צבע (חלקי)

ראה §1.3. רק `colorId="3"` (לקוחות) על אירועי booking. אם נועה רוצה צבעים אחרים לקטגוריות אחרות — היא מסמנת ידנית.

---

## 3. 6 באגי UX מהמשתמש

| # | באג | מורכבות | היכן |
|---|---|---|---|
| 3.1 | שגיאות validation מציגות raw text במקום הודעה ידידותית | נמוכה | exception handler |
| 3.2 | באייקון "אצלי" ב-card הליד צריך ⏳, "אצל הלקוח" 📨 | נמוכה | `LeadCardRow.tsx` |
| 3.3 | "בעוד 5 שעות" — להסיר את מידע הזמן הבא | נמוכה | `TodayActionRow.tsx` |
| 3.4 | "שלחי הצעה" מעדכן סטטוס בלי שבאמת נשלחה הצעה | בינונית | `mark_proposal_sent` flow |
| 3.5 | תיוג "תקין" בכרטיס ליד מיותר | נמוכה | `LeadDetailPage` |
| 3.6 | שדות מיותרים ביומן Google (קטגוריה: production, מזהה booking), חסר סוג שירות | נמוכה | `create_calendar_event` |

### 3.1 הודעות שגיאה ידידותיות

**מצב נוכחי:** FastAPI `RequestValidationError` חוזר עם raw `error.msg` מ-Pydantic, ולפעמים זה פאיתון traceback.

**מימוש:**
- ב-`backend/app/core/exceptions.py`, exception handler ל-`RequestValidationError` שמתרגם field+message לעברית ידידותית.
- מיפוי כללי: `loc=('body','phone'), error="מספר טלפון לא תקין..."` → "מספר הטלפון שהוזן לא תקין".
- אם אין מיפוי ספציפי → "השדה `<שם השדה>` לא תקין".
- אסור לחשוף ערך הקלט המקורי או stack trace (כלל 3 ב-CLAUDE.md).

**ההחלטה:** עד כמה לפרט? "מספר טלפון לא תקין" + רמז ("נייד = 10 ספרות") או רק "לא תקין"?

### 3.2 אייקונים "אצלי"/"אצל הלקוח" — ✅ הוחלט (§7.1)

- מחכה לי (נועה) = ברירת מחדל, **אין סימון**
- מחכה ללקוח = אייקון ⏳ קטן ליד שם הליד

### 3.4 "שלחי הצעה" — שני שלבים (§7.2) — ✅ הוחלט

1. לחיצה → פותחת WhatsApp עם תבנית הצעה.
2. חזרה לאפליקציה → מודאל "האם נשלחה ההצעה? כן/לא".
3. רק על "כן" — סטטוס משתנה ל-PROPOSAL_SENT ו-task PROPOSAL_FOLLOWUP נפתח.

### 3.6 פרטים באירוע ביומן

**הסר:** `קטגוריה: production`, `מזהה booking: <uuid>`.
**הוסף:** `סוג שירות: עמידה מול קהל` (subtype בעברית).

**שינוי ב-`create_calendar_event`:** to lookup `service_subtype` ל-עברית דרך המיפוי הקיים.

---

## 4. באג: ליד חדש מסומן "נתקע ללא צעד הבא"

**ה-spec (שורה 418):** "לא טופלו בזמן" — לא "נתקעו ללא צעד הבא".

**מה קורה כרגע:** `_calc_weekly_insights` ב-`dashboard.py` סופר לידים עם `Lead.next_action_due_at.is_(None)`. ליד חדש עוד לא עבר flow שמגדיר `next_action_due_at`, אז הוא נספר כתקוע.

**הbug האמיתי:** ליד חדש *צריך* לקבל `next_action` אוטומטית בעת יצירה. ראה ה-spec ב-handle הקבוע "ליד חדש = first_response, due_at = +24h".

**שתי פעולות נדרשות:**

### 4.1 על יצירת ליד — להגדיר אוטומטית

```python
# ב-leads.create_lead:
lead.next_action_type = TaskType.FIRST_RESPONSE.value
lead.next_action_due_at = _due_at_for_first_response(now)  # יום עבודה הבא או now
```

**בדיקה:** האם `next_action_due_at` עוד שדה ב-`Lead` model או רק `tasks.due_at`?
- אם רק tasks, ה-spec משתמש בשם כפול. צריך להחליט: לסמוך על tasks או להוסיף שדה ב-Lead.

### 4.2 שינוי השם וההגדרה של התובנה

```python
# במקום: count of leads with next_action_due_at IS NULL
# שינוי ל: count of leads with overdue first-response (פולואפ עבר ולא טופל)
stuck_count = ... where exists task FIRST_RESPONSE for lead, status=open, due_at + grace < now
```

תווית: `"לא טופלו בזמן"`.

---

## 5. Seed templates — 10 התבניות

המשתמש סיפק 10 תבניות מוכנות. צריך migration שטוען אותן ב-deployment הראשון.

**מבנה:**
- **Migration חדש** `2026_05_XX_0009-seed_initial_templates.py` שמכניס את 10 התבניות.
- **תנאי**: רק אם הטבלה ריקה (לא לדרוס תבניות שנועה יצרה).
- **שדות לכל תבנית**: `name`, `channel` (whatsapp/email), `target_audience` (private/organization/any/dormant), `body`, `variables` (list של placeholders), `is_active=true`.

**בדיקה לפני מימוש:**
- מבנה ה-`templates` table הנוכחי — האם תומך ב-`channel`+`target_audience`? `variables` field?
- אם השדות לא קיימים — migration לפני seed.

---

## 6. תוכנית עבודה מומלצת (סדר עדיפות)

### גל 1 — תיקוני באגים קריטיים (שעתיים-3 עבודה)

1. **§4** — ליד חדש מסומן נתקע (קריטי)
2. **§3.1** — שגיאות validation
3. **§3.4** — "שלחי הצעה" — החלטה ומימוש (אופציה A הכי מהירה)
4. **§3.6** — אירוע ביומן
5. **§3.5** — הסרת "תקין" מיותר
6. **§3.3** — הסרת "בעוד X שעות"
7. **§3.2** — אייקונים (אחרי שתחליט)

### גל 2 — ה-spec ↔ קוד (1-2 שעות)

8. **§1.1** — שם התובנה "לא טופלו בזמן"
9. **§1.3** + **§2.4** — colorId לאירועי booking
10. **§2.3** — עמוד "ממתין לטיפול" (task-level)

### גל 3 — פיצ'רים חדשים (חצי יום)

11. **§5** — seed templates (10 תבניות)
12. **§2.1** — צ'יפים editable
13. **§1.2** — כללי פולואפ per-type (אם רוצים יסודי)

### לדחות

- **§2.2** — תזכורת חוזרת (פאזה 3 או כשיהיה צורך אמיתי)
- **§2.5** — דגל לא-עסקי (פאזה 3 עם Gmail)
- **§2.6** — תיעוד קולי (POC אחרי פאזה 3)

---

## 7. החלטות (סגורות)

### 7.1 אייקונים `waiting_on` (§3.2) — ✅ לפי spec

- **מחכה לי** (נועה) = ברירת מחדל, **בלי סימון**
- **מחכה ללקוח** = אייקון ⏳ קטן ליד שם הליד

**רציונל:** רוב הלידים אצל נועה. סימון לכולם = רעש ויזואלי. רק החריגות מקבלות סימון.

### 7.2 "שלחי הצעה" flow (§3.4) — ✅ אופציה B בגרסה פשוטה

זרימה:
1. לחיצה על "שלחי הצעה" → פותחת WhatsApp עם תבנית הצעה (כמו כל תבנית רגילה).
2. כשנועה חוזרת לאפליקציה → מודאל קצר: **"האם נשלחה ההצעה?"** עם כפתורי כן/לא.
3. רק על **"כן"**: סטטוס → `PROPOSAL_SENT`, נפתח task `PROPOSAL_FOLLOWUP`, נרשם activity.
4. **"לא"**: אין שינוי, ה-CTA נשאר זמין.

**רציונל:** עקבי עם "שליחה תמיד ידנית" באפיון. תואם לאיך שאר התבניות עובדות (לחיצה → פתיחת WhatsApp). מבטיח שסטטוס משקף מציאות.

### 7.3 `next_action` location (§4.1) — ✅ גם בטבלת leads וגם דרך tasks

- **`tasks` table = source of truth.** כל פולואפ נוצר כ-task.
- **שדות `next_action_type` ו-`next_action_due_at` ב-leads = cache** של ה-task הפעיל הקרוב ביותר.

**סנכרון:**
- על יצירת/עדכון task פעיל → UPDATE על שדות ה-cache בליד.
- על השלמת/ביטול task → אם היה ה-cache, מעדכן ל-task הבא או NULL.
- אם משתמשים בservice: helper `_sync_lead_next_action_cache(lead_id)` שכל מי שמשנה task יקרא לו.

**רציונל:** קריאה מהירה לכרטיס ליד (בלי JOIN), היסטוריה מלאה ב-tasks.

### 7.4 כללי פולואפ per-type (§1.2) — ✅ עכשיו, hardcoded ב-constants

מוסיפים ל-`backend/app/constants.py`:

```python
FOLLOWUP_RULES = {
    "first_response": timedelta(hours=24),
    "warm_followup": timedelta(hours=60),       # 48-72h, ממוצע
    "proposal_followup_org": timedelta(days=4), # 3-5 ימי עסקים
    "dormant_check": timedelta(days=75),        # 60-90 יום
    "lecture_inquiry": timedelta(hours=24),
}
```

ה-`mark_overdue_leads` וקבועי ה-cron ישתמשו באלה. **אין UI ל-settings בפאזה זו** — אם נועה תרצה לשנות בעתיד, נוסיף.

### 7.5 שדה `target_audience` בtemplates (§5) — ✅ להוסיף

ערכים: `private` / `organization` / `dormant` / `any`.

**אם לא קיים** במודל הקיים → migration חדשה שמוסיפה אותו (`nullable=true` ל-templates קיימים, אחר כך seed יציב לפי הסוג של כל תבנית).

חיוני ל"פתיחה חכמה לפי סוג ליד" — `DynamicActionButton` יבחר תבנית לפי `target_audience` שמתאים ל-lead.

---

## 8. החלטות נוספות שעלו מהשאלות

### 8.1 שמות אקטיביטי "סוג טאסק" (§1.2)

ה-`TaskType` בקוד כרגע: `FIRST_RESPONSE`, `FOLLOWUP`, `PROPOSAL_FOLLOWUP`, `POST_MEETING_UPDATE`, `DORMANT_REACHOUT`, `PROGRAM_END`, `AFTER_HOURS_REPLY`.

הקבועים ב-§7.4 מתייחסים לשמות חדשים (`warm_followup`, `proposal_followup_org`, `lecture_inquiry`). **החלטה:** משאירים את ה-TaskType הקיים, ו-FOLLOWUP_RULES שואב את ה-delta המתאים לפי `task.type` + הקשר נוסף מהליד (`service_category=workshops` → `lecture_inquiry`).

זה דורש פונקציה `resolve_followup_delta(task_type, lead) -> timedelta`. ראה §4.1 בגל 1.

---

## 8. מה אחרי

אחרי גל 1+2+3, פאזה 2.5 סגורה. אז:
- **פאזה 3** — AI + Gmail integration. כל מה שדחינו.
- **המסך של נועה** — בדיקה סופית מקצה לקצה לפני ש-onboarding-ה (לא הbeta).

---

**עדכון אחרון:** התחלת תכנון פאזה 2.5.
