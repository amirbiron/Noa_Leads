# Spec טכני - מערכת ניהול לידים ולקוחות לנועה

> **גרסה:** 1.0
> **תאריך:** מאי 2026
> **לקוחה:** נועה - בימאית, מאמנת קול ועמידה מול קהל
> **מתאם לקוחות:** אדיר גזית 

---

## 1. סקירה כללית

מערכת ווב מותאמת לנייד לניהול לידים, לקוחות, יומן, ותבניות תגובה. המערכת מבטיחה שלכל ליד יש סטטוס ברור ושום פנייה לא נופלת בין הכיסאות.

**עקרונות מנחים:**
- כל פעולה נפוצה - עד 2 לחיצות מהנייד
- ממשק ויזואלי, ללא טבלאות מורכבות
- AI תומך בלבד (סיכומים, זיהוי רדומים) - לא שולח הודעות
- שליחת וואטסאפ תמיד ידנית

---

## 2. סטאק טכני

| רכיב | בחירה | נימוק |
|---|---|---|
| Backend | FastAPI (Python 3.12) | מהיר, type-safe, מתאים ל-API REST |
| DB | PostgreSQL | יחסים מורכבים בין Lead/Activity/Task/Booking |
| Frontend | Next.js 15 + React 19 | App Router, RSC, תואם EmailFlow |
| UI | Tailwind + shadcn/ui | מהיר לבניה, RTL מצוין |
| Hosting | Render | Web Service + PostgreSQL מנוהל |
| File Storage | Cloudflare R2 | קבצי קול, צילומי מסך אם יידרש |
| התראות | Telegram Bot | פוש לליד חדש |
| Cron | Render Cron Jobs | פולואפים, סיכומים, ניקיון |
| AI | Anthropic Claude API | סיכומים, ניסוח, תמלול (Whisper) |

**Skills להתקנה מ-agentskills.co.il:**
- שיטות עבודה מומלצות ל-RTL
- מפרמט טלפונים ישראלי
- בינלאומיות עברית
- מתזמן מודע שבת
- נגישות אתרים ישראלית

---

## 3. ארכיטקטורה ברמה גבוהה

```
┌─────────────────────────────────────────────────────────────┐
│                    מקורות לידים                              │
│  טופס באתר | מייל (Gmail API) | הזנה ידנית | דף קביעת תור   │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│              FastAPI Backend                                 │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │ Lead Intake │  │ State Machine│  │ Followup Engine  │   │
│  └─────────────┘  └──────────────┘  └──────────────────┘   │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │ Templates   │  │ Bookings     │  │ AI Layer         │   │
│  └─────────────┘  └──────────────┘  └──────────────────┘   │
└──────┬──────────────────┬───────────────────┬──────────────┘
       │                  │                   │
       ▼                  ▼                   ▼
┌─────────────┐  ┌─────────────────┐  ┌─────────────────┐
│ PostgreSQL  │  │ Google Calendar │  │ Telegram Bot    │
└─────────────┘  └─────────────────┘  └─────────────────┘
       ▲
       │
┌──────┴──────────────────────────────────────────────────┐
│         Next.js Frontend (PWA, mobile-first)            │
│  דשבורד | כרטיס ליד | תבניות | יומן | תובנות           │
└─────────────────────────────────────────────────────────┘
```

---

# פאזה 1 - הליבה (MVP)

מערכת מרכזית עובדת ושלמה לניהול לידים. בסוף הפאזה הזו - נועה יכולה לעבור לעבודה מהמערכת.

## 4. סכמת מסד נתונים

### 4.1 טבלאות עיקריות

#### `leads`
```sql
CREATE TABLE leads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    full_name VARCHAR(200) NOT NULL,
    phone VARCHAR(20),
    email VARCHAR(200),
    organization_name VARCHAR(200),

    -- קטגוריזציה
    service_category VARCHAR(50) NOT NULL,  -- clinic / workshops / production / digital_course
    service_subtype VARCHAR(100),  -- voice_development / public_speaking / etc.

    -- מצב
    status VARCHAR(30) NOT NULL DEFAULT 'NEW',
    waiting_on VARCHAR(20) DEFAULT 'NOAH',  -- NOAH / CLIENT / ASSISTANT / SYSTEM / NONE
    priority_level VARCHAR(20) DEFAULT 'normal',  -- normal / hot / vip
    preferred_contact VARCHAR(20) DEFAULT 'whatsapp',  -- phone / whatsapp / email

    -- בעלות
    owner_id UUID REFERENCES users(id),

    -- צעד הבא
    next_action_type VARCHAR(50),
    next_action_due_at TIMESTAMPTZ,
    needs_attention BOOLEAN DEFAULT FALSE,

    -- מקור
    source_channel VARCHAR(50) NOT NULL,  -- form / email / manual / referral / facebook / etc.
    source_detail TEXT,
    utm_source VARCHAR(100),
    utm_campaign VARCHAR(100),
    utm_content VARCHAR(100),

    -- היסטוריה
    last_inbound_at TIMESTAMPTZ,
    last_outbound_at TIMESTAMPTZ,
    last_activity_type VARCHAR(50),
    reply_boost_until TIMESTAMPTZ,

    -- דגלים
    dormant_flag BOOLEAN DEFAULT FALSE,
    is_duplicate_suspected BOOLEAN DEFAULT FALSE,
    is_returning_customer BOOLEAN DEFAULT FALSE,

    -- סגירה
    closure_reason VARCHAR(50),  -- no_response / not_relevant / price / timing / etc.

    -- הערה אישית
    personal_note TEXT,

    -- timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_leads_status ON leads(status);
CREATE INDEX idx_leads_owner ON leads(owner_id);
CREATE INDEX idx_leads_needs_attention ON leads(needs_attention) WHERE needs_attention = TRUE;
CREATE INDEX idx_leads_next_action ON leads(next_action_due_at) WHERE status NOT IN ('WON', 'LOST', 'ARCHIVED');
```

#### `activities`
```sql
CREATE TABLE activities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id UUID NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    type VARCHAR(50) NOT NULL,
    performed_by UUID REFERENCES users(id),
    content TEXT,
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_activities_lead ON activities(lead_id, created_at DESC);
```

#### `tasks`
```sql
CREATE TABLE tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id UUID NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    type VARCHAR(50) NOT NULL,  -- first_response / followup / proposal_followup / etc.
    assigned_to UUID REFERENCES users(id),
    due_at TIMESTAMPTZ NOT NULL,
    status VARCHAR(20) DEFAULT 'open',  -- open / done / canceled / snoozed
    snoozed_until TIMESTAMPTZ,
    origin_rule VARCHAR(50),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

CREATE INDEX idx_tasks_open ON tasks(status, due_at) WHERE status = 'open';
```

#### `templates`
```sql
CREATE TABLE templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(200) NOT NULL,
    channel VARCHAR(20) NOT NULL,  -- whatsapp / email
    target_audience VARCHAR(50),  -- private / organization / dormant
    body TEXT NOT NULL,
    variables JSONB,  -- ["customer_name", "service_type"]
    is_active BOOLEAN DEFAULT TRUE,
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

#### `bookings`
```sql
CREATE TABLE bookings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id UUID NOT NULL REFERENCES leads(id),
    requested_slot_start TIMESTAMPTZ NOT NULL,
    requested_slot_end TIMESTAMPTZ NOT NULL,
    status VARCHAR(30) DEFAULT 'pending_approval',
    google_calendar_event_id VARCHAR(200),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    approved_at TIMESTAMPTZ,
    rejected_at TIMESTAMPTZ
);
```

#### `programs` (תוכניות מתמשכות)
```sql
CREATE TABLE programs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id UUID NOT NULL REFERENCES leads(id),
    program_type VARCHAR(50) NOT NULL,  -- voice_rehab_8 / stage_arts_4 / production_3months / etc.
    total_sessions INTEGER NOT NULL,
    completed_sessions INTEGER DEFAULT 0,
    total_price NUMERIC(10, 2),
    actual_hours NUMERIC(6, 2) DEFAULT 0,
    started_at TIMESTAMPTZ DEFAULT NOW(),
    estimated_end_at TIMESTAMPTZ,
    status VARCHAR(20) DEFAULT 'active'  -- active / completed / canceled
);
```

#### `users`
```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(200) UNIQUE NOT NULL,
    name VARCHAR(200) NOT NULL,
    role VARCHAR(20) NOT NULL,  -- owner (נועה) / assistant
    telegram_chat_id VARCHAR(50),
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### 4.2 Enums מרכזיים

```python
# constants.py

LEAD_STATUSES = ['NEW', 'IN_PROGRESS', 'PROPOSAL_SENT', 'BOOKING_PENDING',
                 'BOOKED', 'WON', 'LOST', 'ARCHIVED']

WAITING_ON = ['NOAH', 'CLIENT', 'ASSISTANT', 'SYSTEM', 'NONE']

SERVICE_CATEGORIES = {
    'clinic': ['voice_development', 'public_speaking', 'voice_rehab'],
    'workshops': ['workshop_speaking', 'stage_arts', 'lecture_organization', 'lecture_academic'],
    'production': ['production_guidance', 'production_directing'],
    'digital_course': ['digital_course']
}

CLOSURE_REASONS = ['no_response', 'not_relevant', 'price', 'timing',
                   'went_with_other', 'duplicate', 'other']

ACTIVITY_TYPES = [
    'lead_created', 'lead_updated', 'template_marked_sent', 'manual_message_logged',
    'call_completed', 'call_no_answer', 'meeting_requested', 'meeting_approved',
    'proposal_sent', 'followup_scheduled', 'owner_changed', 'internal_note_added',
    'status_changed', 'lead_won', 'lead_lost', 'lead_reopened',
    'inbound_message_logged', 'outbound_message_logged'
]
```

---

## 5. State Machine - מעברי סטטוסים

### 5.1 דיאגרמה

```
                    ┌──────┐
       ┌───────────►│ NEW  │◄────────┐
       │            └──┬───┘         │
       │               │ (פעולה ראשונה)│
       │               ▼              │
       │       ┌──────────────┐       │
       │       │ IN_PROGRESS  │───────┤
       │       └──┬────────┬──┘       │
       │          │        │          │
       │ (הצעה)   │        │ (בקשת מועד)
       │          ▼        ▼          │
       │  ┌─────────────┐  ┌───────────────┐
       │  │PROPOSAL_SENT│  │BOOKING_PENDING│
       │  └──────┬──────┘  └──────┬────────┘
       │         │                 │
       │         │ (סגירה/דחיה)    │ (אישור)
       │         ▼                 ▼
       │   ┌─────────┐         ┌────────┐
       └───┤ WON/LOST│◄────────┤ BOOKED │
           └─────────┘         └────────┘
                                   │
                                   ▼
                              ┌─────────┐
                              │ARCHIVED │ (אחרי זמן רב)
                              └─────────┘
```

### 5.2 חוקי מעבר

| מעבר | טריגר | תנאים |
|---|---|---|
| NEW → IN_PROGRESS | פעולה ראשונה (template_sent, call, etc.) | אוטומטי |
| IN_PROGRESS → PROPOSAL_SENT | proposal_sent | ידני |
| IN_PROGRESS → BOOKING_PENDING | meeting_requested | אוטומטי מדף תורים |
| BOOKING_PENDING → BOOKED | meeting_approved | אישור נועה |
| BOOKING_PENDING → IN_PROGRESS | meeting_rejected | ידני |
| כל סטטוס → WON | סימון "נסגרה עסקה" | ידני |
| כל סטטוס → LOST | סימון "סגור ללא עסקה" | ידני, חובה closure_reason |
| WON/LOST → IN_PROGRESS | lead_reopened | ידני |

### 5.3 חוקי ולידציה

- ליד פתוח (NEW/IN_PROGRESS/PROPOSAL_SENT/BOOKING_PENDING/BOOKED) **חייב** owner_id
- ליד סגור (WON/LOST/ARCHIVED): next_action_type = NULL
- LOST דורש closure_reason
- אין hard delete - רק ARCHIVED

---

## 6. API Endpoints (REST)

### 6.1 Authentication
```
POST   /auth/login              - login עם email/password
POST   /auth/refresh            - refresh token
POST   /auth/logout
```

### 6.2 Leads
```
GET    /leads                   - רשימה עם filters (?status, ?owner, ?waiting_on, ?source)
GET    /leads/{id}              - כרטיס ליד מלא + activities + tasks + program
POST   /leads                   - יצירה ידנית
PATCH  /leads/{id}              - עדכון
POST   /leads/{id}/actions/{action_type}  - פעולה דינמית (mark_template_sent, log_call, etc.)
POST   /leads/{id}/transfer     - העברה ל-Y עם handoff_note
POST   /leads/{id}/close        - סגירה כ-WON/LOST/ARCHIVED
POST   /leads/{id}/reopen       - פתיחה מחדש
GET    /leads/{id}/timeline     - היסטוריית activities
```

### 6.3 Intake (קליטת לידים)
```
POST   /intake/form             - מטופס באתר (public, rate-limited)
POST   /intake/email            - webhook מ-Gmail
POST   /intake/manual           - הזנה ידנית מהנייד
```

### 6.4 Dashboard
```
GET    /dashboard/home          - מסך הבית (פעולות היום + סקציות)
GET    /dashboard/today         - פעולות היום בלבד
GET    /dashboard/pending       - ממתין לטיפול
GET    /dashboard/proposals     - הצעות פתוחות
GET    /dashboard/weekly        - תובנות השבוע
```

### 6.5 Templates
```
GET    /templates
POST   /templates
PATCH  /templates/{id}
DELETE /templates/{id}
POST   /templates/{id}/render?lead_id={lead_id}  - תבנית עם משתנים ממולאים
```

### 6.6 Calendar & Bookings
```
GET    /calendar/availability?date_from&date_to    - שעות פנויות
POST   /bookings                                    - יצירת בקשת תור (public)
GET    /bookings/pending                            - בקשות ממתינות לאישור
POST   /bookings/{id}/approve                       - אישור + יצירת אירוע ב-Google Calendar
POST   /bookings/{id}/reject                        - דחיה
GET    /calendar/categories                         - רשימת קטגוריות צבע
```

### 6.7 Tasks (פולואפ ותזכורות)
```
GET    /tasks/open
POST   /tasks/{id}/snooze       - דחיה (היום אחה"צ / מחר / וכו')
POST   /tasks/{id}/complete
```

### 6.8 Programs (תוכניות מתמשכות)
```
POST   /programs                - יצירת תוכנית ללקוח
PATCH  /programs/{id}           - עדכון (כמה מפגשים בוצעו, שעות בפועל)
GET    /programs/active         - תוכניות פעילות
```

### 6.9 Settings
```
GET    /settings/chips          - צ'יפים לסיכום שיחה
PATCH  /settings/chips
GET    /settings/followup-rules - כללי פולואפ
PATCH  /settings/followup-rules
GET    /settings/service-rates  - תעריפי שירות
PATCH  /settings/service-rates
```

---

## 7. Cron Jobs

| Job | תדירות | פעולה |
|---|---|---|
| `mark_overdue_leads` | כל 15 דקות | סימון `needs_attention` ללידים שעברו `next_action_due_at` |
| `check_stuck_proposals` | כל שעה | זיהוי הצעות שלא קיבלו פולואפ |
| `detect_dormant_leads` | פעם ביום (03:00) | סימון `dormant_flag` ללקוחות שלא חזרו 60+ ימים |
| `release_stale_locks` | כל 10 דקות | שחרור משימות בסטטוס PROCESSING מעל timeout |
| `daily_summary` | כל יום ב-19:00 | שליחת סיכום יומי לטלגרם של נועה |
| `weekly_summary` | ראשון ב-08:00 | יצירת סיכום שבועי לדשבורד |
| `post_meeting_check` | כל 30 דקות | בדיקת פגישות שהסתיימו, יצירת משימת `post_meeting_update` |

---

## 8. אינטגרציות חיצוניות

### 8.1 Google Calendar
- **OAuth 2.0** - חיבור חד-פעמי, refresh token שמור ב-DB
- **קריאת זמינות:** `freebusy.query` לקבלת slots פנויים
- **יצירת אירוע:** `events.insert` עם `colorId` מתאים לקטגוריה
- **מחיקת/עדכון אירוע:** `events.delete`, `events.patch`

**מיפוי קטגוריות לצבעי Google Calendar:**
```python
GOOGLE_CALENDAR_COLORS = {
    'clients': '3',      # סגול - לקוחות
    'workshops': '4',    # ורוד - סדנאות
    'preparation': '6',  # כתום/חום - הכנה
    'management': '11',  # אדום עמוק - ניהול
    'personal': '5',     # צהוב - אישי
    'blocked': '8',      # אפור - חסום
}
```

### 8.2 Gmail
- **OAuth 2.0** עבור גישה לתיבה של נועה
- **Push Notifications** דרך Pub/Sub לקבלת מיילים בזמן אמת
- **סינון AI:** כל מייל נכנס עובר דרך Claude API לסיווג עסקי/לא עסקי
- **תווית "סוננו"** - מיילים שסוננו מקבלים תווית ייעודית

### 8.3 Telegram Bot
- שימוש בקוד הקיים מ-Telegram MCP Server שלך
- שליחת הודעות פוש לליד חדש
- סיכום יומי

### 8.4 Anthropic Claude API
- **מודלים:** claude-sonnet-4-6 לסיכומים, claude-haiku-4-5 לסיווג מהיר
- **תרחישים:** סינון פניות לא עסקיות, סיכומים יומיים/שבועיים, זיהוי לידים רדומים, ניסוח הצעות

### 8.5 OpenAI Whisper API (לתיעוד קולי - אופציונלי)
- **מודל:** gpt-4o-transcribe (הכי מדויק לעברית)
- POC נדרש לפני התחייבות

---

## 9. Frontend - מסכים עיקריים

### 9.1 מבנה ניווט
```
/                       → דשבורד הבית
/leads                  → רשימת כל הלידים (עם פילטרים)
/leads/[id]            → כרטיס ליד
/today                  → פעולות היום
/pending                → ממתין לטיפול
/proposals              → הצעות פתוחות
/calendar               → יומן
/templates              → ניהול תבניות
/insights               → תובנות שבועיות
/settings               → הגדרות
```

### 9.2 רכיבי UI עיקריים

- **FloatingNewLeadButton** - כפתור צף בכל מסך
- **LeadCard** - כרטיס ליד מקוצר ברשימה
- **LeadDetail** - כרטיס ליד מלא עם timeline
- **DynamicActionButton** - כפתור "מה עכשיו?" שמשתנה לפי סטטוס
- **QuickChips** - צ'יפים לסיכום שיחה
- **SmartSnooze** - בחירת מועד פולואפ מהיר
- **VoiceRecorder** - הקלטה ותמלול (אופציונלי בפאזה 1)
- **TemplateSheet** - bottom sheet לבחירת תבנית

### 9.3 RTL ונגישות
- כל הממשק RTL מההתחלה
- שימוש בסקילים: hebrew-i18n, rtl-best-practices, accessibility-il
- `<html lang="he" dir="rtl">`
- Logical CSS properties בלבד (`padding-inline-start` במקום `padding-left`)

---

## 10. בטיחות ופרטיות

- **Authentication:** JWT עם refresh tokens
- **Authorization:** RBAC - owner (נועה) רואה הכל, assistant רואה רק לידים שהוקצו לה
- **Rate Limiting:** על endpoints ציבוריים (intake/form, bookings)
- **Encryption at rest:** PostgreSQL עם encryption
- **Encryption in transit:** HTTPS only
- **Secrets:** Render Environment Variables, אף פעם לא בקוד
- **Audit Log:** כל שינוי קריטי נכנס לטבלת activities

---

## 11. Deployment

```yaml
# render.yaml
services:
  - type: web
    name: noah-crm-backend
    env: python
    buildCommand: pip install -r requirements.txt
    startCommand: uvicorn main:app --host 0.0.0.0 --port $PORT

  - type: web
    name: noah-crm-frontend
    env: node
    buildCommand: npm install && npm run build
    startCommand: npm start

  - type: pserv
    name: noah-crm-db
    env: postgresql
    plan: starter

  - type: cron
    name: mark-overdue-leads
    schedule: "*/15 * * * *"
    command: python jobs/mark_overdue.py

  # ... שאר ה-cron jobs
```

---

# פאזה 2 - יומן ותורים

> סטטוס: כותרות בלבד. פירוט מלא ייעשה כשמתחילים את הפאזה.

## פיצ'רים עיקריים

1. **סנכרון Google Calendar מלא**
   - קריאה דו-כיוונית של אירועים
   - תמיכה בקטגוריות צבע מלאות
   - אירועים חוזרים (recurring)

2. **דף קביעת תור ללידים**
   - URL ציבורי `noah.app/book/{lead_token}`
   - הצגת slots פנויים בזמן אמת
   - בחירת מועד → סטטוס "ממתין לאישור"
   - אישור נועה → יצירת אירוע ב-Google Calendar
   - שליחת אישור ללקוח (מייל/וואטסאפ ידני)

3. **מנגנון "post meeting update"**
   - 30 דקות אחרי סיום פגישה - הקפצת מסך מהיר
   - בחירה: ממשיכים / לשלוח הצעה / לקבוע סדנה / לא רלוונטי
   - עדכון אוטומטי של סטטוס + תוכנית (אם רלוונטי)

4. **ניהול תוכניות מתמשכות מהיומן**
   - בכל פגישה ב-clinic - סימון "מפגש N מתוך X"
   - התראה אוטומטית כשתוכנית מתקרבת לסיום

## הערות ארכיטקטוניות

- שמירת `google_calendar_event_id` בכל booking לסנכרון דו-כיווני
- שימוש ב-Google Calendar webhooks (push notifications) כדי לתפוס שינויים שנעשו ישירות ביומן
- caching של זמינות (TTL קצר, 5 דקות) לדף קביעת תורים

---

# פאזה 3 - AI ותובנות מתקדמות

> סטטוס: כותרות בלבד. פירוט מלא ייעשה כשמתחילים את הפאזה.

## פיצ'רים עיקריים

1. **סיכום יומי אוטומטי**
   - Cron ב-19:00 כל יום
   - Claude API מסכם את הפעילות של היום
   - שליחה לטלגרם של נועה
   - תוכן: כמה לידים נכנסו, כמה טופלו, מה ממתין למחר, 3 דברים חשובים

2. **סיכום שבועי**
   - Cron ראשון ב-08:00
   - תובנות: מקורות לידים, שירות רווחי, לידים שנתקעו
   - **בלוק "השעה הרווחית שלך השבוע"** - ניתוח רווחיות פר סוג שירות

3. **זיהוי לידים רדומים**
   - Cron יומי שמזהה לידים עם dormant_flag
   - Claude API מציע פעולה לכל ליד (חידוש קשר עדין / ארכוב / וכו')

4. **ניסוח הצעות לארגונים**
   - יוזמת נועה בלחיצת כפתור
   - קלט: שם ארגון, סוג שירות, צורך, הערות
   - פלט: טיוטת הצעה מקצועית
   - נועה עורכת ושולחת ידנית

5. **תיעוד קולי עם תמלול** (אם POC מצליח)
   - הקלטה מכרטיס הליד
   - שליחה ל-OpenAI Whisper (gpt-4o-transcribe)
   - שמירה כהערה פנימית
   - חילוץ נקודות חשובות והצעת צעד הבא

6. **דשבורד תובנות מתקדם**
   - מקורות לידים → המרה
   - תעריף שעתי אפקטיבי פר סוג שירות
   - מגמות לאורך זמן
   - בסיס להחלטות פרסום ממומן

## הערות ארכיטקטוניות

- שימוש ב-batch processing למשימות AI לחיסכון בעלות
- Caching של תובנות שבועיות (לא לחשב מחדש בכל טעינה)
- מעקב עלויות AI - dashboard פנימי לעלויות חודשיות

---

# נספחים

## נספח א' - שאלות פתוחות לבירור עם נועה

1. **מחיר קורס דיגיטלי** - עדיין בפיתוח
2. **מחיר בימוי הפקה** - נועה ציינה תגמול נמוך יחסית למאמץ
3. **אומניות הבמה - מפגש = שעה או שעתיים?**
4. **האם יש מערכת קיימת לייבוא נתונים ממנה?** (לקוחות קיימים, היסטוריה)
5. **שעות זמינות לקליניקה - האם קבועות בכל שבוע?**

## נספח ב' - מקורות ידע

- מסמך אפיון מוצרי: [link to spec.html]
- מסמך MD פנימי עם תוספות: [link to internal-spec.md]
- סקילים מ-agentskills.co.il
- EmailFlow repo (לחילוץ חלקים רלוונטיים)

## נספח ג' - רשימת חבילות עיקריות

**Backend (Python):**
```
fastapi>=0.115
sqlalchemy>=2.0
asyncpg
pydantic>=2.0
python-multipart
anthropic
openai
google-api-python-client
google-auth
python-telegram-bot
celery / arq  # לcron jobs
alembic  # migrations
pytz
```

**Frontend (Next.js):**
```
next@15
react@19
tailwindcss
@radix-ui/* (shadcn/ui base)
lucide-react
date-fns
zustand  # state management
react-hook-form
zod
axios / fetch
```
