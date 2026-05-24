
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

---

## מסמכי ייחוס חיצוניים

תיקיית `docs/references/` מכילה blueprints מפרויקטים אחרים — **לא חלק
מהאפיון של נועה**, אלא דפוסי מימוש מוכחים שיש לאמץ בעת בניית פיצ'רים
מתאימים. הם לא תחליף למסמכי `docs/product-spec.md` ו-`docs/tech-spec.md`
שהם המקור היחיד לדרישות; הם רק מקור השראה ארכיטקטונית.

**מתי לעיין:**

| מסמך | מתי |
|---|---|
| `docs/progress.md` | **קודם כל** בתחילת כל סשן חדש (אחרי compacting). מסכם מה נבנה, איפה אנחנו, מה הצעדים הפתוחים, וההחלטות הארכיטקטוניות. |
| `docs/references/google-calendar-blueprint.md` | בעת מימוש פאזה 2 (Google Calendar). מכסה OAuth flow + PKCE, הצפנת tokens, FreeBusy API, watch channels + syncToken, `bookingId=` anchor לסנכרון דו-כיווני, וטיפול ב-RefreshError. **שים לב:** הפרויקט המקורי משתמש ב-Telegram/WhatsApp bots לקביעת תור, אצלנו זה דף ווב — קח רק את חלקי ה-Google integration. |
| `docs/google-calendar-setup.md` | לקראת deploy של פאזה 2 — מדריך setup ב-Google Cloud Console (יצירת project, Calendar API, OAuth client) + רשימת env vars שצריך להגדיר ב-Render. **הקובץ הזה מיועד לאדיר** (המתאם), לא לקוד. |

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
