# Spec Deviations & Gaps

> **גרסה:** 1.2 (מאי 2026)
> **מטרה:** רישום מסודר של *כל* הפערים הידועים בין `docs/SpecV2.1.md` (גרסה 2.1) לבין הקוד הקיים, עם acceptance checklists ברורים לכל פער.
> **למה זה קיים:** בסבבי bugbot הקודמים גילינו שמשפחת ה-chips, ה-Telegram, ה-cron jobs ועוד סטו מהאפיון בלי שנדע. ה-CLAUDE.md המחודש מבהיר: **המסמך מנצח את הקוד**. המסמך הזה הוא ה-source of truth לתיקונים שצריך לבצע לפני שנועה רואה את המערכת.
> **עדכון v1.2:** כל 9 ה-Open Decisions סגורים. SpecV2.1 ענה על 8 מתוכם; F-14 (release_stale_locks) נסגר בהחלטת משתמש (להוריד מ-Spec). נוסף F-23 (defense in depth ל-sync_lead_next_action_cache).

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

**Acceptance:** אין לטפל עכשיו. כשנממש פאזה 3 — יווצר migration ייעודי.

---

### F-03: טבלת `service_rates` — 🟢 הושלם

**Spec v2.1 §5.10:** טבלת `service_rates` עם service_category/subtype/default_price/default_duration_minutes/default_sessions_count/notes/is_active. נטענת אוטומטית מ-§15.2.

**Code:**
- migration 0015 — טבלת service_rates + seed 10 ערכי ברירת מחדל מ-§15.2.
- model app/models/service_rate.py + schema service_rate.py.
- service app/services/service_rates.py — list + update_by_subtype.
- routes/settings.py: GET קורא מ-DB; PATCH /settings/service-rates/{subtype} owner-only.
- utils/service_rates.py נמחק (הוחלף ע"י DB).
- frontend: `app/settings/rates/page.tsx` — owner מקבל NavRow ב-/settings,
  קבוצה לפי category, inline editor per row (מחיר / דקות / מפגשים / notes / פעיל).

**Acceptance:**
- [x] Migration `service_rates` עם seeds מטבלת §15.2.
- [x] GET endpoint קורא מ-DB.
- [x] PATCH endpoint owner-only.
- [x] frontend UI ב-/settings/rates.

**Acceptance (אם הוחלט hardcoded):**
- [ ] תעריפים ב-`constants.py` כ-`DEFAULT_TARIFFS: dict[str, Decimal]`.
- [ ] §22.9 API endpoints מוסרים מ-Spec או מסומנים "פאזה 4".

---

### F-04: `service_category` חובה ב-LeadCreate, האפיון אומר אופציונלי — 🔴

**Spec §7.1:** "שדות חובה ביצירת ליד חדש: שם מלא, טלפון, מקור פנייה. זה הכל. שאר הפרטים אופציונליים."

**Code:** `backend/app/schemas/lead.py:55` — `service_category: ServiceCategory` (ללא `| None`). **חובה** ב-LeadCreate.

**Severity:** קריטי — סותר את האפיון. ליד שמגיע מטופס בלי קטגוריה ייכשל בvalidation.

**Acceptance:**
- [x] `LeadCreate.service_category: ServiceCategory | None = None` ב-`backend/app/schemas/lead.py`.
- [x] `create_lead` ב-service מטפל ב-None (שומר NULL).
- [x] Migration 0011: `ALTER COLUMN service_category DROP NOT NULL`.
- [x] Frontend `NewLeadModal` עם אופציה "— לבחור מאוחר יותר —" כברירת מחדל.
- [x] Read schemas (LeadRead, LeadListItem, DashboardCard, StuckTaskItem, PendingBookingItem, BookingPageInfo) מקבלים `str | None`.
- [x] `labelCategory(null) → "ללא קטגוריה"` ב-frontend.
- [x] `IntakeFormRequest.service_category` גם אופציונלי.

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

### F-07: daily_summary — bubble בדשבורד, לא Telegram — 🟢 הושלם

**Spec §16.2 (v2.1):** "הדבר היחיד שמקבל פוש מיידי הוא ליד חדש שנכנס" — Telegram יוצא מכל שאר ה-flows.

**Changelog v2.1:** "תיקון סתירה: daily_summary לא נשלח לטלגרם אלא מופיע בדשבורד".

**Code (תיקון):**
- טבלה חדשה `daily_summaries` (migration 0012).
- `backend/jobs/daily_summary.py` עושה UPSERT לתוך הטבלה במקום שליחת Telegram.
- `GET /dashboard/home` מחזיר `daily_summary` (ה-row האחרון או null).
- `frontend/app/page.tsx` מציג bubble בראש העמוד כש-`data.daily_summary` קיים.

**Acceptance:**
- [x] `jobs/daily_summary.py` לא מייבא יותר את `telegram_service` ולא קורא לפונקציה ששולחת.
- [x] טבלת `daily_summaries` קיימת (`summary_date UNIQUE`, 4 counters, `generated_at`).
- [x] cron מבצע `ON CONFLICT (summary_date) DO UPDATE` — re-run באותו יום מעדכן.
- [x] `HomeDashboardResponse.daily_summary: DailySummaryRead | None`.
- [x] frontend מציג bubble עם 4 הספירות + תאריך הסיכום.

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

### F-09: מצב בעלות 3 — "עוזרת ממתין לאישור נועה" — 🟡 חלקי

**Spec v2.1 §5.11 + §13.5:** "שלושה מצבי בעלות: באחריות נועה, באחריות עוזרת, **באחריות עוזרת ממתין לאישור נועה**." ה-enum ב-§5.11: `['NOAH', 'CLIENT', 'ASSISTANT', 'ASSISTANT_PENDING_NOAH', 'SYSTEM', 'NONE']`.

**Code:** `backend/app/constants.py:WaitingOn` — נוסף `ASSISTANT_PENDING_NOAH`. ה-frontend מכיר אותו (`WAITING_ON_LABELS` + chip editor option).

**Severity:** בינוני — הערך נוסף לenum, אבל ה-flow המלא של "העברה לאישור" עדיין לא מומש (אין endpoint דבוק).

**Acceptance:**
- [x] `WaitingOn` enum כולל `ASSISTANT_PENDING_NOAH` (commit הזה).
- [x] frontend label + chip editor אופציה.
- [ ] `transfer_lead` תומך בשליחה למצב "ממתין לאישור" + endpoint לאישור (UI flow מלא).
- [ ] תצוגה ייחודית ויזואלית ב-`/leads` ו-card.

**הערה:** ה-flow המלא נשאר ב-Wave B (לא חוסם MVP).

---

### F-10: `/tasks/stuck` קריטריון לא תואם לאפיון — 🟠

**Spec §22.7:** `GET /tasks/stuck` — "תקועים מ-7+ ימים".

**Spec §16.2 (v2.1):** הבחנה מפורשת בין שני המושגים:
- "לא טופלו בזמן" (תובנה שבועית §13.9) — **כל ליד שעבר `next_action_due_at`**, אפילו יום אחד.
- "ממתין לטיפול" (§22.7 `tasks/stuck`) — **רק לידים שתקועים 7+ ימים**.

**Code:** `backend/app/services/tasks.py:list_stuck_tasks` — קריטריון: `Task.due_at <= now_utc` (כל overdue, ללא סף 7 ימים).

**Severity:** בינוני — קריטריון שגוי, מציג רעש (overdue זמני) במקום lattes ימים.

**Acceptance:**
- [x] `list_stuck_tasks`: `Task.due_at <= now_utc - timedelta(days=7)`.
- [x] `weekly_insights.stuck_count` נשאר על כל overdue (תובנת §13.9 השבועית).
- [x] בדיקה: ליד שעבר את due_at לפני 3 ימים לא יופיע ב-`/tasks/stuck` אבל ייספר ב-stuck_count.

---

### F-11: `ARCHIVED → IN_PROGRESS` reopen — 🟢 הושלם

**Spec §6.3 + §27.5 (v2.1):** "ARCHIVED → IN_PROGRESS (`lead_reopened`, ידני)" + "ARCHIVED יכול לחזור ל-IN_PROGRESS".

**Code:** `backend/app/core/state_machine.py:174` — `REOPEN_ALLOWED_FROM = frozenset({WON, LOST, ARCHIVED})`. `backend/app/services/leads.py:408-444` — `reopen_lead` תומך בכל שלושת הסטטוסים.

**Severity:** מינורי — תוקן/מומש בעבר.

**Acceptance:**
- [x] `REOPEN_ALLOWED_FROM` כולל ARCHIVED.
- [x] `reopen_lead` קורא לreset אטומי של closed_at/closed_value/actual_hours.
- [x] Spec §6.3 + §27.5 כוללים את המעבר.

---

### F-12: `DEFAULT_TARIFFS` ב-DB — 🟡 חלקי (F-03 partial)

**Spec §15.2:** טבלת תעריפי ברירת מחדל — קליניקה, סדנה, אומניות, ליווי הפקה וכו'.

**Code:** התעריפים זמינים מ-DB דרך `app/services/service_rates.py` + GET endpoint (commit הזה). pre-populate ביצירת Program עוד לא מומש.

**Severity:** בינוני — נפתר חלקית עם F-03.

**Acceptance:**
- [x] תעריפים נגישים מ-DB (טבלת service_rates).
- [ ] יצירת Program מקבלת `total_price` אוטומטית כברירת מחדל מהתעריף (ניתן לעקוף).

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

### F-14: `release_stale_locks` — 🟢 closed-as-out-of-scope

**Spec §23 (v2.1):** Cron `release_stale_locks` — "כל 10 דקות. שחרור משימות בסטטוס PROCESSING מעל timeout".

**Code:** אין קובץ `release_stale_locks.py` ב-`backend/jobs/`. אין `PROCESSING` כ-`TaskStatus` (יש OPEN/DONE/CANCELED/SNOOZED).

**הכרעת משתמש:** "להוריד את זה לגמרי מה-Spec. במערכת חד-משתמש + cron jobs שרצים פעם אחת אין race ראלי שמצדיק את המנגנון". ראה גם F-22.

**Severity:** accepted-deviation — לא ייושם.

**Acceptance:**
- [x] לא נוצר קובץ `release_stale_locks.py`.
- [x] לא נוסף ל-render.yaml.
- [x] SpecV2.1 §23 מתעדכן בcommit הזה (השורה מוסרת מהטבלה) — ראה F-22.

---

### F-15: `post_meeting_tasks` schedule — 🟢 הושלם

**Spec §11.4 + §23 (v2.1):** "30 דקות אחרי סיום אירוע" + cron כל 30 דקות.

**Code:** `render.yaml` מתזמן `noa-post-meeting-tasks` ב-`*/30 * * * *` (תוקן ב-F-13). הקוד כבר כולל idempotency דרך `NOT EXISTS` per booking_id.

**Severity:** קריטי — תוקן ב-F-13.

**Acceptance:**
- [x] schedule = `*/30 * * * *` ב-render.yaml.
- [x] Idempotency דרך bookings ללא task קיים.
- [x] חלון: bookings ש-`end_time` בעבר (cron עצמו מחליט מה לעבד).

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

### F-22: SpecV2.1 §23 — release_stale_locks הוסר — 🟢 הושלם

**Spec §23 (לפני התיקון):** `release_stale_locks | כל 10 דקות | שחרור משימות בסטטוס PROCESSING מעל timeout`.

**הכרעת המשתמש:** "להוריד את זה לגמרי מה-Spec. במערכת חד-משתמש + cron jobs פנימיים אין race ראלי שמצדיק את המנגנון."

**Severity:** accepted-deviation. spec עודכן.

**Acceptance:**
- [x] לא נוצר `release_stale_locks.py`.
- [x] לא נוסף ל-render.yaml.
- [x] SpecV2.1 §23 הסיר את השורה (commit הזה).
- [x] Changelog v2.1 כולל הערת הסרה.

---

### F-23: ליד סגור עלול לקבל `next_action_due_at` (פרצה בכלל §6.5) — 🟠

**Spec §6.5 (v2.1):** "ליד סגור (WON/LOST/ARCHIVED): אין `next_action`".

**Code:** `backend/app/services/tasks.py:114-151` — `sync_lead_next_action_cache` מעדכן `Lead.next_action_due_at` בכל קריאה ללא בדיקת `status`. אם task נוצר על ליד סגור (race / cron / chip לא תקין), הליד יקבל `next_action_due_at` חי בניגוד לאפיון.

`close_lead` (services/leads.py:236+) **כן** מנקה את השדות *בזמן* הסגירה ומבטל משימות פתוחות — אבל אין defense in depth כש-sync רץ אחר כך מקוד אחר. הפרצה ריאלית בתרחיש: עוזרת סוגרת ליד באותה שנייה שנועה לוחצת chip עליו.

**Severity:** בינוני — תרחיש race ספציפי אבל ה-side effect (ליד "סגור" שמופיע ב-pending) פוגע באמינות המודל.

**Acceptance:**
- [ ] `sync_lead_next_action_cache` מוסיף `AND status NOT IN CLOSED_LEAD_STATUSES` ל-WHERE של ה-UPDATE.
- [ ] התנהגות: ליד סגור עם task פתוח (תרחיש race) — sync לא דורס את `next_action_due_at = NULL`, ולא זורק שגיאה.
- [ ] `apply_chip` endpoint (חדש ב-F-01/F-05) דוחה ליד סגור עם 400 לפני יצירת task.

**Fix sketch:** WHERE clause קטן ב-UPDATE; guard נוסף ב-apply_chip ברמת הAPI.

---

## 3. סיכום

### ספירה לפי חומרה

| חומרה | כמות | פירוט |
|---|---|---|
| 🔴 קריטי | 7 | F-01, F-04, F-05, F-06, F-07, F-13, F-15 |
| 🟠 בינוני | 7 | F-03, F-08, F-09, F-10, F-12, F-21, F-23 |
| 🟡 מינורי | 2 | F-11, F-20 |
| 🟢 accepted / done | 6 | F-02, F-14, F-16, F-18, F-19 (חלקי), F-22 |
| ✓ verify only | 1 | F-17 |

**סה"כ findings:** 23.

**אחרי v2.1:** 7 מתוך 9 ה-OD-ים נפתרו ב-Spec, השאר resolved-by-user או נדחו. **אפשר להתחיל מימוש Wave A.**

### דפוסים מנחים

1. **Schema gaps מהאפיון** — F-01, F-03 (chips, service_rates). נוצרו כי בחרתי גישת קוד שעקפה את הסכמה ב-§5.7.
2. **Cron jobs חסרים מ-deploy** — F-13 (3 jobs לא ב-render.yaml). מקור: עבדנו על branch ולא וידאנו yaml תואם.
3. **Telegram חורג מ-"רק לליד חדש"** — F-06, F-07. כולל סתירה פנימית ב-Spec עצמו.
4. **Spec חסר טריגרים** — F-08, F-09 (followup types, ownership state 3) מצוינים אבל לא ברור איך/מתי לטריגר.

---

## 4. Open Decisions — סטטוס

**כל ה-9 ה-Open Decisions נסגרו (8 ב-SpecV2.1 + 1 בהחלטת משתמש).**

| # | Finding | סגירה |
|---|---|---|
| OD-1 | F-01 chips schema | ✅ v2.1 §5.7 מוסיף `waiting_on` + `followup_task_type` + `auto_followup_days`. §16.4 מפרט per-chip. |
| OD-2 | F-03 service_rates | ✅ v2.1 §5.10 — טבלה חדשה, DB editable. |
| OD-3 | F-07 Telegram daily_summary | ✅ v2.1 Changelog: "daily_summary לא נשלח לטלגרם אלא מופיע בדשבורד". §16.3 מאשר Telegram רק לליד חדש. *(§23 נשאר עם טקסט ישן — ראה F-21)* |
| OD-4 | F-08 followup triggers | ✅ v2.1 §16.4 ממפה צ'יפים → followup types. §17.1 + §17.2 פירוט חישוב. |
| OD-5 | F-09 ownership state 3 | ✅ v2.1 §5.11 — enum value חדש `ASSISTANT_PENDING_NOAH`. |
| OD-6 | F-10 stuck threshold | ✅ v2.1 §16.2 הבחנה מפורשת: "לא טופלו בזמן" (תובנה שבועית, כל overdue) ≠ "ממתין לטיפול" (עמוד נפרד, 7+ ימים). |
| OD-7 | F-11 ARCHIVED reopen | ✅ v2.1 §6.3 + §27.5 acceptance: "ARCHIVED יכול לחזור ל-IN_PROGRESS". כבר מומש בקוד (`reopen_lead`). |
| OD-8 | F-14 release_stale_locks | ✅ **החלטת משתמש:** להסיר מהspec. v2.1 §23 מתעדכן ב-commit הזה (ראה F-22). |
| OD-9 | F-15 post_meeting timing | ✅ v2.1 §11.4 + §23 — cron כל 30 דק'. מומש ב-F-13. |

---

## 5. Implementation Order (גלים)

### Wave A — Critical pre-launch (1-2 ימים)

תיקונים שצריכים להיות לפני שנועה רואה את המערכת בכלל. **כל ה-blockers נפתרו ב-SpecV2.1.**

1. **F-13** — הוספת 3 services ל-render.yaml. ✅ הושלם.
2. **F-04** — service_category אופציונלי. ✅ הושלם.
3. **F-06** — הסרת Telegram מ-booking request. ✅ הושלם.
4. **F-07** — daily_summary → דשבורד במקום Telegram. ✅ הושלם.
5. **F-22** — הסרת `release_stale_locks` מ-SpecV2.1 §23. ✅ הושלם.
6. **F-23** — guard ב-`sync_lead_next_action_cache` נגד דריסת next_action על ליד סגור. ⏳ commit הזה.
7. **F-01 + F-05** — chips schema fix לפי §5.7 + seed correction לפי §16.4. ⏳ commit הזה.
8. **F-17** — verify only (כבר נעשה).

### Wave B — Pre פאזה 3 (3-5 ימים)

תיקונים חשובים שצריכים להיות לפני שמתחילים פאזה 3, אבל לא חוסמים שימוש בסיסי.

9. **F-08** — 3 כללי פולואפ + integration. ה-task types החדשים (`retry_call`, `send_proposal`, `warm_followup`, `lecture_inquiry`, `dormant_check`) נוספים ל-enum במסגרת F-01/F-05; ב-Wave B נוסיף את ה-cron jobs שיוצרים אותם.
10. **F-09** — ownership state `ASSISTANT_PENDING_NOAH` לפי §5.11.
11. **F-10** — stuck threshold = `due_at <= now - 7d` לפי §16.2 + §22.7.
12. **F-03 + F-12** — service_rates table לפי §5.10.

### Wave C — Nice to have

13. **F-15** — verify only (post_meeting ✅ הושלם ב-F-13).
14. **F-19** — סקילים חסרים (המשתמש יוסיף).
15. **F-20** — /today UX direct actions.
16. **F-21** — Spec cleanup של §23 (daily_summary לטלגרם → לדשבורד).

### Deferred (פאזה 3)

- **F-02** — email_messages table.
- **F-16** — retry_pending_classification cron.
- **F-18** — תזכורת חוזרת.
- **F-19** (חלקי) — תיעוד קולי.

---

## 6. Verification

### איך נדע שהמסמך מוכן וטוב

1. **כיסוי:** `grep -c "^### F-" docs/spec-deviations.md` מחזיר 23.
2. **Acceptance bullets:** לכל finding יש לפחות 2 acceptance bullets קונקרטיים.
3. **Open decisions:** 9 ה-ODs סגורים (8 ב-v2.1 + 1 בהחלטת משתמש). אין יותר בלוקרים פתוחים.
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
- **v1.1 (מאי 2026):** סנכרון מול SpecV2.1 (חלקי). הוספת F-21 + F-22.
- **v1.2 (מאי 2026):** סיום audit מול SpecV2.1.
  - כל 9 ה-ODs סגורים (8 ב-v2.1 + 1 בהחלטת משתמש על F-14).
  - F-10/F-11/F-15 — סטטוס עודכן (הושלמו ב-iterations קודמים או ב-spec).
  - F-14 — closed-as-out-of-scope; SpecV2.1 §23 מוסר את השורה.
  - F-22 — הושלם (הסרת השורה מ-spec ב-commit הזה).
  - F-23 חדש — defense in depth ב-`sync_lead_next_action_cache` כנגד דריסת `next_action_due_at` על ליד סגור.
