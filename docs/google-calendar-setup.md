# הגדרת Google Calendar — צעד-צעד

מסמך זה מסביר איך להגדיר את האינטגרציה ל-Google Calendar (פאזה 2 של
המערכת). חד-פעמי לפני שנועה יכולה להתחבר ליומן שלה דרך /settings.

> דרישות מוקדמות: חשבון Google של נועה (zoneit/gmail/workspace —
> כל אחד מהם עובד), גישת אדמין ל-Render.

---

## 1. יצירת Google Cloud Project

1. כניסה ל-https://console.cloud.google.com
2. בחירת פרויקט קיים או יצירת חדש: למעלה לחיצה על שם הפרויקט → "New Project"
3. שם מומלץ: `noa-leads-crm` (לא חובה, רק לזיהוי)

## 2. הפעלת Calendar API

1. תפריט hamburger → **APIs & Services** → **Enabled APIs**
2. למעלה: **+ Enable APIs and Services**
3. חיפוש "Google Calendar API" → לחיצה → **Enable**

## 3. הגדרת OAuth Consent Screen

לפני שיוצרים credentials, חייבים להגדיר את "מסך ההסכמה" — מה נועה
תראה כשהיא מאשרת חיבור.

1. **APIs & Services** → **OAuth consent screen**
2. **User Type:** External (אלא אם יש Workspace) → Create
3. ב-App information:
   - **App name**: "מערכת ניהול לידים" (זה מה שיופיע ל-נועה)
   - **User support email**: המייל שלך/של נועה
   - **App logo**: אופציונלי
4. **Developer contact email**: המייל שלך
5. Save and Continue
6. **Scopes**: לחיצה על "Add or Remove Scopes" → סינון לפי "calendar":
   - לסמן: `https://www.googleapis.com/auth/calendar` (קריאה+כתיבה)
   - Update → Save and Continue
7. **Test users**: עד שהאפליקציה תקבל verification, רק users שתוסיף כאן
   יכולים להתחבר. הוסף את המייל של נועה (ושל אדיר לבדיקה).
   - Save and Continue
8. סיכום → Back to Dashboard

> **הערה על Verification**: אפליקציה ב-Testing mode עובדת מצוין עד 100
> משתמשים. ל-MVP של נועה זה מספיק בלי תהליך verification של Google
> (שיכול לקחת שבועות).

## 4. יצירת OAuth Client ID

1. **APIs & Services** → **Credentials**
2. **+ Create Credentials** → **OAuth client ID**
3. **Application type**: Web application
4. **Name**: "noa-leads-backend" (לא חשוב)
5. **Authorized JavaScript origins**:
   - `https://noa-leads-frontend.onrender.com` (או הדומיין שלך)
6. **Authorized redirect URIs**:
   - `https://noa-leads-backend.onrender.com/google/auth/callback`
   - **חשוב**: בדיוק כך, עם https ובלי trailing slash
7. **Create**

מקבלים חלון עם **Client ID** ו-**Client Secret**. שניהם נדרשים לשלב הבא.

## 5. ייצור SECRETS_ENCRYPTION_KEY

מפתח Fernet להצפנת refresh_token ב-DB שלנו. ב-terminal מקומי:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

מקבלים מחרוזת ~44 תווים base64. **שמרי אותה לרגע — נדבק ב-Render**.

> **אם המפתח אובד אחרי שהוגדר**: לא ניתן לפענח את הtokens הקיימים.
> במקרה כזה — נועה תצטרך להתנתק ולהתחבר מחדש דרך /settings (זה ייצור
> tokens חדשים עם המפתח החדש).

## 6. הגדרת env vars ב-Render

ב-Render dashboard → noa-leads-backend → **Environment**:

| Key | Value |
|---|---|
| `GOOGLE_CLIENT_ID` | מ-Google Cloud (שלב 4) |
| `GOOGLE_CLIENT_SECRET` | מ-Google Cloud (שלב 4) |
| `GOOGLE_REDIRECT_URI` | `https://noa-leads-backend.onrender.com/google/auth/callback` |
| `FRONTEND_URL` | `https://noa-leads-frontend.onrender.com` |
| `BACKEND_URL` | `https://noa-leads-backend.onrender.com` (לסנכרון הפוך — שלב 14) |
| `SECRETS_ENCRYPTION_KEY` | ראה הסבר מתחת לטבלה |

**ל-`SECRETS_ENCRYPTION_KEY` יש שתי אפשרויות** (לבחור אחת):

- **א. Render auto-generate** — ב-render.yaml או ב-Environment UI לסמן
  `generateValue: true`. Render ייצור ערך אקראי בטוח פעם אחת. **מומלץ
  לפרודקשן** — מפתח לא עובר בכלל דרכך.
- **ב. ידני משלב 5** — מריצים את פקודת ה-Python בשלב 5 ומדביקים את
  הערך כ-value. שימושי אם רוצים לסנכרן את אותו מפתח בין dev/prod (לא
  מומלץ לפרודקשן — אז כל מי שיש לו גישה ל-env vars רואה אותו).

> **אזהרה**: אסור להחליף מפתח אחרי שsecrets נשמרו (refresh_tokens של
> Google). החלפה תכשיל פענוח, ונועה תצטרך להתחבר מחדש דרך /settings.

Save Changes — Render יבצע redeploy אוטומטי.

## 7. אימות domain ב-Search Console (לסנכרון הפוך — שלב 14)

ל-Google Calendar watch channels (push notifications שמודיעים לנו על
שינויים שנועה עושה ביומן) — Google דורש שה-domain של ה-webhook יהיה
**מאומת**.

1. כניסה ל-https://search.google.com/search-console
2. **Add property** → **URL prefix** → `https://noa-leads-backend.onrender.com`
3. **שיטת אימות**: HTML tag (הכי פשוט אם יש שליטה ב-HTML) או DNS
   (אם יש שליטה ב-DNS של onrender.com — אין, אז תבחרי HTML tag).
   - HTML tag: יקבלי `<meta name="google-site-verification" content="...">`.
     הוסיפי אותו כ-endpoint סטטי ב-backend — דרושה תוספת קוד קטנה.
   - **חלופה נוחה יותר**: אם תקנה domain קצר (כמו `noa.co.il`) ותכווני
     אותו ל-Render דרך CNAME — אז יש שליטה DNS ואפשר לאמת דרך TXT record.
4. אחרי אימות: ב-**APIs & Services** → **Domain verification** → ה-domain
   צריך להופיע. אם לא — לחיצה על **Add domain** והקלדת אותו URL.

**חשוב**: בלי אימות הזה, יצירת watch channel תיכשל עם:
`"Unauthorized WebHook callback channel"` בלוגים. כל שאר ה-flow (OAuth,
booking page, אישור, יצירת אירוע) ימשיך לעבוד — רק הסנכרון הפוך
(שינוי/ביטול מהיומן → CRM) יהיה כבוי.

## 8. הגדרת Render Cron Jobs (לתחזוקה אוטומטית)

יש 4 cron jobs שצריך להגדיר ב-Render:

| Job | Schedule | Command | מתי להגדיר |
|---|---|---|---|
| `detect_dormant_leads` | יומי 03:00 | `cd backend && python -m jobs.detect_dormant` | פאזה 1 |
| `post_meeting_tasks` | יומי **02:00** | `cd backend && python -m jobs.post_meeting_tasks` | שלב 15 |
| `expire_stale_bookings` | יומי **03:30** | `cd backend && python -m jobs.expire_stale_bookings` | שלב 13 |
| `renew_calendar_watch` | יומי 04:00 | `cd backend && python -m jobs.renew_calendar_watch` | שלב 14 |

**חשוב**: סדר הריצה של 02:00 → 03:30 חיוני. אם post_meeting ירוץ
*אחרי* expire_stale, ה-bookings כבר יבוטלו ולא תיווצרנה משימות. סדר
ה-cron נשמר ע"י השעות.

ב-Render → **New +** → **Cron Job**:
- **Build Command**: `pip install -r backend/requirements.txt`
- **Schedule**: לפי הטבלה לעיל (cron syntax: `0 2 * * *` = 02:00 יומי)
- **Command**: לפי הטבלה (`cd backend && python -m jobs.<name>`)
- **Environment**: לקשר לאותם env vars של ה-backend service.

## 9. החיבור הראשון מצד נועה

1. נועה נכנסת ל-https://noa-leads-frontend.onrender.com
2. login רגיל
3. ⚙ (גלגל שיניים) → /settings
4. סקציית "Google Calendar" → לחיצה על **"התחברות ליומן Google"**
5. נפתח חלון Google → בוחרת את החשבון שלה → רואה את ה-Consent Screen
   שהגדרנו ("מערכת ניהול לידים מבקשת גישה לקלנדר")
6. **Allow** → חוזרת ל-/settings עם הודעה "חובר בהצלחה"

מאותו רגע, כל BOOKING_APPROVED בפועל ב-/pending ייצור אירוע ביומן שלה
(עם `bookingId=` ב-description לסנכרון דו-כיווני בעתיד).

## פתרון בעיות

### "Error 400: redirect_uri_mismatch"
ה-redirect URI ב-Google Cloud לא תואם מילולית למה שנשלח. וודאי:
- `https://` ולא `http://`
- בלי trailing slash
- בלי לוכסן בסוף
- הדומיין מדויק (לדוגמה אם render הוא `noa-leads-backend-xyz.onrender.com`)

### "Access blocked: noa-leads-crm has not completed Google verification"
המייל שמנסה להתחבר לא ברשימת Test Users (שלב 3, סעיף 7). הוסיפי אותו.

### "החיבור פג תוקף" ב-/settings
Refresh token עלול לפוג אם:
- המשתמשת ניתקה את האפליקציה דרך Google Account → My Apps
- Google חיכה ל-180 יום בלי שימוש (לא רלוונטי אצלנו — יש cron)
- שונה ה-`SECRETS_ENCRYPTION_KEY` (לא ניתן לפענח הישן)

הפתרון: לחיצה על "התחברות מחדש" ב-/settings — מתחיל OAuth מחדש.
