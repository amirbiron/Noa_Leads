// תיאריך בישראל — utilities משותפים.
//
// **למה לא להסתמך על default של `toLocaleDateString("en-CA")` בלי
// options?** המפתחות `en-CA` הם בעיקרון YYYY-MM-DD, אבל ICU/CLDR
// עדכוני data שינו זאת בעבר (Chrome/Firefox החזירו M/d/yyyy ל-en-CA
// בלי options). אם הפלט סוטה מ-YYYY-MM-DD, השוואת מחרוזות עם תאריך
// backend (שתמיד YYYY-MM-DD) נשברת בשקט. options מפורשות מבטיחות
// פלט יציב בכל הדפדפנים והגרסאות.

const ISRAEL_TZ = "Asia/Jerusalem";

/**
 * מחזיר תאריך כ-YYYY-MM-DD בTZ ישראל. תואם לפורמט של DateField ב-DB
 * (`summary_date`, `booking_date` וכו'). יציב לכל הדפדפנים — options
 * מפורשות מונעות drift של locale defaults.
 */
export function toIsraelISODate(d: Date = new Date()): string {
  return d.toLocaleDateString("en-CA", {
    timeZone: ISRAEL_TZ,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });
}

/**
 * "YYYY-MM-DD" → "YYYY-MM-(DD+1)" — ארתימטיקה ב-UTC טהור (לא תלוי
 * ב-browser local TZ). מטפל ברולאובר חודש/שנה/leap year.
 *
 * שימוש: לחישוב "האם summaryDate + 1 = today"; השוואה דרך string match
 * עם פלט של `toIsraelISODate`.
 */
export function plusOneIsoDate(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  const next = new Date(Date.UTC(y, m - 1, d + 1));
  return next.toISOString().slice(0, 10);
}

/**
 * "YYYY-MM-DD" → "YYYY-MM-(DD - N)" — UTC arithmetic, מטפל ב-rollover.
 * משמש לחישוב "השבת האחרונה בישראל" (1-2 ימים אחורה ב-
 * `shouldShowAiWeeklySummary`).
 */
export function isoMinusDays(iso: string, days: number): string {
  const [y, m, d] = iso.split("-").map(Number);
  const target = new Date(Date.UTC(y, m - 1, d - days));
  return target.toISOString().slice(0, 10);
}

/**
 * השעה הנוכחית (0-23) בשעון ישראל. ל-gating של תצוגה תלוית-שעה
 * (למשל הסתרת בועת הסיכום היומי אחרי 07:00 — §12.4).
 */
export function israelHour(d: Date = new Date()): number {
  const h = d.toLocaleString("en-US", {
    timeZone: ISRAEL_TZ,
    hour: "2-digit",
    hour12: false,
  });
  // "24" ב-hour12:false על חצות בחלק מהדפדפנים → נרמול ל-0.
  return Number(h) % 24;
}

/**
 * יום השבוע בישראל: 0=Sunday, 1=Monday, ..., 6=Saturday — תואם ל-Date.getDay().
 * משמש ל-gating של תצוגות תלויות-יום (למשל סיכום שבועי ב-§6.8).
 *
 * המימוש: מעבירים את ה-Date לטקסט "MM/DD/YYYY" ב-en-US/Asia/Jerusalem ואז
 * מפרסרים — נמנעים מהמלכודת של `new Date(toLocaleString(...))` שמפרסר
 * את המחרוזת ב-TZ של ה-host, לא ב-TZ של ישראל.
 */
export function israelWeekday(d: Date = new Date()): number {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: ISRAEL_TZ,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(d);
  const get = (type: string) => Number(parts.find((p) => p.type === type)!.value);
  // Date.UTC + getUTCDay = יום-השבוע של התאריך הישראלי, ללא הזזת host TZ.
  return new Date(Date.UTC(get("year"), get("month") - 1, get("day"))).getUTCDay();
}

/**
 * §6.8 — חלון תצוגה לסיכום השבועי: ראשון 08:00 → שני 07:00 (כ-23 שעות).
 * נקרא ב-`/` כדי להחליט אם להציג את כרטיס ה-`ai_weekly_summary`.
 *
 * cursor bugbot: בנוסף לחלון הזמן, מאמת ש-`summaryWeekEnd` (השבת של
 * השבוע שהסיכום מכסה, מתוך `date_range_end` של ה-row) תואם לשבת
 * האחרונה בישראל. אחרת — סיכום ישן (cron דילג בחג לפי §6.7, או נכשל)
 * יוצג כאילו הוא של השבוע. אותו דפוס בדיוק כמו `shouldShowDailySummary`
 * שמאמת את תאריך הסיכום היומי.
 */
export function shouldShowAiWeeklySummary(
  summaryWeekEnd: string,
  now: Date = new Date(),
): boolean {
  const day = israelWeekday(now);
  const hour = israelHour(now);
  const inWindow =
    (day === 0 && hour >= 8) || (day === 1 && hour < 7);
  if (!inWindow) return false;

  // "השבת האחרונה בישראל" — Sun→1 day back, Mon→2 days back.
  // (day + 1) % 7: Sun(0)→1, Mon(1)→2, ..., Sat(6)→0. הפונקציה רק
  // נקראת בחלון Sun/Mon, אז מספיק לטפל בשני המקרים האלה — אבל
  // הנוסחה הכללית עובדת בכל יום, ל-defense-in-depth.
  const daysBack = (day + 1) % 7;
  const expectedWeekEnd = isoMinusDays(toIsraelISODate(now), daysBack);
  return summaryWeekEnd === expectedWeekEnd;
}

/**
 * חישוב טריות תאריך הסיכום היומי (string YYYY-MM-DD מ-backend ב-Israel TZ)
 * מול היום הנוכחי בישראל.
 *
 * משמש גם להצגת label "סיכום היום / סיכום אתמול" וגם ל-gating
 * (`shouldShowDailySummary`).
 */
export function computeDailySummaryStaleness(
  summaryDate: string,
): "today" | "yesterday" | "older" {
  const todayIsrael = toIsraelISODate();
  if (summaryDate === todayIsrael) return "today";
  if (plusOneIsoDate(summaryDate) === todayIsrael) return "yesterday";
  return "older";
}

/**
 * §12.4 / §6.8 — חלון תצוגה לסיכום היומי (בועה סטטיסטית או כרטיס AI):
 * 19:00 → 07:00 למחרת. סיכום של היום מוצג תמיד; סיכום של אתמול מוצג
 * רק לפני 07:00 (חלון סקירה לילי של 12 שעות); מ-07:00 ואילך — מוסתר עד
 * הסיכום הבא ב-19:00. ישן מאתמול — מוסתר תמיד.
 */
const DAILY_SUMMARY_HIDE_HOUR = 7;
export function shouldShowDailySummary(summaryDate: string): boolean {
  const staleness = computeDailySummaryStaleness(summaryDate);
  if (staleness === "today") return true;
  if (staleness === "yesterday") return israelHour() < DAILY_SUMMARY_HIDE_HOUR;
  return false;
}
