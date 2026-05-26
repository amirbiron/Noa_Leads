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
