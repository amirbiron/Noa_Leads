# Google Calendar — Blueprint לפאזה 2

> **⚠️ מסמך ייחוס חיצוני, לא חלק מהאפיון של נועה.**
>
> זהו תיעוד מימוש מפרויקט אחר ש-amirbiron כתב, שמיועד לשמש כ-blueprint
> ארכיטקטוני בעת בניית פאזה 2 (אינטגרציית Google Calendar) במערכת
> ניהול הלידים של נועה.
>
> **לא כל מה שכתוב כאן רלוונטי אצלנו.** הפרויקט המקורי משתמש ב-Telegram
> ConversationHandler ו-WhatsApp Twilio לקביעת תורים, בעוד שאצלנו
> דף קביעת תור הוא **דף ווב ציבורי** (`/book/{lead_token}`). יש לאמץ
> רק את החלקים הרלוונטיים.
>
> **מתי לעיין:** כשעובדים על פאזה 2 (Google Calendar), במיוחד בנושאים
> OAuth, הצפנת tokens, FreeBusy, watch channels, וטיפול ב-RefreshError.

---

## חלקים שכן ניקח (high relevance)

| נושא | למה רלוונטי |
|---|---|
| OAuth flow עם PKCE + state ב-session | בדיוק מה שצריך ל-`/google/connect`, `/google/callback` |
| טבלת `google_calendar_credentials` (singleton) | המודל המדויק שצריך אצלנו |
| `SECRETS_ENCRYPTION_KEY` להצפנת refresh_token | חובה לפרודקשן |
| `_get_credentials()` עם refresh logic + RefreshError handling | דפוס מוכח |
| `auth_invalid_at` + `owner_alert_sent_at` | מונע ספאם התראות כשהטוקן פג |
| `get_available_slots` עם FreeBusy + DB busy | לדף הזמינות שלנו — תורים שעוד לא ביומן (BOOKING_PENDING) חייבים להופיע כתפוסים |
| `bookingId=<id>` ב-event description | עוגן לסנכרון דו-כיווני |
| Partial unique index למניעת כפילויות | מומלץ — נטמיע ב-`bookings` שלנו |
| Watch channels + webhook + syncToken | לסנכרון הפוך (פאזה 2.5) |
| HTTP 410 = success ב-`delete_event` | detail קטן וחשוב |

## חלקים שלא רלוונטיים אצלנו (skip)

| נושא | למה לא |
|---|---|
| Telegram ConversationHandler לקביעת תור | אצלנו דף ווב, לא בוט |
| WhatsApp Twilio booking + state machine | אצלנו וואטסאפ ידני, לא Twilio |
| Inline calendar keyboard ב-Telegram | לא רלוונטי לדף ווב |
| `auto_booking_mode` (3 מצבים) | האפיון של נועה מפורש: רק `manual` — "ממתין לאישור X" |
| 1600 chars WhatsApp wrapper | לא רלוונטי |
| Referral / live chat guard | לא במערכת שלנו |

---

# המסמך המקורי

## 1) OAuth Flow עם Google Calendar

**קבצים בפרויקט המקורי:**
- `google_calendar.py` (שורות 104–168, 211–250)
- `admin/app.py` (שורות 2315–2384)

**Scopes:** `https://www.googleapis.com/auth/calendar` (קריאה+כתיבה).

**משתני סביבה** (`.env.example` שורות 90–95):
```
GOOGLE_CLIENT_ID=""
GOOGLE_CLIENT_SECRET=""
GOOGLE_REDIRECT_URI="https://your-domain.com/google/callback"
SECRETS_ENCRYPTION_KEY="..."   # להצפנת tokens ב-DB
```

**זרימה:**
1. `GET /google/connect` → `google_connect()` יוצר OAuth flow עם PKCE (`google-auth-oauthlib`). `state` נשמר ב-session ל-CSRF.
2. Google מבצע redirect ל-`GET /google/callback` → `google_callback()`. ולידציה של `state`, ואז:
3. `exchange_code_for_credentials(code, code_verifier)`:
   - `flow.fetch_token(code=code)`
   - `service.calendars().get(calendarId="primary").execute()` לקבלת אימייל ו-timezone
   - `db.save_google_calendar_credentials(...)` שומר ל-DB: `google_account_email`, `calendar_id`, `refresh_token`, `access_token`, `token_expiry`, `timezone`.

**Refresh token logic (`_get_credentials()`, שורות 211–250):**
- טעינת `refresh_token` מ-DB, יצירת `Credentials` עם `token_uri`+client creds.
- אם `creds.expired` → `creds.refresh(Request())` ושמירת access_token חדש.
- במקרה `RefreshError` → סימון `auth_invalid_at` ב-DB וקריאה ל-`_notify_owner_calendar_disconnected()` (Telegram/WhatsApp), עם `owner_alert_sent_at` למניעת התראות חוזרות.

**עזרי DB:** `is_google_calendar_auth_invalid()`, `set_google_calendar_auth_invalid()`, `clear_google_calendar_auth_invalid()`.

## 2) דף קביעת תור (Telegram + WhatsApp) — *לא רלוונטי אצלנו*

> אצלנו זה דף ווב ציבורי, לא בוט. בכל זאת — הלוגיקה של "בדיקה חוזרת מול
> Google לפני יצירה" + "הגנת double-tap" רלוונטית.

**States:** `BOOKING_SERVICE` → `BOOKING_DATE` → `BOOKING_TIME` → `BOOKING_CONFIRM`.

הקבצים המקוריים: `bot/handlers.py` (1245–1663), `bot/calendar_keyboard.py`, `messaging/whatsapp_booking.py`.

## 3) חישוב סלוטים פנויים

**קובץ:** `google_calendar.py` שורות 294–447.

**`get_available_slots(target_date, service_duration_minutes, buffer_after_minutes, buffer_after_event_minutes)`:**

1. **שעות עבודה:** `get_status_for_date(target_date)` — מקור `regular` / `holiday` / `special_day`.
2. **חופשה:** `VacationService.is_active()` — אם פעיל, אין סלוטים.
3. **busy מ-Google:** FreeBusy API:
   ```python
   service.freebusy().query(body={
       "timeMin": day_start.isoformat(),
       "timeMax": day_end.isoformat(),
       "timeZone": tz,
       "items": [{"id": calendar_id}]
   }).execute()
   ```
4. **busy מ-DB:** `get_appointments_busy_ranges(date_str)` — תורים pending/confirmed שטרם הופיעו בגוגל.
5. **לולאת סלוטים** (קפיצות של 30 דק׳ מ-`open_time` עד `close_time`):
   - `slot_end = slot_start + service_duration_minutes`
   - דחייה אם overlap עם busy (גם `buffer_after_event_minutes` לכל אירוע גוגל; `buffer_after_minutes` נוסף אחרי הסלוט עצמו).
   - דחייה אם chunk חוצה חצות או נמצא בעבר (היום: עיגול ל-30 דק׳ קדימה).
6. **במקרה כשל API:** `raise CalendarUnavailable` (הבחנה בין "אין סלוטים" ל-"לא ניתן לבדוק").

**timezones:** ISO מ-Google → `astimezone(ZoneInfo("Asia/Jerusalem"))`.

## 4) יצירת בקשת תור

1. `db.create_appointment(...)` — status `pending`.
2. `gather_and_decide()` → מחזיר `pending` / `confirmed` / `rejected` לפי `auto_booking_mode` ובדיקה מחודשת מול Google.
3. אם `confirmed`: `db.update_appointment_status(appt_id, "confirmed", ...)`.
4. **הגנת כפילויות:** Unique partial index:
   ```sql
   CREATE UNIQUE INDEX idx_appointments_user_datetime
   ON appointments(user_id, preferred_date, preferred_time)
   WHERE preferred_date != '' AND preferred_time != ''
   ```
   `IntegrityError` נתפס ב-handler.

## 5) אישור/דחייה ע"י בעל העסק

**Admin UI:** טבלה של תורים, סינון לפי status, דגל `owner_seen` ל"חדש". כפתורי Confirm / Cancel / Mark Passed, שדה הערה ובחירת משך.

**Handler האישור:**
```python
db.update_appointment_status(appt_id, status, confirmed_duration_minutes=...)
notify_appointment_status(appt, owner_message=...)
```

**`notify_appointment_status()`:**
- בונה הודעת HTML.
- שולח לפי `appt["channel"]` (Telegram עם `parse_mode="HTML"`, או WhatsApp עם הגנת 1600 תווים).
- אם `ics_enabled` — מצרף `.ics`.
- קורא ל-`sync_appointment_to_calendar(appt, status)`.

**Sync ליומן:**
- **confirmed:** `create_event()` — body כולל `summary`, `description` (עם `bookingId=appt_<id>` ⇐ **עוגן לסנכרון הפוך**), `start`/`end` עם `timeZone="Asia/Jerusalem"`, `location`. שמירה: `db.set_appointment_google_event_id(appt_id, event_id)`.
- **cancelled:** `delete_event(google_event_id)`. **HTTP 410 נחשב הצלחה.**

## 6) סנכרון דו-כיווני

**מצב נוכחי בקוד:**
- DB → Google: עובד מלא דרך `sync_appointment_to_calendar`.
- Google → DB: רק קריאה ל-FreeBusy בעת בדיקת זמינות. **אין watch channels / polling אינקרמנטלי כיום.**

**להוספה מלאה — תבנית מומלצת:**

**Watch channel** (תוקף ~1 שעה, יש לרענן):
```python
service.events().watch(calendarId="primary", body={
    "id": f"booking_sync_{uuid4()}",
    "type": "web_hook",
    "address": "https://your-domain.com/webhooks/google-calendar"
}).execute()
```

**Webhook + incremental sync עם `syncToken`:**
```python
@app.route("/webhooks/google-calendar", methods=["POST"])
def google_cal_webhook():
    if request.headers.get("X-Goog-Resource-State") == "exists":
        _sync_gcal_to_db()

def _sync_gcal_to_db():
    sync_token = db.get_gcal_sync_token()
    try:
        events = service.events().list(
            calendarId="primary", syncToken=sync_token, showDeleted=True
        ).execute()
    except HttpError as e:
        if e.resp.status == 410:  # sync_token פג
            events = service.events().list(calendarId="primary").execute()
        else: raise
    for ev in events.get("items", []):
        desc = ev.get("description", "")
        if "bookingId=" not in desc: continue
        appt_id = extract_appt_id(desc)
        if ev.get("status") == "cancelled":
            db.update_appointment_status(appt_id, "cancelled")
        else:
            db.update_appointment_datetime(appt_id, ev["start"]["dateTime"])
    db.save_gcal_sync_token(events.get("nextSyncToken"))
```

**עוגן הקישור הוא `bookingId=appt_<id>` בתוך `description` של האירוע** — נכתב כבר היום ב-`create_event()`.

## 7) Post-Meeting Update

- ג'וב יומי קורא ל-`db.expire_past_appointments()` — מסמן תורים שזמנם עבר כ-`passed`.
- מנגנון follow-up: אם enabled, נקרא `follow_up_service.send_post_meeting_followup(appt_id)` — שליחת הודעת תודה/feedback בערוץ הרלוונטי.
- מנגנון feedback אינו ממומש כטבלה ייעודית כיום; אופציה: טבלה `appointment_feedback(appt_id, rating, comment, created_at)`.

## 8) סכימת DB מלאה

**`google_calendar_credentials`** — singleton:
```sql
id INTEGER PRIMARY KEY CHECK(id = 1),
google_account_email TEXT,
calendar_id TEXT DEFAULT 'primary',
refresh_token TEXT,    -- מוצפן אם SECRETS_ENCRYPTION_KEY מוגדר
access_token  TEXT,    -- מוצפן
token_expiry  TEXT,    -- ISO 8601
timezone      TEXT DEFAULT 'Asia/Jerusalem',
auth_invalid_at     TEXT,  -- timestamp של RefreshError
owner_alert_sent_at TEXT,
updated_at TEXT DEFAULT (datetime('now'))
```

**`appointments`** (שם שונה אצלנו: `bookings`):
```sql
id INTEGER PRIMARY KEY AUTOINCREMENT,
user_id TEXT NOT NULL,
username TEXT,
telegram_username TEXT,
channel TEXT NOT NULL DEFAULT 'telegram',  -- telegram/whatsapp
service TEXT,
preferred_date TEXT,   -- YYYY-MM-DD
preferred_time TEXT,   -- HH:MM
notes TEXT,
status TEXT DEFAULT 'pending',  -- pending/confirmed/cancelled/passed
google_event_id TEXT,
confirmed_duration_minutes INTEGER,
reminder_sent INTEGER DEFAULT 0,
second_reminder_sent INTEGER DEFAULT 0,
owner_seen INTEGER NOT NULL DEFAULT 0,
created_at TEXT DEFAULT (datetime('now'))
-- + partial unique index על (user_id, date, time)
```

**`bot_settings`** — הגדרות auto-booking ותזכורות:
```
auto_booking_mode (manual/auto_with_check/auto_always)
auto_booking_max_days_ahead, auto_booking_buffer_after_event_minutes
default_appointment_duration_minutes, appointment_duration_step_minutes
appointment_duration_steps_backward, appointment_duration_steps_forward
reminder_enabled, reminder_time
second_reminder_enabled, second_reminder_hours
```

**`business_hours`** (יום-בשבוע 0–6), **`special_days`** (תאריך ספציפי), **`vacation_mode`** (חופשה גלובלית) — מוזרמים כולם ל-`get_status_for_date()` שמשמש את חישוב הסלוטים.

## 9) קונפיגורציה

```
# OAuth
GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REDIRECT_URI
SECRETS_ENCRYPTION_KEY  # חובה בפרוד — מצפין refresh/access tokens

# עסק
BUSINESS_NAME, BUSINESS_PHONE, BUSINESS_ADDRESS
ADMIN_URL  # משמש בקישורים בהתראות ובדפי WhatsApp ארוכים

# ערוצים
TELEGRAM_OWNER_CHAT_ID
TWILIO_ACCOUNT_SID/AUTH_TOKEN/WHATSAPP_NUMBER, OWNER_WHATSAPP_NUMBER
```

**Multi-tenant:** הקוד כיום singleton (`CHECK(id = 1)`). לרב-לקוחות יש להחליף את ה-singleton במפתח `tenant_id`.

## 10) שילוב עם handlers של Telegram/WhatsApp — *לא רלוונטי אצלנו*

> אצלנו אין Telegram/WhatsApp booking flow — הליד נכנס לדף ווב.

---

# קווי מפתח לזכור בעת השכפול

1. **PKCE + state ב-session** — חובה לאבטחת OAuth.
2. **`SECRETS_ENCRYPTION_KEY`** — להצפנת refresh_token ב-DB.
3. **בדיקה כפולה לפני יצירת התור** (race condition בין הצגת השעות לאישור).
4. **Partial unique index** על `(user_id, date, time)` למניעת תורים כפולים.
5. **DB busy ranges + Google busy ranges** — שניהם בחישוב הזמינות (pending עוד לא בגוגל).
6. **`bookingId=appt_<id>`** ב-event description — עוגן הסנכרון הדו-כיווני העתידי.
7. **`auth_invalid_at` + `owner_alert_sent_at`** — להתאוששות חיננית מ-RefreshError בלי ספאם.
8. **HTTP 410 ב-`delete_event`** — להתייחס כהצלחה (אירוע כבר נמחק).
9. **Refresh של watch channels** — ל-Google יש תוקף ~שעה; ג'וב שמרענן.

---

## מבנה תיקיות בפרויקט המקורי (לעיון)

```
google_calendar.py            # OAuth, FreeBusy, Events CRUD, refresh
core/booking_decision.py      # auto-booking logic
bot/
  handlers.py                 # ConversationHandler ב-Telegram
  calendar_keyboard.py        # קלנדר חודשי + month availability
messaging/
  whatsapp_booking.py         # WhatsApp state machine
  conversation_state.py
admin/
  app.py                      # /google/connect, /google/callback, /appointments
  templates/
    google_calendar.html
    appointments.html
appointment_notifications.py  # templates + trigger sync
database.py + migrations.py   # schema + tokens encryption
```
