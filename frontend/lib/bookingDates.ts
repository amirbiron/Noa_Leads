/**
 * עזרי התאריך של גריד הקביעה + טיפוס החודש.
 *
 * הוצאו לכאן כששני מסלולי הקביעה — קישור של ליד וקישור פתוח — נזקקו
 * לאותו גריד בדיוק. עותק שני היה נסחף: שינוי באופן שבו נבנה יום או
 * מחושב שם חודש באחד מהם היה משאיר את השני עם רשת שמתארת משהו אחר
 * ממה שהשרת מוכן לקבל.
 */

import { toIsraelISODate } from "@/lib/date";

const ISRAEL_TZ = "Asia/Jerusalem";

// formatDate היה wrapper מקומי; הוחלף ב-toIsraelISODate המשותף ב-
// `lib/date.ts`. הוא משתמש באותו `en-CA` עם options מפורשות (year/
// month/day) — כך שהפלט יציב לפורמט YYYY-MM-DD בכל הדפדפנים.
export const formatDate = toIsraelISODate;

// ===== עזרי תאריך לגריד החודשי =====
// כל יום נבנה כ-12:00 UTC. בישראל (UTC+2/+3) זה תמיד אותו תאריך קלנדרי,
// כך שהגריד זהה לחישוב של השרת גם כשהמכשיר מוגדר לאזור זמן אחר. בניית
// `new Date()` מקומי הייתה יכולה להזיז את היום הראשון ביום שלם.
export function dateAtNoonUTC(year: number, month: number, day: number): Date {
  return new Date(Date.UTC(year, month - 1, day, 12));
}

export function parseISODate(iso: string): { year: number; month: number; day: number } {
  const [year, month, day] = iso.split("-").map(Number);
  return { year, month, day };
}

// יום 0 של החודש הבא = היום האחרון של החודש המבוקש.
export function daysInMonth(year: number, month: number): number {
  return new Date(Date.UTC(year, month, 0)).getUTCDate();
}

export function monthLabel(year: number, month: number): string {
  return dateAtNoonUTC(year, month, 1).toLocaleDateString("he-IL", {
    month: "long",
    timeZone: ISRAEL_TZ,
  });
}

export function monthKeyOf(iso: string): string {
  const { year, month } = parseISODate(iso);
  return `${year}-${month}`;
}

// חודש בחירה אחד בגריד: התוויות שלו והטווח לשליפה מהשרת.
export type BookingMonth = {
  key: string;
  label: string;
  dates: Date[];
  from: string;
  to: string;
};

export function shortDayName(d: Date): string {
  return d.toLocaleDateString("he-IL", {
    weekday: "short",
    timeZone: ISRAEL_TZ,
  });
}

export function shortDate(d: Date): string {
  return d.toLocaleDateString("he-IL", {
    day: "2-digit",
    month: "2-digit",
    timeZone: ISRAEL_TZ,
  });
}

export function slotLabel(iso: string): string {
  return new Date(iso).toLocaleTimeString("he-IL", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: ISRAEL_TZ,
  });
}

export function fullSlotLabel(start: string, end: string): string {
  const s = new Date(start).toLocaleString("he-IL", {
    weekday: "long",
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: ISRAEL_TZ,
  });
  const e = slotLabel(end);
  return `${s} - ${e}`;
}
