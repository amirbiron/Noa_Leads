# Skills Review Plan

מסמך שמרכז מה צריך לעבור עליו בקוד הקיים מול 6 הסקילים ב-`docs/Skills/`.
ה-review **לא ייעשה כשלב נפרד** אלא משולב בעבודה השוטפת: בכל פעם שאני
נוגע ב-area רלוונטי, אעבור על הפריטים הרלוונטיים כאן, אעדכן את הסטטוס,
ואקפיץ קומיט.

מצב כל פריט: ⬜ לא בוצע · ✅ בוצע · ⏭️ דולג (עם הסבר)

---

## 1. `israeli-phone-formatter`

הסקיל מספק validation מלא של קידומות ישראליות + scripts/validate_phone.py.
הקוד שלנו כיום בודק רק תווים מותרים, לא קידומות/ספירת ספרות.

**לבדוק/לתקן:**

- ✅ **`backend/app/schemas/lead.py:_normalize_phone`** — תוקן. נוסף `app/utils/phone.py` עם patterns מהסקיל (נייד 05X/0-9 ספרות, קווי 02-04/08-09, VoIP 07[2-9], 1-700/1-800, *XXXX). אימות מלא + נירמול ל-`0XX-XXXXXXX`. תומך גם ב-`+972`/`972` (ממיר ל-0) וגם במספרי חו"ל (pass-through). 17 test cases.
- ✅ **חיפוש `list_leads`** — כבר משתמש ב-`regexp_replace`, מתאים להמלצות הסקיל.
- ✅ **המרת `+972` ל-`0`** — מטופל ב-backend `_normalize_phone` בכניסה. כל input שמגיע ל-API ייקלט נכון.
- ✅ **תצוגה אחידה** — backend מאחסן עכשיו תמיד בפורמט `0XX-XXXXXXX` (או international לחו"ל). ה-DB הוא source of truth, frontend מציג כפי שמגיע.
- ✅ **wa.me URL** — נוסף `frontend/lib/phone.ts:toWhatsAppDigits` שממיר ל-E.164 ללא + (`972521234567`). תוקן ב-`leads/[id]/page.tsx` ו-`TemplatePickerSheet.tsx` — בעבר wa.me קיבל `0521234567` שלא עובד.

**מתי לטפל:** בוצע.

---

## 2. `hebrew-rtl-best-practices`

הסקיל מכסה logical CSS props, `:dir()` pseudo-class, icon mirroring, פונטים.
אנחנו כבר משתמשים ב-logical (`border-s`, `ms`, `pe`) — אבל לא בדקנו הכל.

**לבדוק/לתקן:**

- ✅ **Physical CSS audit** — `grep` על `ml-/mr-/pl-/pr-/border-l/border-r/left-/right-/rounded-l/rounded-r/text-left/text-right` חזר נקי. הכל logical (`ms-`, `me-`, `ps-`, `pe-`, `border-s`, `inset-inline-*`).
- ✅ **Icon mirroring** — סקירה מלאה:
  - `ChevronLeft`/`ArrowLeft` (3 מקומות): כבר מצביעים נכון ל"קדימה" ב-RTL. אין שיקוף.
  - `Send` (paper plane, 2 מקומות): נוסף `rtl:-scale-x-100` — הסקיל מסווג "חצי שליחה" כצריכים שיקוף.
  - `Phone`/`Mail`/`MessageCircle`/`Search`/`Clock`/`Settings`/`X`/`Check`/`Plus`/`Trash` — universal, לא משקפים (לפי הסקיל).
  - `ArrowRightLeft` (transfer) — bidirectional, לא משקפים.
- ✅ **Bidi: email/phone בטקסט מעורב** — תוקן ב-settings (`<span dir="ltr">{email}</span> · {role}`). יתר המקומות עם phone/email היו כבר עם `dir="ltr"`.
- ✅ **`:dir()` vs `[dir="rtl"]`** — לא בשימוש; אנחנו ב-Tailwind `rtl:` variant הסטנדרטי.

**מתי לטפל:** בוצע.

---

## 3. `hebrew-tailwind-preset`

**לבדוק/לתקן:**

- ✅ **שדרוג ל-Tailwind v4.3.0** — בוצע. v4 יציבה מאז Jan 2025.
  - הוסר `tailwindcss 3.4.17` + `autoprefixer`
  - הוסף `tailwindcss ^4` + `@tailwindcss/postcss ^4`
  - `postcss.config.mjs` עודכן ל-`@tailwindcss/postcss` plugin יחיד
  - `tailwind.config.ts` נמחק (v4 auto-scans את כל ה-`./app/**/*.tsx` וכו')
- ✅ **`@theme` block** — צבעי המצב והפונטים הוגדרו ב-CSS תחת `@theme {}` (פונטים, --color-state-*).
- ✅ **`@utility pb-safe`** — הועבר ל-syntax v4.
- ✅ **dir variants** — `rtl:-scale-x-100` מתקמפל ל-`:where(:dir(rtl), [dir=rtl], [dir=rtl] *)` ב-v4 — שימוש אוטומטי ב-`:dir()` pseudo-class המודרני (בדיוק מה שהסקיל המליץ).

**Audit לאחר השדרוג:**
- אין שימוש ב-`bg-opacity-*`/`text-opacity-*`/`ring-opacity-*` (deprecated ב-v4)
- אין שימוש ב-`ring-*` בקוד
- כל ה-`border-*` עם צבע מפורש — לא נפלנו על default שהשתנה ל-`currentColor`
- Build: 10 routes, types ✓, CSS bundle תקין (אומת ב-`.next/static/css`).

**מתי לטפל:** רק אם נראה issue ויזואלי או אם משדרגים tailwind.

---

## 4. `hebrew-i18n`

הסקיל מכסה i18n frameworks (react-intl, next-intl, vue-i18n) + פלורליזציה +
פורמט תאריכים/מספרים.

אנחנו לא משתמשים ב-i18n framework — יש לנו `frontend/lib/hebrew.ts` עם
מילונים פשוטים ופונקציות פורמט. זה מתאים לnon-multilingual app (עברית בלבד),
אבל פלורליזציה לא מטופלת כראוי.

**לבדוק/לתקן:**

- ✅ **`formatRelativeHebrew`** — תוקן עם `pluralizeTimeUnit` helper לפי קטגוריות CLDR (one/two/other). הצורות לפי הסקיל: דקה / שתי דקות / N דקות; שעה / שעתיים / N שעות; יום / יומיים / N ימים. בנוסף: היום/מחר/אתמול כשרלוונטי. אומת על 19 test cases.
- ⏭️ **`Intl.RelativeTimeFormat`** — דילגתי. לא נותן את הצורה הזוגית ("יומיים") הנדרשת בעברית, רק "לפני יום אחד" / "לפני 2 ימים". helper מקומי קצר יותר ועקבי עם הסקיל.
- ⬜ **`Intl.NumberFormat('he-IL')`** — כבר משתמשים ב-`toLocaleString("he-IL")` בכמה מקומות, לוודא שכל המקומות עקביים.

**מתי לטפל:** בוצע (formatRelativeHebrew). יתר ייעשה בסבב polish כללי.

---

## 5. `gws-hebrew-email-automation` — פאזה 3

**אין קוד קיים לסקור.** הסקיל יתועל כשנממש את `/intake/email` ב-פאזה 3.

**Notes לפאזה 3:**
- Gmail Pub/Sub setup לקליטה בזמן אמת
- פילטרים בעברית למיון אוטומטי (subject contains "פנייה" / "הצעה" / וכו')
- חיתוך quote/signature ב-replies בעברית (קשה יותר מאשר באנגלית — אין `On wrote:` בעברית)
- ניסוח תזכורת תשלום בש"ח (לא רלוונטי לנו, אנחנו לא מטפלים בתשלומים)

---

## 6. `hebrew-llm-eval-suite` — פאזה 3

**אין קוד קיים לסקור.** הסקיל יתועל כשנשתמש ב-Claude ל-summaries, סינון
מיילים עסקיים, ניסוח הצעות.

**Notes לפאזה 3:**
- ה-suite כולל scripts ל-`run_eval.py`, `make_scorecard.py`, `score_results.py`
- benchmarks: HeQ (Hebrew Q&A), Hebrew sentiment
- המלצה לסקיל לפני בחירת מודל: `claude-sonnet-4-6` לסיכומים מורכבים, `claude-haiku-4-5` לסיווג מהיר (כבר ב-tech-spec)

---

## טבלת priorities

| פריט | סטטוס | הערה |
|---|---|---|
| `formatRelativeHebrew` פלורליזציה | ✅ Done | 19 test cases |
| `_normalize_phone` קידומות ישראליות | ✅ Done | 17 test cases + wa.me E.164 |
| Phone display formatting אחיד | ✅ Done | backend מנרמל ב-storage |
| Icon mirroring + bidi audit | ✅ Done | Send שוקף + email dir="ltr" |
| Tailwind v4 שדרוג | ✅ Done | + auto `:dir(rtl)` בונוס |
| `@theme` block לפונטים | ✅ Done | --color-state-*, --font-sans |

**כל הפריטים שזוהו ב-review הושלמו.** ב-pass עתידי על הסקילים הנותרים
(`gws-hebrew-email-automation` ו-`hebrew-llm-eval-suite`) — בעת מימוש פאזה 3.
