# הגדרת Gmail Push Notifications (Pub/Sub)

מדריך לאדיר — להגדיר ב-Google Cloud Console ו-Render כדי שמיילים שמגיעים
ל-Gmail של נועה יקפצו אוטומטית כלידים במערכת.

> אם כל זה נראה מאיים: אפשר להריץ את שלבים 1–3 פעם אחת ב-Google Cloud
> Console (UI ברור עם buttons), אחר כך 4 דקות ב-Render UI, וזהו.

## תלויות מוקדמות

- שלב 1 של פאזה 2 (Google Calendar) כבר מוגדר → קיים project, OAuth client,
  ו-`GOOGLE_CLIENT_ID/SECRET`. נשתמש באותם פרטים.
- ה-backend פרוס ל-Render עם URL ציבורי (`https://noa-leads-backend.onrender.com`).
- `BACKEND_URL` env var מוגדר ב-Render.

## שלב 1 — הפעלת Gmail API + Pub/Sub API

ב-Google Cloud Console → [APIs & Services > Library](https://console.cloud.google.com/apis/library):

1. חפש **Gmail API** → "Enable".
2. חפש **Cloud Pub/Sub API** → "Enable".

(אם כבר ראית checkmark — מצוין, אין צורך לעשות שוב.)

## שלב 2 — הוספת Gmail scope ל-OAuth consent

ב-[OAuth consent screen](https://console.cloud.google.com/apis/credentials/consent):

1. "Edit App" → סמל ✏️ ליד Scopes.
2. "Add or Remove Scopes" → סמן:
   - `https://www.googleapis.com/auth/gmail.readonly`
   - `https://www.googleapis.com/auth/gmail.modify`
3. "Update" → "Save and Continue".

> Gmail.modify נדרש כדי להוסיף תווית "סוננו אוטומטית" למיילים שה-AI סינן
> כספאם, בלי לקרוא או למחוק שום דבר אחר.

## שלב 3 — הוספת Gmail redirect URI ל-OAuth client

ב-[Credentials](https://console.cloud.google.com/apis/credentials):

1. פתח את ה-OAuth 2.0 Client שכבר יצרת עבור Calendar.
2. תחת **Authorized redirect URIs** הוסף:
   ```
   https://noa-leads-backend.onrender.com/google/gmail/callback
   ```
   (החלף `noa-leads-backend.onrender.com` לדומיין הפרודקשן האמיתי.)
3. "Save".

## שלב 4 — יצירת Pub/Sub topic

ב-[Pub/Sub > Topics](https://console.cloud.google.com/cloudpubsub/topic):

1. "Create Topic":
   - Topic ID: `gmail-incoming` (כל שם עובד; השם נכנס ל-env var).
   - השאר ברירות מחדל ("Add a default subscription" אפשר להשאיר מסומן —
     ניצור subscription נוסף בשלב 6).
2. "Create".

ה-topic נראה עכשיו: `projects/<PROJECT_ID>/topics/gmail-incoming` —
שמור את ה-string הזה.

## שלב 5 — הענקת publish permission ל-Gmail

ב-Topic שנוצר → "Permissions" (panel ימני):

1. "Add Principal".
2. New principals:
   ```
   gmail-api-push@system.gserviceaccount.com
   ```
   (זה service account של Gmail עצמו — קבוע, לא מזהה שלך.)
3. Role: **Pub/Sub Publisher**.
4. "Save".

> בלי השלב הזה, Gmail מקבל "permission denied" כשהוא מנסה לפרסם הודעות
> ל-topic, ולא יגיע כלום ל-webhook.

## שלב 6 — יצירת Push subscription

ב-Pub/Sub → ה-topic שנוצר → "Subscriptions" → "Create Subscription":

1. **Subscription ID:** `gmail-incoming-push` (כל שם).
2. **Topic:** הtopic שיצרת.
3. **Delivery type:** **Push**.
4. **Endpoint URL:**
   ```
   https://noa-leads-backend.onrender.com/webhooks/gmail
   ```
5. **Enable authentication** ✓.
   - **Service account:** בחר את ה-default Compute Engine SA, או צור SA
     ייעודי (`gmail-push-sa@<PROJECT>.iam.gserviceaccount.com`) — שניהם
     עובדים. SA ייעודי עדיף מבחינת least privilege.
   - **Audience:** השאר ברירת מחדל (Pub/Sub ישתמש ב-URL כ-audience אם לא
     מציינים — זה בדיוק מה שאנחנו רוצים).
6. **Acknowledgement deadline:** 10 שניות (default).
7. "Create".

## שלב 7 — env vars ב-Render

ב-[Render Dashboard](https://dashboard.render.com) → ה-web service
`noa-leads-backend`:

| Env var | ערך |
|---|---|
| `GMAIL_REDIRECT_URI` | `https://noa-leads-backend.onrender.com/google/gmail/callback` |
| `GMAIL_PUBSUB_TOPIC` | `projects/<PROJECT_ID>/topics/gmail-incoming` (מ-שלב 4) |
| `GMAIL_PUBSUB_SERVICE_ACCOUNT` | אופציונלי — ה-email של ה-SA משלב 6, למשל `gmail-push-sa@<PROJECT>.iam.gserviceaccount.com`. אם תשאיר ריק, רק חתימת Google תיבדק (פחות חזק, אך עדיין מאומת). |
| `BACKEND_URL` | `https://noa-leads-backend.onrender.com` (אם עוד לא היה) |

> כל ה-env vars האחרים (GOOGLE_CLIENT_ID/SECRET, SECRETS_ENCRYPTION_KEY,
> ANTHROPIC_API_KEY) כבר מוגדרים משלבים קודמים.

אותם משתנים גם ל-cron `noa-renew-gmail-watch` (כבר מוגדר) ול-cron
`noa-retry-pending-classification` (חדש בפאזה 3 commit 4/4) — מהדרישות
שמופיעות ב-`render.yaml`.

## שלב 8 — חיבור Gmail ב-UI של נועה

אחרי deploy:

1. נועה נכנסת ל-`/settings`.
2. בקובץ Gmail → "התחבר ל-Gmail" → OAuth flow → אישור scopes.
3. אחרי הצלחה, השרת:
   - שומר tokens מוצפנים.
   - קורא ל-`users.watch()` עם ה-topic מהenv.
   - שומר history_id התחלתי.

מעכשיו: כל מייל חדש → Gmail מפרסם ל-topic → Pub/Sub שולח push ל-webhook
→ אנחנו מסווגים → יוצרים ליד.

## שלב 9 — בדיקה

1. שלח לעצמך מייל לחשבון Gmail שחיברת.
2. תוך 30 שניות, פתח `/leads` במערכת — הליד צריך להופיע.
3. בלוגים של ה-backend: שורות `Gmail history: 1 new message(s)` ו-
   `msg <id> → lead <id> created`.

### בדיקת ספאם

שלח לעצמך מ-`newsletter@<דומיין>.com` → ה-AI צריך לסווג כלא-עסקי,
לשים תווית "סוננו אוטומטית" ב-Gmail, ולא ליצור ליד.

## תחזוקה

| מצב | תגובת המערכת |
|---|---|
| Watch פג (Gmail max 7 ימים) | cron `noa-renew-gmail-watch` רץ יומי 05:00 ישראל ומחדש אם נשארו <24h. |
| `history_id` נישן (>7 ימים) | webhook מקבל 404, מאפס history_id, ה-cron הבא של renew יקבל id טרי. |
| Pub/Sub push נכשל | Pub/Sub מנסה שוב עם exponential backoff. אם 7 ימים עוברים בלי success — message נזרק (default retention). |
| AI מסרב לסווג (rate limit / שגיאה) | המייל נשמר ב-DB עם retry_count=0; cron `noa-retry-pending-classification` רץ כל דקה ומנסה שוב. אחרי 10 ניסיונות — ליד עם דגל `manual_review_needed`. |
| Tokens של Gmail פגו / נשללו | המערכת שולחת התראה לטלגרם של נועה ("החיבור ל-Gmail פג, יש להתחבר מחדש"). |

## עלויות צפויות

- **Pub/Sub:** $0.04 לכל מיליון messages. ~50 מיילים ביום → ~1,500 בחודש →
  $0 ($40 free tier כיסוי מלא).
- **Gmail API:** חינם עד quota גבוה.
- **Anthropic API:** ~$0.001 לסיווג + ~$0.002 לextract = ~$0.003 לליד.
  50 לידים ביום → ~$4.5 בחודש.

סה"כ Gmail+AI לחודש: כ-$5.
