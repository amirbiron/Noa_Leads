# פאזה 3 — תכנון: AI + Gmail Integration

> **מטרה:** מסמך תכנון לפאזה האחרונה. **לא להתחיל מימוש לפני אישור.**
>
> **תלות:** פאזה 2.5 צריכה להסתיים קודם — היא מתקנת את הבסיס שעליו ה-AI יבנה.

---

## למה פאזה 3 קיימת

עד עכשיו, נועה צריכה לעשות הכל ידנית:
- להזין כל ליד שמגיע במייל.
- לסקור כל מייל אם הוא רלוונטי או ספאם.
- לנסח הצעות מאפס.
- לעקוב ידנית אחרי מי לא ענה.

**הפאזה הזו מוסיפה שכבת AI שעוזרת — לא מנהלת.** עיקרון מהאפיון: "ה-AI לא שולח הודעות, לא מנסח תגובות ללידים".

---

## 4 חבילות עבודה

### חבילה A — Gmail integration (תשתית)

לקלוט לידים שמגיעים במייל, אוטומטית.

**רכיבים:**
1. **OAuth ל-Gmail** (scope `gmail.readonly` + `gmail.modify`).
2. **Pub/Sub topic** — `gmail_pubsub_topic` כבר בconfig. הקצאה ב-Google Cloud.
3. **Push notification** — `users.watch()` על תיבת המייל של נועה.
4. **Webhook endpoint** `POST /webhooks/gmail` — מקבל push, מאחזר מיילים חדשים דרך Gmail API.
5. **Endpoint /intake/email** — מקבל מייל מ-webhook, יוצר ליד.

**מורכבות:** דומה לקריאות יומן, אבל ב-scope אחר. Token refresh, watch renewal, sync via historyId (במקום syncToken).

**שיעורים מפאזה 2:**
- Race conditions: שני webhooks מקבילים → אותו אימייל מעובד פעמיים. CAS על `historyId`.
- Webhook delay: לא להניח שזמן ה-activity = זמן המייל. להשתמש ב-`message.internalDate`.
- Stop watch על reconnect (אחרת orphan channel).

---

### חבילה B — AI סינון מיילים

לסנן מיילים שלא רלוונטיים (ספאם, ניוזלטרים, התראות אוטומטיות) לפני שייצרו ליד.

**רכיבים:**
1. **LLM call** דרך Claude API — מומלץ `claude-haiku-4-5` (מהיר, זול).
2. **Prompt מצומצם** — subject + 200 תווים ראשונים של body. תשובה JSON: `{"is_business": bool, "confidence": float, "reason": str}`.
3. **Caching** — `prompt_cache` מ-API של Anthropic על system prompt גדול (categories, examples).
4. **Threshold החלטה** — `is_business=true` → צור ליד. `false` → תווית "סוננו" ב-Gmail (`gmail.modify` scope).

**Fallback:** אם LLM נכשל / timeout → treat as business (better safe than sorry, נועה מוחקת ידנית).

**Skill קיים:** `docs/Skills/gws-hebrew-email-automation/` — לקרוא לפני המימוש.

**עלות משוערת:** Haiku 4.5 = ~$0.001 לסינון מייל בודד. 1,000 מיילים/חודש = ~$1.

---

### חבילה C — AI סיכומים

החלפת הסיכום הסטטיסטי הקיים בסיכום נרטיבי חכם.

**רכיבים:**
1. **`daily_summary`** (קיים) — קלט: רשימת פעולות היום, לידים חדשים, פגישות. פלט: 2-3 משפטים בעברית.
2. **`weekly_summary`** (קיים) — קלט: מצרפי השבוע. פלט: סיכום + תובנה ("השעה הרווחית" כבר מחושב, נוסיף נרטיב).
3. **Prompt design** — קצר, מצומצם, ללא ז'רגון. דוגמה: "סיכמת השבוע 5 פגישות, רובן בקליניקה. שתי הצעות לארגונים נשלחו - שתיהן ממתינות לתשובה. המקסום: שיחה עם אורנה ביום שלישי."
4. **Model:** `claude-sonnet-4-6` לאיכות סיכומים. אם עלות יקרה — `haiku`.

**שינוי בקוד:**
- `jobs/daily_summary.py` ו-`jobs/weekly_summary.py` — להוסיף קריאה ל-LLM.
- ההודעה בטלגרם הופכת לdynamic, לא רק ספירות.

**עלות משוערת:** sonnet ~$0.01 לסיכום. יומי+שבועי = ~$0.5/חודש.

---

### חבילה D — AI עוזרים נקודתיים

3 מיני-פיצ'רים שעוזרים בנקודות חיכוך ספציפיות:

#### D.1 זיהוי לידים רדומים — הצעת פעולה

**כבר יש:** `detect_dormant_leads` cron שמסמן flag.
**מוסיפים:** LLM שמציע פעולה מתאימה לכל ליד רדום — "חידוש קשר עדין" / "ארכוב" / "להתקשר" — לפי ההיסטוריה של אותו ליד.

**מימוש:** משימה type=`DORMANT_REACHOUT` עם `metadata.ai_suggestion = "..."`. ה-`DynamicActionButton` מציג את ההצעה.

#### D.2 ניסוח הצעות

**העיקרון מהאפיון:** "עזרה בניסוח הצעות — בעיקר להרצאות וסדנאות לארגונים, שדורשות מענה אישי וארוך יותר".

**מימוש:**
- כפתור "ניסוח עם AI" בכרטיס ליד שסטטוסו `IN_PROGRESS` ושסוג השירות workshops/production.
- LLM מקבל: פרטי הליד + סוג השירות + הקשר ידני שנועה מקלידה בקצרה.
- מחזיר טיוטה ארוכה (200-400 מילים) — נועה עורכת, אחר כך שולחת.

**מודל:** `sonnet` — איכות חשובה כי זה לקוח קצה.

#### D.3 חילוץ פרטים מטקסט חופשי

**שימוש:** באינטייק ממייל — חילוץ אוטומטי של שם, טלפון, נושא, סוג שירות מקובץ הודעת המייל.

**LLM:** `haiku` עם prompt + structured output (`response_format: json_schema`).

---

## תכנון תשתית AI משותפת

**Service חדש:** `backend/app/services/ai.py`.

מספק:
- `classify_email(subject, body) -> ClassificationResult`
- `summarize_daily(data) -> str`
- `summarize_weekly(data) -> str`
- `suggest_action_for_dormant(lead, history) -> str`
- `draft_proposal(lead, context) -> str`
- `extract_lead_from_email(email) -> LeadDraft`

**עיקרון:** כל פונקציה מקבלת dict פשוט ומחזירה Result מוגדר (Pydantic). הכוונה: לעטוף את ה-API מאחורי abstraction יציב.

**Error handling:**
- Timeout → fallback definido (לסינון: treat as business; לסיכום: stats-only).
- Rate limit → retry עם exponential backoff (max 3 פעמים).
- שגיאת מפתח → log + fallback. *אסור* שהאפליקציה תפול בגלל AI.

**Skill קיים:** `docs/Skills/hebrew-llm-eval-suite/` — לקרוא לפני בחירת מודל ל-prompts.

**Caching:** prompt cache של Anthropic על system prompts ארוכים (החיסכון ~90% כשעובד). זה רלוונטי במיוחד ל-classify_email שירוץ מאות פעמים ביום.

---

## עלויות צפויות

| חבילה | מודל | עלות לחודש (משוערת) |
|---|---|---|
| סינון מייל | Haiku 4.5 | $1-2 |
| סיכום יומי | Sonnet 4.6 | $0.30 |
| סיכום שבועי | Sonnet 4.6 | $0.10 |
| לידים רדומים | Haiku 4.5 | $0.20 |
| ניסוח הצעות | Sonnet 4.6 | $0.50 (לפי ~10 הצעות/חודש) |
| חילוץ מייל | Haiku 4.5 | $1 |
| **סה"כ** | | **~$3-5/חודש** |

עם prompt caching של Anthropic, הסה"כ יכול לרדת ל-$1-2/חודש.

---

## תכנון פיזי (סדר עבודה)

### שלב 16 — תשתית AI

1. service חדש `ai.py` עם wrapper סביב Anthropic SDK.
2. config: `anthropic_api_key` (קיים ב-config).
3. כתיבת prompts ב-prompts/ folder עם versioning.
4. error handling, retries, timeout.

### שלב 17 — Gmail OAuth + watch

5. routes/google_gmail.py (דומה ל-google_calendar.py).
6. כפתור ב-/settings: "חיבור ל-Gmail".
7. watch creation אוטומטית. cron renewal יומי.

### שלב 18 — Gmail webhook + intake

8. POST /webhooks/gmail.
9. שליפת מייל בפועל דרך Gmail API.
10. קריאה ל-`ai.classify_email`.
11. אם business: `ai.extract_lead_from_email` + יצירת ליד.
12. אם not business: תווית "סוננו" ב-Gmail.

### שלב 19 — AI סיכומים

13. עדכון `jobs/daily_summary.py` ו-`jobs/weekly_summary.py`.

### שלב 20 — Dormant suggestion + proposal drafting

14. הוספה ל-`detect_dormant` cron של AI suggestion.
15. כפתור "ניסוח עם AI" ב-frontend.

---

## החלטות פתוחות

לפני התחלת מימוש, צריך תשובות:

1. **מודל ברירת מחדל**: Sonnet 4.6 לסיכומים, Haiku 4.5 לסינון? להשאיר flexible (config)?
2. **תווית "סוננו" ב-Gmail**: שם קבוע ("סוננו אוטומטית") או configurable?
3. **חתימה בטיוטת הצעה**: לחתום אוטומטית "נועה" או להשאיר ריק?
4. **שפה**: עברית בלבד או תמיכה באנגלית (פניות מארגונים זרים)?
5. **מודאל אישור** לפני שליחת איין-עמוד למייל פה (כפילות, ספאם זמני, וכו')?
6. **תקרת עלות חודשית** — האם להגדיר limit ולכבות AI אם עוברים אותו?
7. **AI ניסוח הצעות** — חובה לפאזה 3 או יכול לחכות לפאזה 4? (זה הכי מורכב מבחינת UX)

---

## תלויות חיצוניות

- **Anthropic API key** — צריך להגדיר ב-Render.
- **Gmail API**: enable ב-Google Cloud, scope נוסף ל-OAuth consent screen.
- **Pub/Sub topic**: יצירה ב-Google Cloud, הרשאה ל-Gmail API.
- **Cloud Function או Cloud Run**: לקלוט push מ-Pub/Sub. או — Pub/Sub Push subscription ישירות ל-webhook שלנו.

---

## הערכת זמן

- **חבילה A** (Gmail integration): שבוע עבודה
- **חבילה B** (סינון AI): 2-3 ימים
- **חבילה C** (סיכומים): 1-2 ימים
- **חבילה D** (עוזרים): 3-5 ימים

**סה"כ:** ~2-3 שבועות עבודה מרוכזת לאחר פאזה 2.5.

---

## מה אחרי פאזה 3

המערכת בעצם שלמה. דברים שעשויים לעלות:
- **תיעוד קולי** (POC) — אם נועה מבקשת.
- **Meta Lead Ads integration** — כשתתחיל לרוץ קמפיינים.
- **Multi-user/multi-tenant** — אם תרצה למכור את המערכת.
- **App native** — אם web-app לא מספיק.

אבל ה-MVP יסיים בסוף פאזה 3.
