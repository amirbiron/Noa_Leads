# ENV-VARS-REFERENCE — מסמך הסבר לכל משתני הסביבה במערכת

מסמך זה הוא **reference מלא** של כל ה-env vars במערכת Noa_Leads — חובה
ואופציונליים, עם תיאור, מקור, ערכים לדוגמה. ל-**checklist ממוקד-פעולה**
של setup ראשוני ב-Render, ראה [`SETUP-CHECKLIST.md`](SETUP-CHECKLIST.md).

כל ה-vars נטענים ב-`backend/app/config.py` (Settings class, pydantic).
ערכי default מתועדים שם.

**שינוי בעתיד:** כל env var ניתן לעדכון ב-Render UI בלי redeploy. תידרש
פעולת restart של ה-service לתחולה (`get_settings()` cached per process).

---

## 1. General

### `APP_ENV`
- **סטטוס:** אופציונלי (default).
- **תיאור:** סביבת הפעלה — `development` / `production`. משפיע על
  התנהגות לוגינג ועל עיגול תאריכים בדוגמאות.
- **ערך לדוגמה:** `production`
- **Default:** `development`
- **מקור:** `backend/app/config.py:21`

### `LOG_LEVEL`
- **סטטוס:** אופציונלי (default).
- **תיאור:** רמת logging של ה-backend.
- **ערך לדוגמה:** `INFO` (בפרודקשן) / `DEBUG` (לדיבאג זמני)
- **Default:** `INFO`
- **מקור:** `backend/app/config.py:22`

### `TIMEZONE`
- **סטטוס:** אופציונלי (default).
- **תיאור:** TZ של המערכת. לרוב לא צריך לשנות — הקוד תלוי `Asia/Jerusalem`
  במספר מקומות (חישובי שבת/חג/work hours).
- **ערך לדוגמה:** `Asia/Jerusalem`
- **Default:** `Asia/Jerusalem`
- **מקור:** `backend/app/config.py:23`

---

## 2. Database

### `DATABASE_URL`
- **סטטוס:** **חובה.**
- **תיאור:** PostgreSQL async connection string. נטען אוטומטית מתוך
  `databases:` ב-`render.yaml` דרך `fromDatabase`. הקוד עושה נרמול
  אוטומטי של `postgres://` ו-`postgresql://` ל-`postgresql+asyncpg://`.
- **איפה משיגים:** Render auto-provide (PostgreSQL add-on).
- **ערך לדוגמה:** `postgresql+asyncpg://user:pass@host:5432/dbname`
- **Default:** `postgresql+asyncpg://user:password@localhost:5432/noa_leads` (לdev בלבד)
- **מקור:** `backend/app/config.py:26`, נרמול ב-`config.py:111-123`

---

## 3. Authentication & JWT

### `JWT_SECRET_KEY`
- **סטטוס:** **חובה.**
- **תיאור:** מפתח חתימה ל-JWT tokens. **חייב להיות חזק וייחודי בפרודקשן**
  — חתימה חלשה = compromise של כל ה-sessions.
- **איפה משיגים:** Render `generateValue: true` ב-`render.yaml` מייצר
  אוטומטית. אפשר גם ידנית: `openssl rand -hex 32`.
- **ערך לדוגמה:** `7d6f2a1c... (32+ תווים hex)`
- **Default:** `change-me` (mustn't ship to prod!)
- **מקור:** `backend/app/config.py:29`

### `JWT_ALGORITHM`
- **סטטוס:** אופציונלי (default).
- **תיאור:** אלגוריתם חתימה. לא לשנות אלא אם יש צורך ספציפי.
- **Default:** `HS256`
- **מקור:** `backend/app/config.py:30`

### `JWT_ACCESS_TOKEN_MINUTES`
- **סטטוס:** אופציונלי (default).
- **תיאור:** משך חיי access token (דקות).
- **Default:** `30`
- **מקור:** `backend/app/config.py:31`

### `JWT_REFRESH_TOKEN_DAYS`
- **סטטוס:** אופציונלי (default).
- **תיאור:** משך חיי refresh token (ימים).
- **Default:** `14`
- **מקור:** `backend/app/config.py:32`

---

## 4. CORS & URLs

### `CORS_ORIGINS`
- **סטטוס:** **חובה בפרודקשן.**
- **תיאור:** רשימת origins מורשים (מופרדים בפסיק) ל-CORS. ה-frontend
  צריך להיות ברשימה אחרת ה-API חוסם.
- **ערך לדוגמה:** `https://noa-leads-frontend.onrender.com`
- **Default:** `http://localhost:3000` (לdev בלבד)
- **מקור:** `backend/app/config.py:35`

### `FRONTEND_URL`
- **סטטוס:** **חובה בפרודקשן.**
- **תיאור:** כתובת ה-frontend. משמש ב-OAuth callbacks (redirect חזרה
  אחרי authorize) ובקישורים בהתראות (e.g., link בטלגרם).
- **ערך לדוגמה:** `https://noa-leads-frontend.onrender.com`
- **Default:** `http://localhost:3000`
- **מקור:** `backend/app/config.py:93`

### `BACKEND_URL`
- **סטטוס:** **חובה בפרודקשן — incident-grade.** הגדר תמיד, גם אם
  הלקוח לא מתחבר ל-Google Calendar ביום הראשון. ברגע שמחברים, בלי
  ה-var האינטגרציה תישבר אחרי 7 ימים בשקט.
- **תיאור:** כתובת ציבורית של ה-backend (HTTPS). נדרשת לרישום Google
  Calendar watch channels (Google שולח push notifications ל-
  `<BACKEND_URL>/webhooks/google-calendar`). cron `renew_calendar_watch`
  מחדש את ה-channel יומית; אם `BACKEND_URL` לא מוגדר → ה-cron
  מדלג בשקט, ה-watch הקיים פג תוקף תוך ~7 ימים → sync הפוך
  (Google → DB) נשבר ללא error הנראה למשתמש.
- **incident report:** קרה בפרודקשן — sync הפסיק לעבוד בשבוע השני,
  לקח זמן לאתר כי אין error log קולני.
- **ערך לדוגמה:** `https://noa-leads-backend.onrender.com`
- **Default:** `None`
- **מקור:** `backend/app/config.py:99`

---

## 5. Encryption

### `SECRETS_ENCRYPTION_KEY`
- **סטטוס:** **חובה אם משתמשים ב-Google OAuth (Calendar / Gmail).**
- **תיאור:** Fernet key להצפנת OAuth refresh tokens ב-DB. אם לא מוגדר,
  ה-tokens נשמרים plaintext (סיכון אבטחה חמור בפרודקשן).
- **איפה משיגים:** generation ידני:
  ```bash
  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
  ```
  פלט: 32 bytes URL-safe base64 (44 תווים). **שמור אותו** — אם תאבד
  אותו, tokens שמורים בעבר לא ניתנים לפענוח.
  **שים לב:** Render `generateValue: true` **לא** מייצר ערך תקף ל-Fernet
  (יוצר אלפא-נומרי אקראי). חייב להזין ידנית.
- **ערך לדוגמה:** `Hl9j2K... (44 תווים base64)`
- **Default:** `None`
- **מקור:** `backend/app/config.py:89`

---

## 6. Google OAuth & Pub/Sub

### `GOOGLE_CLIENT_ID`
- **סטטוס:** **חובה אם משתמשים ב-Google integration.**
- **תיאור:** OAuth 2.0 Client ID. משותף בין Calendar ל-Gmail (אותו
  Google project, אותו consent screen).
- **איפה משיגים:** Google Cloud Console → APIs & Services → Credentials
  → Create OAuth Client ID (Web Application).
- **ערך לדוגמה:** `123456789-abcdef.apps.googleusercontent.com`
- **Default:** `None`
- **מקור:** `backend/app/config.py:75`

### `GOOGLE_CLIENT_SECRET`
- **סטטוס:** **חובה אם משתמשים ב-Google integration.**
- **תיאור:** OAuth 2.0 Client Secret, תואם ל-`GOOGLE_CLIENT_ID`.
- **איפה משיגים:** אותו מקום של ה-Client ID (Google Cloud Console).
- **Default:** `None`
- **מקור:** `backend/app/config.py:76`

### `GOOGLE_REDIRECT_URI`
- **סטטוס:** **חובה ל-Calendar.**
- **תיאור:** Callback URL ל-OAuth של Google Calendar. חייב להיות **רשום
  בדיוק** ב-Authorized redirect URIs של ה-OAuth Client (Google Cloud Console).
- **ערך לדוגמה:** `https://noa-leads-backend.onrender.com/google/auth/callback`
- **Default:** `None`
- **מקור:** `backend/app/config.py:77`

### `GMAIL_REDIRECT_URI`
- **סטטוס:** **חובה ל-Gmail intake.**
- **תיאור:** Callback URL נפרד ל-OAuth של Gmail (scope אחר → callback
  אחר). חייב להיות רשום ב-Authorized redirect URIs בנפרד.
- **ערך לדוגמה:** `https://noa-leads-backend.onrender.com/gmail/auth/callback`
- **Default:** `None`
- **מקור:** `backend/app/config.py:80`

### `GMAIL_PUBSUB_TOPIC`
- **סטטוס:** **חובה ל-Gmail intake (push notifications).**
- **תיאור:** שם topic של Google Cloud Pub/Sub ל-Gmail watch (push). אם
  לא מוגדר → cron `renew_gmail_watch` ידלג בשקט.
- **איפה משיגים:** Google Cloud Console → Pub/Sub → Create Topic, ואז
  Subscription מסוג Push לכתובת `<BACKEND_URL>/webhooks/gmail`.
- **ערך לדוגמה:** `projects/my-project-id/topics/gmail-notifications`
- **Default:** `None`
- **מקור:** `backend/app/config.py:81`

### `GMAIL_PUBSUB_SERVICE_ACCOUNT`
- **סטטוס:** אופציונלי (defense-in-depth).
- **תיאור:** Service account email שחתום על ה-OIDC token של Pub/Sub
  Push. אם מוגדר — ה-webhook יאמת שה-token חתום ע"י ה-SA הספציפי
  (מעבר לאימות חתימת Google הרגיל). אם `None` — רק חתימת Google.
- **איפה משיגים:** Google Cloud Console → IAM → Service Accounts.
- **ערך לדוגמה:** `gmail-pubsub@my-project.iam.gserviceaccount.com`
- **Default:** `None`
- **מקור:** `backend/app/config.py:85`

---

## 7. Anthropic / AI

### `ANTHROPIC_API_KEY`
- **סטטוס:** **חובה אם משתמשים בפיצ'רי AI** (סיכומים יומיים/שבועיים,
  סיווג מיילים, הצעת פעולה לליד רדום).
- **תיאור:** API key ל-Claude API.
- **איפה משיגים:** `console.anthropic.com` → Settings → API Keys → Create Key.
- **ערך לדוגמה:** `sk-ant-api03-...`
- **Default:** `None`
- **מקור:** `backend/app/config.py:42`

### `AI_MODEL_FAST`
- **סטטוס:** אופציונלי (default).
- **תיאור:** מודל ברירת-מחדל לפעולות מהירות/זולות (e.g., classification).
  משמש כ-fallback לכל override שלא הוגדר.
- **Default:** `claude-haiku-4-5`
- **מקור:** `backend/app/config.py:46`

### `AI_MODEL_QUALITY`
- **סטטוס:** אופציונלי (default).
- **תיאור:** מודל ברירת-מחדל לפעולות איכותיות (e.g., סיכומים, drafts).
- **Default:** `claude-sonnet-4-6`
- **מקור:** `backend/app/config.py:47`

### `AI_MODEL_EMAIL_CLASSIFIER`
- **סטטוס:** אופציונלי (None → יורש מ-FAST).
- **תיאור:** override למודל סיווג מיילים.
- **Default:** `None` (יורש)
- **מקור:** `backend/app/config.py:48`

### `AI_MODEL_DAILY_SUMMARY`
- **סטטוס:** אופציונלי (None → יורש מ-QUALITY).
- **תיאור:** override למודל סיכום יומי.
- **Default:** `None` (יורש)
- **מקור:** `backend/app/config.py:49`

### `AI_MODEL_WEEKLY_SUMMARY`
- **סטטוס:** אופציונלי (None → יורש מ-QUALITY).
- **תיאור:** override למודל סיכום שבועי.
- **Default:** `None` (יורש)
- **מקור:** `backend/app/config.py:50`

### `AI_MODEL_PROPOSAL_DRAFT`
- **סטטוס:** אופציונלי (None → יורש מ-QUALITY).
- **תיאור:** override למודל draft של הצעה.
- **Default:** `None` (יורש)
- **מקור:** `backend/app/config.py:51`

### `AI_MODEL_DORMANT_SUGGESTION`
- **סטטוס:** אופציונלי (default).
- **תיאור:** מודל להצעת פעולה לליד רדום (§19 D.1). default Opus בכוונה
  לאיכות (לא יורש מ-QUALITY כי החלטה אסטרטגית רגישה).
- **Default:** `claude-opus-4-7`
- **מקור:** `backend/app/config.py:54`

### `AI_FILTER_LABEL_NAME`
- **סטטוס:** אופציונלי (default).
- **תיאור:** שם תווית Gmail למיילים שסוננו ע"י AI כספאם. שינוי **לא
  retroactive** (תוויות ישנות לא ישתנו).
- **Default:** `"סוננו אוטומטית"`
- **מקור:** `backend/app/config.py:57`

### `AI_CLASSIFY_CONFIDENCE_THRESHOLD`
- **סטטוס:** אופציונלי (default).
- **תיאור:** סף בטחון לסיווג מיילים. מתחת לסף → ליד מסומן
  `low_confidence_classification=true`.
- **Default:** `0.7`
- **מקור:** `backend/app/config.py:59`

### `AI_MAX_CLASSIFICATION_RETRIES`
- **סטטוס:** אופציונלי (default).
- **תיאור:** מספר ניסיונות של cron `retry_pending_classification` לפני
  שמסמן `manual_review_needed=true`. שמרני (10 דקות ל-API להתאושש).
- **Default:** `10`
- **מקור:** `backend/app/config.py:62`

### `AI_TEMPERATURE_SUMMARIES`
- **סטטוס:** אופציונלי (default).
- **תיאור:** temperature לסיכומי AI. 0.5 = איזון יציבות/גיוון ניסוח.
- **Default:** `0.5`
- **מקור:** `backend/app/config.py:66`

### `AI_MAX_OUTPUT_TOKENS_SUMMARIES`
- **סטטוס:** אופציונלי (default).
- **תיאור:** מקסימום טוקנים לפלט של סיכומי AI. 2000 מספיק ל-500 מילים
  + מבנה JSON.
- **Default:** `2000`
- **מקור:** `backend/app/config.py:67`

### `SYSTEM_START_DATE`
- **סטטוס:** **מומלץ לעדכן ל-go-live של הלקוח** (פורמט ISO `YYYY-MM-DD`).
- **תיאור:** תאריך תחילת המערכת — קבוע. ממנו נגזרים `days_in_system`
  ביומי ו-`week_number_in_system` + `has_comparison_data` בשבועי.
- **ערך לדוגמה:** `2026-09-01`
- **Default:** `2026-05-23` (תאריך migration הראשון; לא נכון לפר-לקוח).
- **מקור:** `backend/app/config.py:72`

---

## 8. Telegram

### `TELEGRAM_BOT_TOKEN`
- **סטטוס:** אופציונלי (פיצ'ר degrades silently אם חסר).
- **תיאור:** token של בוט Telegram שמשמש לפוש כשליד חדש נכנס.
- **איפה משיגים:** שיחה עם `@BotFather` בטלגרם → `/newbot` → קבל token.
- **ערך לדוגמה:** `1234567890:ABCdefGHIjklMNOpqrSTUvwxYZ`
- **Default:** `None`
- **מקור:** `backend/app/config.py:38`

### `TELEGRAM_OWNER_CHAT_ID`
- **סטטוס:** אופציונלי (חובה אם `TELEGRAM_BOT_TOKEN` מוגדר).
- **תיאור:** מזהה צ'אט של נועה (לאן נשלחות התראות לידים חדשים).
- **איפה משיגים:** שלח `/start` לבוט שיצרת, אז GET לכתובת
  `https://api.telegram.org/bot<TOKEN>/getUpdates` ולחפש `chat.id`.
  או דרך בוט עזר כמו `@userinfobot`.
- **ערך לדוגמה:** `123456789` (מספר חיובי או שלילי, לקבוצות שלילי)
- **Default:** `None`
- **מקור:** `backend/app/config.py:39`

---

## 9. Work Hours

### `WORK_DAY_START_HOUR`
- **סטטוס:** אופציונלי (default).
- **תיאור:** שעת תחילת יום עבודה (0-23). משפיע על תיוג after-hours,
  scheduling של tasks, וכו'.
- **Default:** `9`
- **מקור:** `backend/app/config.py:102`

### `WORK_DAY_END_HOUR`
- **סטטוס:** אופציונלי (default).
- **תיאור:** שעת סיום יום עבודה (0-23).
- **Default:** `18`
- **מקור:** `backend/app/config.py:103`

### `FRIDAY_CLOSE_HOUR`
- **סטטוס:** אופציונלי (default).
- **תיאור:** שעת סיום ביום שישי (סיום מוקדם — שבוע יהודי).
- **Default:** `16`
- **מקור:** `backend/app/config.py:104`

---

## 10. Frontend (Next.js)

### `NEXT_PUBLIC_API_BASE_URL`
- **סטטוס:** **חובה בפרודקשן.**
- **תיאור:** כתובת ה-backend של ה-FastAPI. ה-frontend פונה אליה לכל
  בקשת API. הקידומת `NEXT_PUBLIC_` נדרשת כדי שתהיה זמינה בקליינט.
- **ערך לדוגמה:** `https://noa-leads-backend.onrender.com`
- **Default:** `http://localhost:8000`
- **מקור:** `frontend/lib/api.ts:45`, `frontend/.env.example:2`

---

## 11. (?) לעתיד — לא ממומש כיום

סעיף זה מתעד env vars שיתווספו כשפיצ'רים עתידיים ייכנסו למימוש.
**אין צורך להגדיר אותם ב-deploy הנוכחי** — להוסיף רק כשהפיצ'ר נכנס לקוד.

### `OPENAI_API_KEY`
- **סטטוס:** **(?) לעתיד — לא קיים בקוד הנוכחי.**
- **תיאור:** API key ל-OpenAI לצורך תמלול קולי (`gpt-4o-transcribe` —
  המודל הנבחר לעברית). מתואר ב-`docs/tech-spec.md:457` ("מודל:
  gpt-4o-transcribe (הכי מדויק לעברית)") וב-`docs/SpecV2.1.md:132`
  בטבלת ספקים ("OpenAI Whisper (gpt-4o-transcribe) — תיעוד קולי -
  אופציונלי").
- **איפה משיגים:** `platform.openai.com` → API Keys.
- **ערך לדוגמה:** `sk-proj-...`
- **Default:** N/A — השדה לא קיים ב-`backend/app/config.py` כיום.
- **כשנכנס למימוש:** להוסיף ל-`config.py` (Settings field
  אופציונלי), `requirements.txt` (`openai`), `ENV-VARS-REFERENCE.md`
  (להעביר מסעיף 11 למיקום קבוע), ו-`SETUP-CHECKLIST.md` (להעביר
  מ-3.C ל-3.A.2 או סעיף נפרד).

---

## נספח: defaults וה-startup minimum

המערכת **יכולה לעלות** רק עם:
- `DATABASE_URL` (חובה — אחרת crash בעלייה).
- `JWT_SECRET_KEY` (חובה — אחרת auth שבור).

כל שאר ה-features מתפקדות באופן מותנה לפי מה שהוגדר:
- **בלי** `ANTHROPIC_API_KEY` → אין AI summaries, אין email classification,
  אין dormant suggestions. ליד intake עדיין עובד.
- **בלי** `GOOGLE_*` → אין Calendar/Gmail integration. ליד intake עדיין
  עובד (manual / phone / WhatsApp dashboards).
- **בלי** `TELEGRAM_*` → אין פוש לליד חדש; הליד עדיין נשמר ומופיע ב-UI.
- **בלי** `BACKEND_URL` → Calendar watch channels לא נוצרים (סנכרון
  הפוך כבוי), אבל one-way (booking → calendar) עדיין עובד.

---

## הערות שימוש

- כל ה-vars **case-insensitive** (`Settings` עם `case_sensitive=False`).
  אפשר להגדיר `database_url` או `DATABASE_URL` — אותו דבר.
- `extra="ignore"` ב-`SettingsConfigDict` → vars לא-מוכרים נדחים בשקט,
  לא crash. שמור על שמות מדויקים.
- שינוי env var ב-Render → **חייב restart של ה-service** (`get_settings()`
  cached דרך `lru_cache`).
