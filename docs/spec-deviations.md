# Spec Deviations & Gaps

> **גרסה:** 1.1 (מאי 2026)
> **מטרה:** רישום מסודר של *כל* הפערים הידועים בין `docs/SpecV2.1.md` (גרסה 2.1) לבין הקוד הקיים, עם acceptance checklists ברורים לכל פער.
> **למה זה קיים:** בסבבי bugbot הקודמים גילינו שמשפחת ה-chips, ה-Telegram, ה-cron jobs ועוד סטו מהאפיון בלי שנדע. ה-CLAUDE.md המחודש מבהיר: **המסמך מנצח את הקוד**. המסמך הזה הוא ה-source of truth לתיקונים שצריך לבצע לפני שנועה רואה את המערכת.
> **עדכון v1.1:** SpecV2.1 פותר 7 מתוך 9 ה-Open Decisions שהיו ב-v1.0. ראה §4.

---

## 0. רקע ומתודולוגיה

**מקור הנתונים:** סריקה שיטתית של 28 הסעיפים ב-`docs/SpecV2.1.md` מול הקוד תחת `backend/app/`, `backend/jobs/`, `frontend/`, ו-`render.yaml`. סבב כפול — סוכן Explore + אימות ידני של line numbers ולוגיקה.

**עקרונות סיווג:**
- 🔴 **קריטי** — שובר תפקודיות / מציג נתון שגוי / לא תואם דרישה מפורשת מהאפיון.
- 🟠 **בינוני** — סטייה מהאפיון שלא שוברת כרגע אבל תתבטא כשנועה תיגע בפיצ'ר.
- 🟡 **מינורי** — שינוי קוסמטי / nice-to-have.
- 🟢 **accepted-deviation** — דחיה ידועה ומתועדת ב-`docs/phase-3-plan.md` או `docs/phase-2.5-plan.md`.

**שימוש במסמך:** לפני מימוש של finding — `grep -A 30 "^### F-NN" docs/spec-deviations.md` ולעבור על ה-acceptance. אחרי מימוש — סמן `[x]` במקום `[ ]`.

---

## 1. Status Legend

| סטטוס | משמעות |
|---|---|
| 🔴 | קריטי — לתקן לפני שנועה נכנסת |
| 🟠 | בינוני — לתקן ב-Wave B (לפני פאזה 3) |
| 🟡 | מינורי — לדחות ל-Wave C / לפי כאב |
| 🟢 | accepted — מתועד כדחיה, לא לטפל עכשיו |

---

## 2. Findings

### F-01: `quick_action_chips` schema לא תואמת לאפיון — 🔴

**Spec §5.7:** טבלת `quick_action_chips` עם השדות `label, target_status, auto_followup_days, sort_order, is_active`.

**Spec §16.3:** כל צ'יפ דורש גם `waiting_on` (NOAH/CLIENT) וסוג פולואפ (`retry_call`, `followup`, `send_proposal`, `dormant_check`).

**Code:** `backend/app/models/quick_action_chip.py` ו-`migration 0010` — השדות הם `label, action_type, requires_content, sort_order, is_active`. הגישה: `action_type` מצביע ל-`state_machine.ACTIONS` שמכיל את ה-transition. **אין** את `target_status`/`auto_followup_days`/`waiting_on` כשדות נפרדים ב-DB.

**Severity:** קריטי (Schema לא תואמת לאפיון; CLAUDE.md אומר "המסמך מנצח").

**Open decision:** השדות הנדרשים — האם הסכמה תהיה לפי §5.7 בלבד (`target_status + auto_followup_days`), או יורחב כדי לכסות גם את §16.3 (`waiting_on + followup_type`)? §16.3 לכאורה מצריך שדות נוספים שאינם ב-§5.7 — שאלה למשתמש: לאחד את שני הסעיפים?

**Acceptance:**
- [ ] `migration 0011` מוסיף שדות חסרים (לפחות `target_status`, `auto_followup_days`; אם הוחלט להרחיב — גם `waiting_on`, `followup_type`).
- [ ] `QuickActionChip` model תואם לסכמה החדשה.
- [ ] לוגיקת הקליק על צ'יפ ב-backend משתמשת בשדות אלה (לא ב-`action_type` כיום).
- [ ] `grep "action_type" backend/app/models/quick_action_chip.py` לא מחזיר כלום (השדה הוסר).

**Fix sketch:** Migration חדשה שמוסיפה עמודות + מעדכנת את 6 הצ'יפים הקיימים לערכים מ-§16.3 + ALTER לעמודות הישנות (drop `action_type`, `requires_content`).

---

### F-02: טבלת `email_messages` חסרה — 🟢

**Spec §5 + §20.10:** טבלה לשמירת ה-HTML הגולמי, הטקסט המנוקה, ו-cleaning_metadata לכל מייל שנכנס.

**Code:** לא קיים — אין טבלה ולא endpoint.

**Severity:** accepted-deviation — מתועד ב-`docs/phase-3-plan.md` כחלק מפאזה 3 (Gmail intake + AI classification).

**Acceptance:** אין לטפל עכשיו. כשנמצמש פאזה 3 — יווצר migration ייעודי.

---

### F-03: טבלת `service_rates` חסרה — 🟠

**Spec §5 (לא מפורט במפורש) + §22.9:** API endpoints `GET/PATCH /settings/service-rates` קיימים בקטלוג. §15.2 מציג טבלת תעריפי ברירת מחדל.

**Code:** `backend/app/services/service_rates.py` מחזיר תעריפים hardcoded. אין טבלת DB editable.

**Severity:** בינוני — Spec מציין API לעריכת תעריפים, אבל אין DB editable.

**Open decision:** האם תעריפים editable דרך UI (טבלת DB + endpoints), או hardcoded ב-`constants.py` עם override דרך config? Spec §15.1 אומר "ברירת מחדל אוטומטית לפי הקטגוריה - **ניתן לשינוי**" — מצביע על editable per-deal, אבל לא בהכרח per-rate-default.

**Acceptance (אם הוחלט DB editable):**
- [ ] Migration `service_rates` עם seeds מטבלת §15.2.
- [ ] GET/PATCH endpoints + frontend UI ב-/settings.
- [ ] `service_rates.py` קורא מ-DB עם fallback ל-defaults.

**Acceptance (אם הוחלט hardcoded):**
- [ ] תעריפים ב-`constants.py` כ-`DEFAULT_TARIFFS: dict[str, Decimal]`.
- [ ] §22.9 API endpoints מוסרים מ-Spec או מסומנים "פאזה 4".

---

### F-04: `service_category` חובה ב-LeadCreate, האפיון אומר אופציונלי — 🔴

**Spec §7.1:** "שדות חובה ביצירת ליד חדש: שם מלא, טלפון, מקור פנייה. זה הכל. שאר הפרטים אופציונליים."

**Code:** `backend/app/schemas/lead.py:55` — `service_category: ServiceCategory` (ללא `| None`). **חובה** ב-LeadCreate.

**Severity:** קריטי — סותר את האפיון. ליד שמגיע מטופס בלי קטגוריה ייכשל בvalidation.

**Acceptance:**
- [ ] `LeadCreate.service_category: ServiceCategory | None = None` ב-`backend/app/schemas/lead.py`.
- [ ] `create_lead` ב-service מטפל ב-None (לא קורס; שומר NULL בעמודה).
- [ ] Migration: אם `leads.service_category` הוא NOT NULL ב-DB — להפוך ל-nullable.
- [ ] Frontend `NewLeadModal` לא דורש קטגוריה (חזרה ל-§7.1 — רק שם/טלפון/מקור חובה).
- [ ] `grep "service_category: ServiceCategory$" backend/app/schemas/lead.py` לא מחזיר תוצאות.

**Fix sketch:** הופך את השדה ל-optional בכל מקום (schema, model, frontend). אם קטגוריה לא ידועה ביצירה — נועה תוכל לסווג אחר כך מהכרטיס.

---

### F-05: 6 הצ'יפים ב-migration 0010 לא תואמים לאפיון — 🔴

**Spec §16.3:** 6 צ'יפים מדויקים — אין מענה, רוצה פרטים, מעוניין בשיחה, רוצה הצעה, לא רלוונטי כרגע, לחזור בעוד חודש. כל אחד עם target_status + waiting_on + followup type + days.

**Code:** `migration 0010` יוצר 6 צ'יפים אחרים: אין מענה, סיכמתי שיחה, שלחתי תבנית, שלחתי הצעה, הוסיפי הערה, הודעה נכנסת. ה-`action_type` של כל אחד מצביע ל-action ב-state_machine.

**Severity:** קריטי — 5 מתוך 6 הצ'יפים שונים מהאפיון.

**Open decision:** **תלוי ב-F-01** (החלטת schema). אחרי קביעת השדות — להחליט אילו 6 צ'יפים בדיוק.

**Acceptance:**
- [ ] Migration חדשה (`0011` או מאוחר יותר) מוחקת את 6 הצ'יפים הקיימים ומוסיפה את 6 מ-§16.3.
- [ ] שמות מדויקים: "אין מענה", "רוצה פרטים", "מעוניין בשיחה", "רוצה הצעה", "לא רלוונטי כרגע", "לחזור בעוד חודש".
- [ ] לכל צ'יפ — `target_status` ו-`auto_followup_days` (וכל שדה אחר שהוחלט ב-F-01).
- [ ] Frontend `QuickActions` משקף את ה-labels החדשים.
- [ ] `grep -c "INSERT INTO quick_action_chips" backend/alembic/versions/*.py` מראה רק migration אחת פעילה (לא 2 סותרות).

**Fix sketch:** Drop the old 6 + insert the new 6 בmigration אחת אטומית. UUIDs דטרמיניסטיים חדשים ל-6 החדשים כדי שדאונגרייד יהיה safety net.

---

### F-06: Telegram נשלח גם ב-booking request — 🔴

**Spec §16.2:** "הדבר היחיד שמקבל פוש מיידי הוא ליד חדש שנכנס. ההתראה הולכת לטלגרם."

**Code:** `backend/app/services/booking.py:625` קורא ל-`notify_booking_requested()` — שולח Telegram כשליד מבקש תור.

**Severity:** קריטי — נועה תקבל ספאם בטלגרם על כל בקשת תור, מערער את ה-"ערוץ ייחודי לליד חדש".

**Acceptance:**
- [x] `notify_booking_requested` הוסר מ-`telegram.py` (גם הפונקציה עצמה — נשמרה הערה בלבד).
- [x] `booking.py:625` (השורה שקוראת ל-notify) הוסרה.
- [x] במקום — הליד עובר ל-BOOKING_PENDING + next_action מתעדכן, יופיע ב-/today/`/pending` כשנועה נכנסת.
- [x] `grep -rn "notify_booking_requested" backend/app/` מחזיר 0 שורות פונקציונליות.

**Fix sketch:** הסר את הקריאה ב-booking.py. הוסף activity log + עדכון `next_action_due_at` כך שהליד יקפוץ ב-/today של נועה בכניסה הבאה. אין צורך ב-push.

---

### F-07: סתירה פנימית באפיון — Telegram ב-daily_summary — 🔴 (Open Decision)

**Spec §16.2:** "הדבר היחיד שמקבל פוש מיידי הוא ליד חדש שנכנס" — מוציא Telegram מכל שאר ה-flows.

**Spec §23:** Cron `daily_summary` — "שליחת סיכום יומי **לטלגרם** של נועה".

**Code:** `backend/jobs/daily_summary.py` שולח Telegram ב-19:00 כל יום.

**Severity:** קריטי — סתירה בתוך ה-Spec עצמו. צריך הכרעה.

**Open decision:** **השאלה למשתמש:** איזה משני הסעיפים לעקוב?
- (א) §16.2 = יחיד. סיכום יומי עובר ל-bubble בדשבורד / מייל.
- (ב) §23 = יחיד. §16.2 נשאר "פוש מיידי" (לא תקופתי) — סיכום יומי הוא פוש תקופתי, לא נכלל ב-"מיידי".
- (ג) §16.2 + sender notification: סיכום יומי דרך Telegram אבל עם header "[סיכום]" כדי להפריד ויזואלית.

**Acceptance (תלוי בהחלטה):**
- [ ] Spec.md מתעדכן: שני הסעיפים מתיישבים זה עם זה.
- [ ] `daily_summary` ו-`weekly_summary` נוקטים בגישה שהוחלטה.

---

### F-08: 3 כללי פולואפ חסרים — 🟠

**Spec §17.1:** 5 כללי פולואפ:
1. `first_response` (ליד חדש) — 24h ✓ קיים
2. `warm_followup` (לקוח שהתעניין) — 48-72h ✗ חסר
3. `proposal_followup` (הצעה לארגון) — 3-5 ימי עסקים ✓ קיים
4. `dormant_check` (לקוח שלא חזר) — 60-90 יום ✗ חסר
5. `lecture_inquiry` (ארגון בהרצאה) — 24h ✗ חסר

**Code:** `backend/app/constants.py` — יש רק `FOLLOWUP_GRACE_FIRST_RESPONSE` ו-`FOLLOWUP_GRACE_PROPOSAL_ORG`.

**Severity:** בינוני — לא שובר כרגע (אין יוצרי tasks לסוגים החסרים), אבל פיצ'ר חסר.

**Open decision:** מתי בדיוק נוצרים `warm_followup`/`dormant_check`/`lecture_inquiry` tasks? §17 מציין כללים אבל לא טריגרים. §16.3 chips מצביעים על חלקם (`dormant_check` עבור "לא רלוונטי כרגע").

**Acceptance:**
- [ ] 3 קבועים חדשים ב-`constants.py`: `FOLLOWUP_GRACE_WARM`, `FOLLOWUP_GRACE_DORMANT`, `FOLLOWUP_GRACE_LECTURE_INQUIRY`.
- [ ] לוגיקת יצירת tasks (`lead_actions.py`, `_create_followup_task_if_needed`) מקבלת פרמטר `followup_type` ובוחרת grace.
- [ ] Chips מ-F-05 משתמשים בכללים הנכונים בהתאם לבחירת המשתמש.

---

### F-09: מצב בעלות 3 — "עוזרת ממתין לאישור נועה" חסר — 🟠

**Spec §13.5:** "שלושה מצבי בעלות: באחריות נועה, באחריות עוזרת, **באחריות עוזרת ממתין לאישור נועה**."

**Code:** `backend/app/constants.py:WaitingOn` — מכיל `NOAH`, `CLIENT`, `ASSISTANT`, `SYSTEM`, `NONE`. **אין** ערך ל-"עוזרת ממתין לאישור נועה" (מצב 3).

**Severity:** בינוני — אין מצב טכני לייצוג זה. נועה לא תוכל לסמן/לראות לידים ב-state זה.

**Open decision:** **גישה למימוש**:
- (א) ערך enum נוסף `ASSISTANT_PENDING_APPROVAL` ב-`WaitingOn` (מבלבל קצת — זה גם owner וגם waiting state).
- (ב) שדה נפרד `awaiting_owner_approval: bool` ב-Lead (סמנטיקה נקייה: owner=ASSISTANT + flag).
- (ג) field `ownership_state` ייעודי עם 3 ערכים (NOAH/ASSISTANT/ASSISTANT_PENDING).

**Acceptance:**
- [ ] Migration מוסיף את המנגנון שנבחר.
- [ ] `transfer_lead` תומך בשליחה למצב "ממתין לאישור" + endpoint לאישור.
- [ ] תצוגה ב-`/leads` ו-card עם סימון ויזואלי ייחודי למצב.

---

### F-10: `/tasks/stuck` קריטריון לא תואם לאפיון — 🟠 (Open Decision)

**Spec §22.7:** `GET /tasks/stuck` — "תקועים מ-7+ ימים".

**Code:** `backend/app/services/tasks.py:list_stuck_tasks` — קריטריון: `Task.due_at <= now_utc` (כל overdue, ללא סף 7 ימים). הוחלף ב-bugbot iteration קודם כדי להתאים ל-stuck_count בדשבורד.

**Severity:** בינוני — שונה מהאפיון, אבל עקבי עם תובנות הדשבורד.

**Open decision:** **השאלה למשתמש:** איזה משני הקריטריונים נכון?
- (א) Spec §22.7 = 7 ימים. /tasks/stuck יציג פחות items. תובנת "לא טופלו בזמן" צריכה להתאים — שינוי כפול.
- (ב) `due_at <= now` (קיים). יש לתקן את §22.7 ב-Spec.

**Acceptance (תלוי):**
- [ ] קריטריון אחיד בין `list_stuck_tasks` לבין `weekly_insights.stuck_count`.
- [ ] Spec.md מתעדכן אם נבחרה אופציה ב.

---

### F-11: `ARCHIVED → IN_PROGRESS` reopen לא מוגדר — 🟡

**Spec §6.3:** "WON/LOST → IN_PROGRESS (`lead_reopened`, ידני)". **ARCHIVED לא מצוין** כסטטוס שניתן לפתוח מחדש.

**Code:** `backend/app/services/leads.py:reopen_lead` — בדיקה אם תומך ב-ARCHIVED.

**Severity:** מינורי — קצה.

**Open decision:** האם ARCHIVED לעולם סופי, או שניתן לפתוח מחדש?

**Acceptance:**
- [ ] התנהגות `reopen_lead` תואמת להחלטה.
- [ ] Spec §6.3 מעודכן עם ההחלטה.

---

### F-12: `DEFAULT_TARIFFS` לא ב-`constants.py` — 🟠

**Spec §15.2:** טבלת תעריפי ברירת מחדל — קליניקה, סדנה, אומניות, ליווי הפקה וכו'.

**Code:** Service rates נמצא ב-`backend/app/services/service_rates.py` (לא ב-constants). אין pre-populate ביצירת Program — נועה ממלאת ידנית.

**Severity:** בינוני — תלוי ב-F-03 (DB editable או hardcoded).

**Open decision:** **F-03 קודם** — אז זה ייפתר ביחד.

**Acceptance:**
- [ ] תעריפים נגישים מ-`constants.py` או DB (לפי F-03).
- [ ] יצירת Program מקבלת `total_price` אוטומטית כברירת מחדל (ניתן לעקוף).

---

### F-13: 3 cron jobs חסרים ב-render.yaml — 🔴

**Code:** `backend/jobs/` מכיל 8 קבצי job:
- `mark_overdue.py` ✓ מתוזמן
- `check_stuck_proposals.py` ✓ מתוזמן
- `detect_dormant.py` ✓ מתוזמן
- `daily_summary.py` ✓ מתוזמן
- `weekly_summary.py` ✓ מתוזמן
- `post_meeting_tasks.py` ✗ **לא ב-render.yaml**
- `expire_stale_bookings.py` ✗ **לא ב-render.yaml**
- `renew_calendar_watch.py` ✗ **לא ב-render.yaml**

**Spec §23:** מציין post_meeting_check ו-retry_pending_classification, אך לא expire_stale_bookings ולא renew_calendar_watch (אלה מהמימוש של פאזה 2).

**Severity:** קריטי — אחרי deploy, jobs אלה לא ירוצו. נועה תקבל "תקועים" שלעולם לא ייסגרו, watch ביומן יפוג ולא יתחדש, post-meeting tasks לא ייווצרו.

**Acceptance:**
- [x] `render.yaml` מכיל 3 services נוספים — `noa-post-meeting-tasks`, `noa-expire-stale-bookings`, `noa-renew-calendar-watch`.
- [x] schedules:
  - `post_meeting_tasks`: `*/30 * * * *` (כל 30 דק', לפי F-15 + §11.4)
  - `expire_stale_bookings`: `30 0 * * *` (00:30 UTC = 03:30 Israel)
  - `renew_calendar_watch`: `0 1 * * *` (01:00 UTC = 04:00 Israel)
- [x] `grep -c "startCommand: python -m jobs" render.yaml` מחזיר 8 (לא 5).

**Fix sketch:** הוסף 3 services ל-render.yaml בעקבות הדוגמא של noa-detect-dormant.

---

### F-14: `release_stale_locks` לא קיים — 🟡 (Open Decision)

**Spec §23:** Cron `release_stale_locks` — "כל 10 דקות. שחרור משימות בסטטוס PROCESSING מעל timeout".

**Code:** אין קובץ `release_stale_locks.py` ב-`backend/jobs/`. אין `PROCESSING` כ-`TaskStatus` (יש OPEN/DONE/CANCELED/SNOOZED).

**Severity:** מינורי — לא משפיע על פיצ'רים קיימים.

**Open decision:** **השאלה למשתמש:** מה ה-job הזה אמור לעשות?
- (א) פאזה 3 — לרעיון לכשנממש classification: tasks במצב "מעובד" שצריך לשחרר אם נתקעו.
- (ב) מנגנון distributed locking לcrons (לא רלוונטי כי Render Cron Jobs רץ פעם בלבד).
- (ג) Spec מטעה — להסיר מהקטלוג.

**Acceptance (תלוי):**
- [ ] תוצאת ההחלטה: או קובץ job חדש + status חדש, או הסרת השורה מ-§23.

---

### F-15: `post_meeting_tasks` schedule — 🔴 (Open Decision)

**Spec §11.4 + §23:** "30 דקות אחרי סיום אירוע, הקפצת מסך מהיר" + cron כל 30 דקות.

**Code:** `post_meeting_tasks.py` קיים. תיעוד שלנו (`docs/google-calendar-setup.md`) קובע ריצה יומית 02:00. ב-render.yaml זה לא מתוזמן בכלל (F-13).

**Severity:** קריטי — תלוי ב-decision של תדירות.

**Open decision:** **השאלה למשתמש:** כל 30 דקות (Spec) או יומי (קיים)?
- (א) 30 דקות: התראה כמעט מיידית אחרי פגישה. דורש schedule `*/30 * * * *` + `run_in_window` בקוד כדי לא ליצור tasks כפולים.
- (ב) יומי 02:00: פשוט יותר. נועה רואה בבוקר את כל הפגישות מאתמול. אבל אם פגישה הסתיימה ב-08:00 — תזכורת תופיע רק יום אחר כך.

**Acceptance (אופציה א):**
- [ ] schedule משתנה ל-`*/30 * * * *`.
- [ ] Idempotency: ה-job בודק שלא קיים task `post_meeting_update` פתוח לאותו booking (כבר קיים — `NOT EXISTS` ב-query).
- [ ] חלון: רק bookings ש-`end_time + 30min <= now < end_time + 24h`.

**Acceptance (אופציה ב — Spec יתעדכן):**
- [ ] שמירה על schedule יומי 02:00.
- [ ] Spec §11.4 ו-§23 מתוקנים.

---

### F-16: `retry_pending_classification` cron חסר — 🟢

**Spec §23:** Cron כל 60 שניות לעיבוד מחדש של לידים עם `pending_classification=true`.

**Code:** השדה `pending_classification` מוגדר ב-§5.1 בSpec, אבל אין אצלנו מימוש (פאזה 3).

**Severity:** accepted — חלק מפאזה 3 (AI integration).

**Acceptance:** ייווצר במסגרת פאזה 3 יחד עם clean_email_body_for_ai.

---

### F-17: Calendar `colorId="3"` (סגול) על אירועים — ✓ קיים

**Spec §10.1:** אירועי "לקוחות" מסומנים אוטומטית colorId=3.

**Code:** `backend/app/services/google_calendar.py:_create_event_blocking` — `"colorId": "3"` כלול ב-body של ה-event.

**Severity:** ✓ תואם, אין finding.

**Acceptance:** verify — `grep '"colorId"' backend/app/services/google_calendar.py` מחזיר את השורה.

---

### F-18: תזכורת חוזרת בנוסף ל-snooze ידני — 🟢

**Spec §16.1:** "נועה יכולה להגדיר תזכורת חוזרת (כמה פעמים, כל כמה זמן)".

**Code:** אין שדות `repeat_count`/`repeat_interval` ב-Task.

**Severity:** accepted — דחוי ב-`docs/phase-2.5-plan.md §2.2` ("לפאזה 3 או כשיהיה צורך").

---

### F-19: תיעוד קולי + סקילים חסרים — 🟢/🟡

**Spec §13.3:** "כפתור 'הקליטי לעצמך סיכום' — תמלול קולי אוטומטי".

**Spec §25:** סקילים `shabbat-aware-scheduler`, `accessibility-il`, `hebrew-date-converter` חסרים ב-`docs/Skills/`.

**Code:** תיעוד קולי לא ממומש. הסקילים המקומיים: `israeli-phone-formatter`, `hebrew-rtl-best-practices`, `hebrew-tailwind-preset`, `hebrew-i18n`, `gws-hebrew-email-automation`, `hebrew-llm-eval-suite`. שמות שונים, וחלקם חסרים.

**Severity:**
- תיעוד קולי: 🟢 accepted — דחוי ל-POC נפרד אחרי פאזה 3.
- שמות סקילים: 🟡 — צריך ליישר.

**Acceptance (סקילים):**
- [ ] תוספת מקומית של `shabbat-aware-scheduler`, `accessibility-il`, `hebrew-date-converter` — או עדכון §25 ב-Spec.md לפי הקיים.
- [ ] CLAUDE.md (טבלת סקילים) משקף את המצב לאחר היישור.

**הודעת המשתמש:** "אה ותיכף אוסיף את הסקילים החסרים" — מצופה הוספת הסקילים הנדרשים.

---

### F-20: `/today` UX — קליק מנווט במקום פעולה ישירה — 🟡

**Spec §12.6:** "רשימה ממוקדת של 5-7 דברים שצריך לעשות היום. בלי רעש."

**Code:** עמוד `/today` מציג task → קליק מוביל ל-`/leads/[id]`. אין כפתור "שלח" / "התקשרי" ישיר מהרשימה.

**Severity:** מינורי — UX optimization, לא breaks.

**Acceptance:**
- [ ] לכל שורה ב-`/today`: כפתור מהיר לפעולה הראשית של ה-task (לפי `task.type` ו-`lead.preferred_contact`).
- [ ] אם הפעולה דורשת template — פתיחת `TemplatePickerSheet` ישירות.

---

### F-21: סתירה פנימית ב-SpecV2.1 — daily_summary בטבלת §23 — 🟠 (Spec cleanup)

**Spec §23:** `daily_summary | כל יום ב-19:00 | שליחת סיכום יומי **לטלגרם** של נועה`.

**Spec §16.3 + Changelog v2.1:** "הדבר היחיד שמקבל פוש מיידי הוא ליד חדש שנכנס" + "daily_summary לא נשלח לטלגרם אלא מופיע בדשבורד".

**Severity:** בינוני — הסתירה הפנימית עלולה לבלבל מימוש עתידי. ההכרעה ברורה (Changelog מנצח), אבל §23 צריך עדכון.

**הכרעה למימוש:** daily_summary **מופיע בדשבורד**, *לא* בטלגרם.

**Acceptance:**
- [ ] קוד `daily_summary` לא קורא ל-`telegram_service.send_message`.
- [ ] במקום — תוצאת ה-summary נשמרת ב-DB (טבלה חדשה? או JSONB ב-`users`?) כדי שדשבורד יציג כשנועה נכנסת.
- [ ] (לא חובה במסמך, אבל מומלץ) SpecV2.1 §23 מתעדכן בעדכון הבא ל-"בדשבורד" במקום "לטלגרם".

---

### F-22: סתירה פנימית ב-SpecV2.1 — release_stale_locks לא רלוונטי — 🟢 (Spec cleanup)

**Spec §23:** `release_stale_locks | כל 10 דקות | שחרור משימות בסטטוס PROCESSING מעל timeout`.

**הכרעת המשתמש:** "להוריד את זה לגמרי מה-Spec. זה היה בקונטקסט של מנגנון נעילה למניעת race conditions ב-multi-channel publisher (פרויקט אחר), והוא חלחל לכאן בטעות."

**Severity:** accepted-deviation. לא לממש. SpecV2.1 צריך עדכון בעדכון הבא.

**Acceptance:**
- [ ] לא ליצור `release_stale_locks.py`.
- [ ] לא להוסיף ל-render.yaml.
- [ ] (לא חובה במסמך, אבל מומלץ) SpecV2.1 §23 מסיר את השורה בעדכון הבא.

---

## 3. סיכום

### ספירה לפי חומרה

| חומרה | כמות | פירוט |
|---|---|---|
| 🔴 קריטי | 7 | F-01, F-04, F-05, F-06, F-07, F-13, F-15 |
| 🟠 בינוני | 6 | F-03, F-08, F-09, F-10, F-12, F-21 |
| 🟡 מינורי | 3 | F-11, F-14, F-20 |
| 🟢 accepted | 5 | F-02, F-16, F-18, F-19 (חלקי), F-22 |
| ✓ verify only | 1 | F-17 |

**סה"כ findings:** 22.

**אחרי v2.1:** 7 מתוך 9 ה-OD-ים נפתרו ב-Spec, השאר resolved-by-user או נדחו. **אפשר להתחיל מימוש Wave A.**

### דפוסים מנחים

1. **Schema gaps מהאפיון** — F-01, F-03 (chips, service_rates). נוצרו כי בחרתי גישת קוד שעקפה את הסכמה ב-§5.7.
2. **Cron jobs חסרים מ-deploy** — F-13 (3 jobs לא ב-render.yaml). מקור: עבדנו על branch ולא וידאנו yaml תואם.
3. **Telegram חורג מ-"רק לליד חדש"** — F-06, F-07. כולל סתירה פנימית ב-Spec עצמו.
4. **Spec חסר טריגרים** — F-08, F-09 (followup types, ownership state 3) מצוינים אבל לא ברור איך/מתי לטריגר.

---

## 4. Open Decisions — סטטוס

### ✅ נסגרו ב-SpecV2.1 (7)

| # | Finding | סגירה ב-v2.1 |
|---|---|---|
| OD-1 | F-01 chips schema | §5.7 מוסיף `waiting_on` + `followup_task_type` + `auto_followup_days`. §16.4 מפרט per-chip. |
| OD-2 | F-03 service_rates | §5.10 — טבלה חדשה, DB editable. |
| OD-3 | F-07 Telegram daily_summary | Changelog: "daily_summary לא נשלח לטלגרם אלא מופיע בדשבורד". §16.3 מאשר Telegram רק לליד חדש. *(§23 נשאר עם טקסט ישן — ראה F-21)* |
| OD-4 | F-08 followup triggers | §16.4 ממפה צ'יפים → followup types. §17.1 + §17.2 פירוט חישוב. |
| OD-5 | F-09 ownership state 3 | §5.11 — enum value חדש `ASSISTANT_PENDING_NOAH`. |
| OD-6 | F-10 stuck threshold | §16.2 הבחנה מפורשת: "לא טופלו בזמן" (תובנה שבועית, כל overdue) ≠ "ממתין לטיפול" (עמוד נפרד, 7+ ימים). |
| OD-7 | F-11 ARCHIVED reopen | §27.5 acceptance: "ARCHIVED יכול לחזור ל-IN_PROGRESS". |
| OD-9 | F-15 post_meeting timing | §11.4 + §23 — cron כל 30 דק'. |

### ⏳ סגירות פתורות אבל לא דחופות

| # | Finding | סטטוס |
|---|---|---|
| OD-8 | F-14 release_stale_locks | המשתמש: "להוריד את זה לגמרי מה-Spec". §23 בv2.1 *עדיין כולל אותו* — ראה F-22. |

---

## 5. Implementation Order (גלים)

### Wave A — Critical pre-launch (1-2 ימים)

תיקונים שצריכים להיות לפני שנועה רואה את המערכת בכלל. **כל ה-blockers נפתרו ב-SpecV2.1, אפשר להתחיל.**

1. **F-13** — הוספת 3 services ל-render.yaml (5 דקות).
2. **F-04** — service_category אופציונלי (1 שעה — schema + migration + frontend).
3. **F-06** — הסרת Telegram מ-booking request (10 דקות).
4. **F-07** — daily_summary → דשבורד במקום Telegram (1-2 שעות — migration + service + UI bubble).
5. **F-01 + F-05** — chips schema fix לפי §5.7 + seed correction לפי §16.4 (חצי יום).
6. **F-17** — verify only (כבר נעשה).

### Wave B — Pre פאזה 3 (3-5 ימים)

תיקונים חשובים שצריכים להיות לפני שמתחילים פאזה 3, אבל לא חוסמים שימוש בסיסי.

7. **F-08** — 3 כללי פולואפ + integration. הטריגרים מוגדרים ב-§16.4 (chips) ו-§17.
8. **F-09** — ownership state `ASSISTANT_PENDING_NOAH` לפי §5.11.
9. **F-03 + F-12** — service_rates table לפי §5.10.
10. **F-15** — post_meeting cron כל 30 דק' לפי §11.4 + §23.

### Wave C — Nice to have

11. **F-11** — ARCHIVED reopen (תלוי ב-OD-7).
12. **F-10** — stuck threshold aligned (תלוי ב-OD-6).
13. **F-14** — release_stale_locks (תלוי ב-OD-8).
14. **F-19** — סקילים חסרים (המשתמש יוסיף).
15. **F-20** — /today UX direct actions.

### Deferred (פאזה 3)

- **F-02** — email_messages table.
- **F-16** — retry_pending_classification cron.
- **F-18** — תזכורת חוזרת.
- **F-19** (חלקי) — תיעוד קולי.

---

## 6. Verification

### איך נדע שהמסמך מוכן וטוב

1. **כיסוי:** `grep -c "^### F-" docs/spec-deviations.md` מחזיר 20.
2. **Acceptance bullets:** לכל finding יש לפחות 2 acceptance bullets קונקרטיים.
3. **Open decisions:** 9 שאלות פתוחות מצוטטות במפורש בסעיף 4.
4. **Cross-link:** כל finding מצביע ל-Spec section ו-code path עם line numbers.
5. **CLAUDE.md** מעודכן עם הפניה למסמך הזה.

### איך נדע שתיקנו

לאחר מימוש כל finding:

1. ה-acceptance checklists של ה-finding מסומנים כ-`[x]`.
2. ה-code paths המצוטטים שונו / חדשים.
3. `git grep -F "F-NN"` בcommit message מצביע ל-finding הספציפי.
4. אחרי כל גל — סיבוב bugbot על ה-branch.

### Run-time verification (לאחר מימוש Wave A)

```bash
# F-13 - cron jobs ב-render.yaml
grep -c "startCommand: python -m jobs" render.yaml  # צריך להחזיר 8

# F-04 - service_category אופציונלי
grep "service_category: ServiceCategory$" backend/app/schemas/lead.py  # 0 שורות

# F-06 - notify_booking_requested הוסר
grep -rn "notify_booking_requested" backend/app/services/booking.py  # 0 שורות

# F-01/F-05 - chips לפי Spec
psql $DATABASE_URL -c "SELECT label, target_status, auto_followup_days FROM quick_action_chips ORDER BY sort_order"
# צריך להחזיר 6 שורות עם תכני §16.3
```

---

## Changelog

- **v1.0 (מאי 2026):** מסמך ראשוני — 20 findings מ-audit מקיף של Spec.md (v2.0) מול הקוד אחרי פאזות 1+2+2.5.
