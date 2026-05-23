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
| ~~`_normalize_phone` הוספת אימות קידומות~~ | ✅ Done | תוקן + 17 test cases + wa.me E.164 |
| ~~Phone display formatting אחיד~~ | ✅ Done | backend מנרמל ב-storage |
| Icon mirroring + `:dir()` audit | Medium | בסבב a11y |
| Tailwind v4 שדרוג | Low | רק אם צריך |
| `@theme` block לפונטים | Low | רק אם נשדרג ל-v4 |
