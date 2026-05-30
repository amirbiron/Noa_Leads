# Setup Checklist — Noa_Leads Production

מסמך זה הוא **רשימת פעולות ידניות** להעלאת deploy חדש ב-Render עבור
לקוח חדש. כל הצעדים פה מחייבים את המפעיל (אדיר) — דברים שמטופלים
אוטומטית (migrations, cron jobs, seeds) **לא** רשומים כאן (ראה הערה
בסוף).

ל-reference מלא של כל ה-env vars (כולל אופציונליים), ראה
[`ENV-VARS-REFERENCE.md`](ENV-VARS-REFERENCE.md).

---

## Section 0: הכנות מראש (חד-פעמי, לפני הכל)

חשבונות שצריך לוודא שיש (שלי או של הלקוח, לפי מה שהוסכם):

- [ ] **GitHub** — חשבון של הלקוח לאחסון הריפו השכפול.
- [ ] **Render** — חשבון לעלייה (כרטיס אשראי מקושר).
- [ ] **Google Cloud** — project של הלקוח ל-OAuth Calendar + Gmail.
- [ ] **Anthropic Console** — חשבון ל-API key (`console.anthropic.com`).
- [ ] **Telegram** — חשבון של נועה (לבוט; **אופציונלי**, רק אם רוצים פוש).

---

## Section 1: Repo Setup

- [ ] שכפול (fork או clone) של הריפו `Noa_Leads` לחשבון GitHub של הלקוח.
- [ ] חיבור Render לריפו דרך GitHub integration:
  - Render Dashboard → New → Blueprint → Connect repository.
  - בוחרים את הריפו השכפול → Render מזהה אוטומטית את `render.yaml`.

---

## Section 2: Render Configuration

- [ ] וידוא ש-Blueprint זיהה את `render.yaml`:
  - 2 web services (`noa-leads-backend`, `noa-leads-frontend`),
  - 1 database (`noa-leads-db`),
  - 10 cron jobs (mark_overdue, check_stuck_proposals, check_warm_followups,
    detect_dormant, suggest_dormant_actions, daily_summary, weekly_summary,
    post_meeting_tasks, expire_stale_bookings, renew_calendar_watch,
    renew_gmail_watch, retry_pending_classification, capture_weekly_open_state).
- [ ] PostgreSQL database נוצר אוטומטית מ-`databases:` ב-`render.yaml`.
- [ ] **וידוא ש-`alembic upgrade head` רץ אחרי כל deploy** — מוגדר ב-
  `render.yaml` כ-`preDeployCommand` של ה-backend service. אחרי ה-deploy
  הראשון בדוק את הלוג של ה-backend → "Running upgrade ... -> ..., ..."
  שאומר שכל ה-migrations רצו.
- [ ] **רישום ה-URLs הציבוריים** (יידרשו ב-Section 3 וב-Google Cloud):
  - URL של ה-backend: `https://noa-leads-backend-<hash>.onrender.com`
  - URL של ה-frontend: `https://noa-leads-frontend-<hash>.onrender.com`

---

## Section 3: Environment Variables — חובה

> רק חובה. לכל variable + שינויים אופציונליים → ראה
> [`ENV-VARS-REFERENCE.md`](ENV-VARS-REFERENCE.md).

### 3.1 ליבה (חובה אבסולוטית — בלי זה השרת לא מתפקד)

- [ ] `DATABASE_URL` — auto-provided ע"י Render (`fromDatabase` ב-render.yaml).
  לוודא רק שה-binding ל-`noa-leads-db` תקין.
- [ ] `JWT_SECRET_KEY` — `generateValue: true` ב-render.yaml יוצר אוטומטית.
  **לוודא** ב-Render UI שלא נשאר default `"change-me"`.
- [ ] `CORS_ORIGINS` — URL של ה-frontend (Section 2). דוגמה:
  `https://noa-leads-frontend-<hash>.onrender.com`
- [ ] `FRONTEND_URL` — אותו URL של ה-frontend.
- [ ] `BACKEND_URL` — URL של ה-backend (Section 2). דוגמה:
  `https://noa-leads-backend-<hash>.onrender.com`
- [ ] `NEXT_PUBLIC_API_BASE_URL` (ב-frontend service) — URL של ה-backend.

### 3.2 AI (חובה אם הלקוח מפעיל סיכומים יומיים/שבועיים או Gmail intake)

- [ ] `ANTHROPIC_API_KEY` — מ-`console.anthropic.com` → Settings → API Keys.
- [ ] `SYSTEM_START_DATE` — תאריך go-live של הלקוח, פורמט ISO
  (`YYYY-MM-DD`). דוגמה: `2026-09-01`. **חשוב** — בלי לעדכן ה-default
  הוא תאריך migration ישן (2026-05-23) שיתן אנליטיקות שגויות.

### 3.3 Google integration (חובה אם הלקוח מפעיל Calendar / Gmail intake)

- [ ] `GOOGLE_CLIENT_ID` — מ-Google Cloud Console (ראה Section 4.1).
- [ ] `GOOGLE_CLIENT_SECRET` — אותו מקום.
- [ ] `GOOGLE_REDIRECT_URI` — `<BACKEND_URL>/google/auth/callback`.
- [ ] `GMAIL_REDIRECT_URI` — `<BACKEND_URL>/gmail/auth/callback` (נפרד).
- [ ] `GMAIL_PUBSUB_TOPIC` — name של Pub/Sub topic
  (`projects/PROJECT_ID/topics/TOPIC_NAME`).
- [ ] `SECRETS_ENCRYPTION_KEY` — Fernet key, מייצרים ידנית:
  ```bash
  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
  ```
  פלט: 44 תווים base64. **חובה** ייצור ידני — Render `generateValue` לא יוצר
  ערך תקף ל-Fernet (האלגוריתם דורש פורמט ספציפי).

### 3.4 אופציונלי לפי צורך

- [ ] `TELEGRAM_BOT_TOKEN` — אם הלקוח רוצה פוש על ליד חדש. ראה Section 4.3.
- [ ] `TELEGRAM_OWNER_CHAT_ID` — אם `TELEGRAM_BOT_TOKEN` מוגדר.

---

## Section 4: External Integrations Setup

### 4.1 Google Cloud (Calendar + Gmail)

- [ ] יצירת project ב-`console.cloud.google.com`.
- [ ] הפעלת **Google Calendar API** (APIs & Services → Library).
- [ ] הפעלת **Gmail API** (APIs & Services → Library).
- [ ] OAuth Consent Screen:
  - User Type:
    - **Internal** אם הלקוח על Google Workspace (לא דורש Google
      verification — מהיר ופשוט).
    - **External** אם חשבון אישי (gmail.com) — דורש Google verification
      לפני שמשתמשים אחרים יוכלו לאשר. **(?) לבחור לפי סוג חשבון.**
  - הגדרת App name, support email, developer contact.
- [ ] יצירת **OAuth 2.0 Client ID** (Credentials → Create Credentials →
  OAuth client ID → Web application).
- [ ] Authorized redirect URIs — להוסיף **שתי כתובות**:
  - `<BACKEND_URL>/google/auth/callback` (Calendar)
  - `<BACKEND_URL>/gmail/auth/callback` (Gmail, scope נפרד)
- [ ] שמירת Client ID + Client Secret → להזין ב-Render כ-
  `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`.
- [ ] **Pub/Sub setup** (ל-Gmail push notifications):
  - יצירת topic: Pub/Sub → Topics → Create Topic. שם: `gmail-notifications`
    (או דומה). השם המלא יהיה
    `projects/<PROJECT_ID>/topics/gmail-notifications` → `GMAIL_PUBSUB_TOPIC`.
  - יצירת Push Subscription על אותו topic, Endpoint URL:
    `<BACKEND_URL>/webhooks/gmail`.
  - **הרשאות:** ל-Pub/Sub service account של Google חייבת להיות
    `roles/pubsub.publisher` על ה-topic (Gmail API דורש זאת לפרסם
    אליו). זה מוגדר אוטומטית כש-Gmail watch נרשם.
- [ ] **(?) Service account ל-OIDC verification** — אופציונלי
  (defense-in-depth מעבר לאימות חתימת Google). אם רוצים: יצירת SA →
  copy ה-email → להזין כ-`GMAIL_PUBSUB_SERVICE_ACCOUNT`. אם לא — להשאיר ריק.
- [ ] **בייצור, אחרי שכל ה-vars מוגדרים:** חיבור חשבון Google של הלקוחה
  דרך UI ב-`<FRONTEND_URL>/settings` (כפתור "חיבור Google") — מוביל
  ל-OAuth flow, האסימונים נשמרים מוצפנים ב-DB.

### 4.2 Anthropic

- [ ] התחברות ל-`console.anthropic.com`.
- [ ] Settings → API Keys → Create Key. שמור את ה-key (יוצג רק פעם אחת).
- [ ] Settings → Plans & Billing → לוודא שיש credits או payment method
  פעיל (אחרת ה-API מחזיר 402).
- [ ] הזנת ה-key ב-Render כ-`ANTHROPIC_API_KEY` של ה-backend.

### 4.3 Telegram (אופציונלי)

רק אם הלקוח רוצה פוש על ליד חדש. בלי זה — הליד עדיין נשמר ומופיע ב-UI.

- [ ] שיחה עם `@BotFather` בטלגרם → `/newbot` → לבחור שם (display) +
  username (חייב להסתיים ב-`bot` או `Bot`). יקבל בחזרה token →
  `TELEGRAM_BOT_TOKEN`.
- [ ] **קבלת chat_id של נועה:**
  1. נועה שולחת `/start` לבוט שיצרת.
  2. במכשיר אחר (או דפדפן):
     `https://api.telegram.org/bot<TOKEN>/getUpdates`
  3. בתשובה, חפש `"chat":{"id":NUMBER,...}` → ה-`NUMBER` הוא ה-chat_id.
  4. הזן כ-`TELEGRAM_OWNER_CHAT_ID`.
  - אלטרנטיבה: שלח הודעה לבוט `@userinfobot` בטלגרם → יחזיר את ה-chat_id.

---

## Section 5: Initial Data

### אוטומטי (לא דורש פעולה — אזכור בלבד)

ה-migrations של ה-DB מטעינים אוטומטית עם ה-deploy הראשון:
- 10 תבניות הודעה ראשוניות (migration 0009/0021 — idempotent).
- 6 צ'יפי פעולה מהירה (migration 0010).
- תעריפי שירות ברירת-מחדל (migration 0015).
- 5 צ'יפים מעודכנים לפי SpecV2.1 (migration 0013).

ניתן לערוך את התבניות/צ'יפים/תעריפים דרך ה-UI אחרי deploy.

### ידני (חובה)

- [ ] **יצירת משתמש Owner ראשון.** שתי דרכים:

  **דרך 1 — UI (מומלצת):** אחרי deploy ראשון, פתח את ה-frontend
  בכתובת `<FRONTEND_URL>`. ה-app יזהה ש-DB ריק (`GET /setup/status` →
  `setup_needed: true`) ויפנה אוטומטית ל-`/setup`. מלא email, name,
  password (≥8 תווים) → הליד הופך ל-OWNER ומחובר אוטומטית.

  **דרך 2 — CLI:** אם הלקוח רוצה משתמש דרך SSH/Render shell:
  ```bash
  python -m scripts.create_user \
    --email noa@example.com \
    --name "נועה" \
    --role owner
  ```
  (יבקש סיסמה אינטראקטיבית).

- [ ] **(?) יצירת משתמש Assistant** — אם יש עוזרת בנוסף לנועה.
  אחרי שה-Owner מחובר, יש שתי אופציות:
  - **UI** — Owner יוצר דרך `/settings/users` (אם יש בפיצ'ר ב-UI; כן
    קיים route `POST /users` כ-OwnerOnly).
  - **CLI** — `python -m scripts.create_user --email ... --role assistant`.

  **(?) להחליט עם הלקוחה אם נדרש**, אם כן — להזכיר לבחור דרך לפי הצורך.

---

## Section 6: Smoke Tests

אחרי שכל ה-env vars מוגדרים וכל החיבורים החיצוניים בוצעו:

- [ ] **Backend health check:**
  - `GET <BACKEND_URL>/health` → `{"status":"ok"}`. Render auto-runs
    זה ככה healthcheck.
- [ ] **Login:** פתח את ה-frontend, התחבר כ-Owner שיצרת.
- [ ] **יצירת ליד ידני:** דרך UI (`/leads/new`) או API:
  ```bash
  curl -X POST <BACKEND_URL>/intake/manual \
    -H "Authorization: Bearer <TOKEN>" \
    -H "Content-Type: application/json" \
    -d '{"full_name":"בדיקה","phone":"050-1234567","source_channel":"manual"}'
  ```
  לוודא שהליד מופיע ב-dashboard.
- [ ] **`/today` בדשבורד** טוען בלי שגיאות.
- [ ] **(אם Telegram מוגדר):** יצירת ליד חדש שולחת push לנועה
  בטלגרם תוך שניות.
- [ ] **(אם Google מחובר):**
  - `/settings/google` → כפתור "חיבור" → OAuth flow מצליח → חוזרים
    לדף settings עם status מחובר.
  - בדיקה ידנית של sync: יצירת event ביומן Google → אמור להופיע ב-DB
    תוך דקות (`renew_calendar_watch` cron יוצר watch channel; ה-push
    מגיע ל-`/webhooks/google-calendar`).
- [ ] **(אם AI מוגדר):**
  - הרצה ידנית של cron summary: דרך Render Dashboard → Cron service →
    "Trigger Run". או SSH:
    ```bash
    python -m jobs.daily_summary
    ```
  - לוודא שנכתב row ב-`daily_summaries` ושהוא מוצג בדשבורד כ-bubble.
- [ ] **Cron capture_weekly_open_state** רץ פעם בשבוע ראשון 00:30 IL.
  לוודא אחרי שבוע ראשון שיש row ב-`weekly_open_state_snapshots`.

---

## הערות

### מה מטופל אוטומטית (לא ב-checklist)
- **Migrations:** רצות ב-`preDeployCommand` בכל deploy (`alembic upgrade head`).
- **Cron jobs:** כולם מוגדרים ב-`render.yaml` (13 jobs); Render Blueprint
  טוען אותם אוטומטית. תזמונים ב-UTC.
- **Seeds:** תבניות, צ'יפים, תעריפי שירות — דרך migrations.
- **Schema changes:** אסור לערוך DB ישירות; כל שינוי הוא דרך migration חדש.

### Recovery
- אם cron נכשל, רוב ה-jobs idempotent ו-self-recovering בריצה הבאה.
- ה-DB Render כולל auto-backups (daily snapshots, 7 days retention ב-plan
  `basic-256mb`).
- שינוי env var → restart של ה-service הרלוונטי (Render UI → Manual Deploy).
