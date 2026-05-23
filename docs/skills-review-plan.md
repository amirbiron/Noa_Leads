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

- ⬜ **`backend/app/schemas/lead.py:_normalize_phone`** — להוסיף אימות קידומת (050-058/02-09/07X/1-800/*XXXX) וספירת ספרות לפי טבלת הסקיל. אופציה: לקרוא לסקריפט `validate_phone.py` או לשכפל את הלוגיקה הקצרה ל-Python בלבד.
- ⬜ **`backend/app/services/leads.py:list_leads` (חיפוש)** — הסקיל ממליץ על נירמול דרך `regexp_replace`. כבר עושים את זה. ✓ to verify only.
- ⬜ **המרת `+972` ל-`0`** ב-input של `NewLeadModal.tsx` — אוטומטית כשהמשתמש מקליד.
- ⬜ **תצוגה אחידה** של phone ב-`leads/[id]/page.tsx` ו-`LeadCardRow` — להציג תמיד בפורמט `050-1234567` (גם אם נשמר אחרת).

**מתי לטפל:** בפעם הבאה שאני נוגע ב-phone-related code, או בסבב a11y/UX ייעודי.

---

## 2. `hebrew-rtl-best-practices`

הסקיל מכסה logical CSS props, `:dir()` pseudo-class, icon mirroring, פונטים.
אנחנו כבר משתמשים ב-logical (`border-s`, `ms`, `pe`) — אבל לא בדקנו הכל.

**לבדוק/לתקן:**

- ⬜ **חיפוש `left`/`right` במחלקות** — `grep -rn "\\bleft\\|right\\b" frontend/components/ frontend/app/` ובדיקה שכולם logical. נמצאו: `inset-inline-end-4`, `text-end`, `ps-9 pe-3` — אלה בסדר. צריך לאמת.
- ⬜ **Icon mirroring** — `ChevronLeft` ב-`LeadCardRow.tsx`, `TodayActionRow.tsx`, `NavRow` בsettings: לפי הסקיל צריך `:dir(rtl) { transform: scaleX(-1); }` או לבחור `ChevronRight` ב-RTL. במצב הנוכחי החץ הוא ChevronLeft (מצביע שמאלה) — ב-RTL זה "קדימה" שזה הגיוני, אבל יש לוודא שזה מכוון.
- ⬜ **scroll directions** ב-modals — `TemplatePickerSheet`, `CloseLeadModal` (max-h-[95vh] flex-col + overflow-y-auto) — לבדוק שאין `scroll-padding-left/right` שלא מותאם.
- ⬜ **`:dir()` במקום `[dir="rtl"]`** — אנחנו לא משתמשים ב-attribute selector בכלל. ✓ to verify.

**מתי לטפל:** בסבב a11y/RTL ייעודי, או כשמוסיפים קומפוננטה חדשה עם layout מורכב.

---

## 3. `hebrew-tailwind-preset`

הסקיל ממליץ על Tailwind v4. אנחנו על v3.4.17. גרסה v3.1+ תומכת ב-dir variants —
התאמה חלקית.

**לבדוק/לתקן:**

- ⬜ **שדרוג ל-Tailwind v4** — לא דחוף ולא בהכרח רצוי (v4 בשלבי early adoption, יציבות פחותה). דחיתי לעתיד.
- ⬜ **`@theme` block + פונטים עבריים** — להעביר את הגדרת Heebo מ-Google Fonts לרשימת `@theme` מסודרת לפי הסקיל.
- ⬜ **dir variants** — אם נצטרך styling שונה ב-LTR/RTL (לא צפוי, אנחנו RTL-only), להשתמש ב-`rtl:` ו-`ltr:`.

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

| פריט | priority | מתי |
|---|---|---|
| ~~`formatRelativeHebrew` פלורליזציה~~ | ✅ Done | תוקן + 19 test cases |
| `_normalize_phone` הוספת אימות קידומות | Medium | בנגיעה הבאה ב-lead intake |
| Icon mirroring + `:dir()` audit | Medium | בסבב a11y |
| Phone display formatting אחיד | Low | בסבב polish |
| Tailwind v4 שדרוג | Low | רק אם צריך |
| `@theme` block לפונטים | Low | רק אם נשדרג ל-v4 |
