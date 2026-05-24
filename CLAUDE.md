> [!IMPORTANT]
> **המסמכים ב-`/docs` הם source of truth - לא הקוד.**
>
> חובה לממש את כל הפיצ'רים וכל האפיון לפי המסמכים הרלוונטיים ב-`/docs`:
> - אסור לקצר מימוש
> - אסור להחסיר
> - אסור להוסיף
> - **אסור להחליט החלטות מוצר באופן עצמאי** (כמו לבחור צ'יפים, סטטוסים, תבניות, צבעים, וכו'). כל פרט קונקרטי - לקרוא מהמסמך.
>
> **לפני מימוש כל פיצ'ר:**
> 1. לקרוא את הסעיף הרלוונטי במסמך **מחדש** (לא להסתמך על זיכרון מסשן קודם)
> 2. אם הפיצ'ר כולל רשימה קונקרטית (צ'יפים, תבניות, סטטוסים) - לוודא Acceptance Criteria בסעיף 27
> 3. אם משהו במסמך לא ברור או חסר - **לעצור ולשאול**, לא להמציא
>
> **אם הקוד הקיים סותר את המסמך - המסמך מנצח.** עדכן את הקוד לפי המסמך.


## תהליך עבודה

1. **קודם מתכננים** – לפני כל מימוש, יש להציג תוכנית עבודה ברורה (עם הסברים בשפה פשוטה ומובנת לכל)
2. **אחר כך מממשים** – המימוש מתחיל רק לאחר אישור התוכנית.

## כלל חשוב: 

אם נמצאו באגים כלשהם בריפו - תמיד נחפש פיתרונות שורשיים לבעיה, ולא פיתרונות "טלאי".

## שפה

- סיכומי PR, תיאורי commit, והודעות סשן — **בעברית**
- הערות בקוד (comments) — **בעברית**
- שמות משתנים, פונקציות, וטבלאות — באנגלית (כמקובל)

---

### כלל 1: בדוק await על כל קריאה לפונקציה async
> לפני push, חפש בכל הקבצים שהשתנו קריאות לפונקציות async. ודא שכל קריאה עטופה ב-`await`. coroutine object ללא await הוא תמיד truthy — זה באג שקט שיכול לשבור הכול.

### כלל 2: Race conditions — check-then-act חייב להיות אטומי
> אל תפריד בין בדיקת תנאי לביצוע פעולה. אם יש lock/mutex, הבדיקה חייבת להיות בתוכו. במיוחד: daily limits, dedup checks, state transitions. השתמש ב-`UPDATE ... WHERE status = 'X'` + `rowcount` במקום SELECT+UPDATE.

### כלל 3: אל תחשוף מידע פנימי ב-API responses
> לפני כל שינוי ב-error handling או exception classes, ודא ש-`to_dict()` / response body לא מכילים: internal IDs, password hashes, stack traces, מזהי DB, או הודעות שגיאה באנגלית טכנית. החזר הודעה גנרית בעברית למשתמש.

### כלל 4: ולידציית קלט מספרי — בדוק NaN, Inf, ו-edge cases
> בכל validator מספרי, בדוק קודם `math.isnan()` ו-`math.isinf()` (Python) או `Number.isNaN()` ו-`!Number.isFinite()` (JS). NaN comparisons תמיד מחזירות False — ה-NaN יעבור כל בדיקת טווח.

### כלל 5: SQLAlchemy async — אל תיגע ב-attributes אחרי commit/close
> אחרי `db.commit()`, כל ה-attributes של model objects דורשים re-fetch. חלץ ערכים פרימיטיביים (IDs, strings) לפני ה-commit, ואז בצע `db.execute(select(...))` מחדש בתוך הלולאה. זה מונע MissingGreenlet errors.

### כלל 6: Escape של user-data בכל output formatter שיש לו סינטקס פעיל
> כשמטמיעים נתון מבחוץ (DB / API / user input) לתוך output עם סינטקס פעיל — HTML, mrkdwn, SQL, shell, ANSI — חובה escape. עדיף formatter נפרד פר-target (Telegram HTML, Slack mrkdwn) על format-string אחיד, כי כללי ה-escape שונים פר ספק וtemplate אחת תעבוד טוב על אחד ותשבור על האחר. דוגמה: `parse_mode=HTML` של Telegram דורש `html.escape`; Slack mrkdwn דורש escape של `& < >` בלבד. סובייקט "Price < $100" או שולח "AT&T" מספיקים לשבור את שני הספקים.

### כלל 7: SSRF — URL מ-user → allowlist origin, לא רק https
> כל endpoint שה-backend עושה אליו fetch/POST עם URL שמשתמש סיפק (webhooks, redirect URIs, image-proxy, file-download) חייב לאמת origin מול allowlist קבוע. הגבלת `https://` בלבד לא מספיקה — `https://169.254.169.254/` היא URL חוקי שמצביע ל-AWS metadata service. לדוגמה: Slack webhook → `https://hooks.slack.com/services/` בלבד.

### כלל 8: לפני קוד של feature עם concurrency/sync — תרחישי race קודם
> כל פיצ'ר שמערב webhooks, cron, multi-instance, או UPDATE/SELECT על אותם משאבים — לכתוב 5-10 תרחישי race לפני המימוש. שאלות חובה: (1) מה קורה אם שני webhooks ירוצו במקביל? (2) מה אם UPDATE מקבל rowcount=0? (3) מה אם sync מתעכב/נפסק באמצע? (4) מה אם פעולה X רצה לפני שפעולה Y הסתיימה? כל תרחיש צריך תשובה ברורה בקוד (אטומיות / optimistic locking / CAS / idempotency). באג שקט בwebhook גרוע מבאג קולני — קשה לזהות, קשה לשחזר.

### כלל 9: Activity log = source of truth, גם כש-UPDATE נכשל
> ב-handlers של webhook/sync, רשום activity *לפני* או *בלי תלות* בהצלחת ה-UPDATE על השורה הראשית. ה-activity מתעד את ה-*intent* (מה ש-Google אמר / מה שהמשתמש ביקש), לא רק את ה-*outcome* בDB. תהליכים downstream (cron, סינון, סטטיסטיקה) צריכים גם signal של "ניסינו" ולא רק "הצלחנו". סמן ב-metadata: `"applied": true/false` כדי להבחין.

### כלל 10: אחרי תיקון באג — בדוק regression בתיקון עצמו
> כל תיקון עלול ליצור באג חדש. אחרי שגרסה X פותר בעיה, חזור על השאלה: "אילו תרחישים *חדשים* התיקון הזה פותח?". במיוחד: תיקון של dedup (פתאום over-dedup), תיקון של filter (פתאום משאיר עוד מקרים), תיקון של race (פתאום lock נשבר). bugbot יתפוס את הרגרסיות, אבל עדיף ש-3 סבבי תיקון יהפכו ל-1.

### כלל 11: שמות מ-enum, לא מהאינטואיציה
> כשמציבים ערך לעמודה ש-string שמוגדרת על-ידי enum (status, type, waiting_on וכו'), קח את הערך *מ-`Enum.MEMBER.value`*, לא ממחרוזת hardcoded. דוגמה: `waiting_on=WaitingOn.CLIENT.value` ולא `waiting_on="CLIENT"` (ובוודאי לא `"THEM"`). זה מונע: typos שעוברים בלי שגיאה, drift בין enum ל-DB, ומקל על rename בעתיד.

### כלל 12: לפני יצירת/שינוי Task — checklist השוואה
> כל פונקציה שיוצרת `Task` (auto-cron, chip apply, service call) צריכה להיות עקבית עם peer-functions קיימים. לפני commit, חפש דוגמה דומה (`grep -n "Task(" backend/app/services backend/jobs`) ובדוק:
> 1. `assigned_to=lead.owner_id` נקבע? (אחרת ה-task לא מופיע ב-owner-scoped views).
> 2. `due_at` ב-UTC? (`next_working_day_start(x).astimezone(timezone.utc)` — לא רק `next_working_day_start(x)`).
> 3. `origin_rule` ייחודי ומתעד את המקור? (debug / analytics).
> 4. `sync_lead_next_action_cache(db, lead_id)` נקרא אחרי `flush()` ולפני `commit()`? (cache stale = `next_action_due_at` שגוי בdashboard).
> 5. Idempotency: יש check מתאים? "כל open task" או "type ספציפי + נוצר אחרי last_outbound_at" — לפי הסמנטיקה.

### כלל 13: לפני שינוי `lead.status` — חפש side-effects
> כל שינוי `Lead.status` (chip, action, cron) צריך לטפל ב-side-effects שתלויים בסטטוס היעד:
> - `PROPOSAL_SENT` → `proposal_sent_at = COALESCE(proposal_sent_at, now)` (אחרת check_stuck_proposals שובר).
> - `BOOKING_PENDING` / `BOOKED` → דורש שורת `Booking` תואמת (אסור להציב ישירות בלי booking flow).
> - `WON` / `LOST` / `ARCHIVED` → רק דרך `close_lead` (closure_reason, closed_at, ביטול tasks).
> - `IN_PROGRESS` → אם הליד היה ב-BOOKING_PENDING/BOOKED עם active booking → דורש קודם לטפל ב-booking.
>
> חוקיות: chip / custom action שמציב status — חוסם targets שדורשים flow ייעודי. ראה `_CHIP_FORBIDDEN_TARGETS` ב-`backend/app/schemas/quick_action_chip.py` כדוגמה.

### כלל 14: כל touchpoint סוגר tasks מ-AUTO_CLOSE_TASK_TYPES
> כל פעולה ש-Noah מבצעת על ליד (chip click, action, mark sent) היא touchpoint = "טיפלה". צריכה לסגור tasks תקועים מאותם sub-types שlist `AUTO_CLOSE_TASK_TYPES` ב-`backend/app/services/lead_actions.py` (FIRST_RESPONSE, LECTURE_INQUIRY, FOLLOWUP, AFTER_HOURS_REPLY, DORMANT_CHECK, WARM_FOLLOWUP, RETRY_CALL). אחרת ה-`/today` ו-`next_action_due_at` יציגו עבודה כפולה. ראה `_close_addressed_tasks` ב-lead_actions.py + שלב 2b ב-`apply_chip`.

---

## מסמכי ייחוס חיצוניים

תיקיית `docs/references/` מכילה blueprints מפרויקטים אחרים — **לא חלק
מהאפיון של נועה**, אלא דפוסי מימוש מוכחים שיש לאמץ בעת בניית פיצ'רים
מתאימים. הם לא תחליף למסמכי `docs/product-spec.md` ו-`docs/tech-spec.md`
שהם המקור היחיד לדרישות; הם רק מקור השראה ארכיטקטונית.

**מתי לעיין:**

| מסמך | מתי |
|---|---|
| `docs/SpecV2.1.md` | **המקור היחיד והאמיתי לדרישות** (גרסה 2.1, מאוחדת). לקרוא את הסעיף הרלוונטי **מחדש** לפני כל מימוש פיצ'ר. אם פיצ'ר כולל רשימה קונקרטית (צ'יפים, סטטוסים, תבניות) — להעתיק את הרשימה ל-commit description ולוודא 1:1 מול §27 (Acceptance Criteria). |
| `docs/spec-deviations.md` | **חובה לקרוא לפני מימוש של פיצ'ר** — רישום כל הפערים הידועים בין `SpecV2.1.md` לבין הקוד, עם acceptance checklists. לפני קוד: `grep -A 30 "F-NN" docs/spec-deviations.md`. אחרי מימוש: לסמן `[x]` ב-acceptance. |
| `docs/progress.md` | **קודם כל** בתחילת כל סשן חדש (אחרי compacting). מסכם מה נבנה, איפה אנחנו, מה הצעדים הפתוחים, וההחלטות הארכיטקטוניות. |
| `docs/references/google-calendar-blueprint.md` | בעת מימוש פאזה 2 (Google Calendar). מכסה OAuth flow + PKCE, הצפנת tokens, FreeBusy API, watch channels + syncToken, `bookingId=` anchor לסנכרון דו-כיווני, וטיפול ב-RefreshError. **שים לב:** הפרויקט המקורי משתמש ב-Telegram/WhatsApp bots לקביעת תור, אצלנו זה דף ווב — קח רק את חלקי ה-Google integration. |
| `docs/google-calendar-setup.md` | לקראת deploy של פאזה 2 — מדריך setup ב-Google Cloud Console (יצירת project, Calendar API, OAuth client) + רשימת env vars שצריך להגדיר ב-Render. **הקובץ הזה מיועד לאדיר** (המתאם), לא לקוד. |
| `docs/phase-3-plan.md` | תכנון פאזה 3 (Gmail + AI). 4 חבילות עבודה, עלויות צפויות, שלבי מימוש 16-20, החלטות פתוחות. **לקרוא לפני התחלת פאזה 3.** |
| `docs/phase-3-ai-token-management.md` | **חובה לפני כל קוד בפאזה 3 שמעביר תוכן ל-AI** — מפרט פונקציית `clean_email_body_for_ai` (תקרות תווים per-purpose, שלבי ניקוי HTML, retry, סינון לפני AI). לקח מ-EmailFlow: HTML גולמי → 10K טוקנים במקום 1.5K → 429 + לידים חסומים. |

**עקרון:** אם הוספת בקוד דפוס שמופיע ב-references, ציין בקומנט קצר
`# ראה: docs/references/<file>.md סעיף N` כדי שמי שיקרא ידע מנין המקור.

---

## סקילים מקומיים — `docs/Skills/`

בפרויקט מותקנים 6 סקילים — יחידות עצמאיות עם `SKILL.md` (הוראות),
`references/` (חומרי עזר), ולעיתים `scripts/` להפעלה. שונה ממסמכי
references: סקיל הוא best-practice עם תוכן אינסטרומנטלי שיש לפעול לפיו,
לא רק להתייחס אליו.

**מתי לפתוח כל סקיל לפני כתיבת קוד:**

| סקיל | מתי לפתוח את `SKILL.md` |
|---|---|
| `israeli-phone-formatter` | בנגיעה ב-`_normalize_phone`, תצוגת טלפון, חיפוש לפי 4 ספרות, או intake שמכיל phone |
| `hebrew-rtl-best-practices` | בהוספה/שינוי קומפוננטה ב-`frontend/components/` עם layout מורכב, scrolling, popovers, או modals |
| `hebrew-tailwind-preset` | בשינוי `tailwind.config.ts`, בהוספת utility classes חדשות, או בעבודה על הקצאת פונטים |
| `hebrew-i18n` | בהוספת טקסט דינמי עם מספר ("3 ימים"), ניסוח תאריכים, פלורליזציה ("יום/יומיים/N ימים") |
| `gws-hebrew-email-automation` | רק בפאזה 3 — בעת מימוש `/intake/email`, סינון Gmail, ניתוח subject/body בעברית |
| `hebrew-llm-eval-suite` | רק בפאזה 3 — בעת בחירת מודל ל-Claude API, כתיבת prompt templates, או הערכת איכות תשובות בעברית |

**עקרון:** לפני כל commit שנוגע ב-area של סקיל — `cat docs/Skills/<name>/SKILL.md`.
זה לוקח דקה ומונע re-do של דברים שכבר פתורים. אם חרגת מההמלצות של
הסקיל, כתוב קומנט מסביר.

**Code review של מה שכבר נכתב:** ראה `docs/skills-review-plan.md`
לרשימה של areas בקוד הקיים שצריך לעבור עליהם מול הסקילים. ה-review
ייעשה משולב בעבודה השוטפת (כל פעם שאני נוגע ב-area), לא כשלב נפרד.
