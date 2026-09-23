"use client";

import { useState } from "react";
import { CalendarPlus, Copy, Check } from "lucide-react";

/**
 * הקישור הפתוח לקביעת פגישה.
 *
 * בניגוד לקישור שמופק מכרטיס ליד, הקישור הזה **אחד וקבוע** ואינו קשור
 * לאף רשומה: מי שפותח אותו ממלא שם וטלפון בעצמו, והפגישה נכנסת ישירות
 * ליומן. לכן אין כאן כפתור "הפקה" — אין מה להפיק, הכתובת תמיד אותה
 * כתובת.
 */
export function OpenBookingLinkSection() {
  const [copied, setCopied] = useState(false);

  // נבנה מ-`window.location.origin` ולא מ-`process.env`, בדיוק כמו
  // `CopyBookingLinkButton` בדף הליד — כך זה עובד גם ב-dev על host אחר
  // וגם בפרודקשן, בלי משתנה סביבה נוסף שצריך לזכור להגדיר.
  const url =
    typeof window !== "undefined"
      ? `${window.location.origin}/book/open`
      : "";

  async function copy() {
    if (!url) return;
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      // ה-Clipboard API דורש secure context ועלול להיחסם. בלי ה-fallback
      // הזה הלחיצה לא עושה כלום ונראית כמו כפתור שבור.
      window.prompt("העתיקי את הקישור:", url);
    }
  }

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4">
      <div className="flex items-start gap-2">
        <CalendarPlus
          size={16}
          className="text-brand-primary mt-0.5 shrink-0"
          aria-hidden
        />
        <div className="min-w-0 flex-1">
          <div className="text-sm font-medium text-gray-900">
            קישור פתוח לקביעת פגישה
          </div>
          <p className="text-xs text-gray-600 mt-1 leading-relaxed">
            קישור אחד וקבוע, שאינו קשור לאף ליד. מי שפותח אותו ממלא שם
            וטלפון, בוחר מועד פנוי, והפגישה נכנסת ליומן שלך עם הפרטים
            שמילא. <strong>לא נוצר ליד במערכת</strong> — הפגישה מופיעה
            ביומן בלבד.
          </p>
          {/* הקישור מסרב לקבוע כשהיומן לא מחובר (`OpenBookingUnavailable`
              בשרת): בלי יומן אין לאן להכניס את הפגישה. הלקוח רואה את
              הסירוב — אבל מי שצריכה לפעול היא נועה, ולכן זה כתוב כאן. */}
          <p className="text-xs text-gray-500 mt-1 leading-relaxed">
            הקישור פועל רק כשיומן Google מחובר.
          </p>

          {/* הכתובת עצמה מוצגת ולא רק מועתקת: אם ההעתקה נחסמת בדפדפן,
              עדיין אפשר לסמן ולהעתיק ידנית. `dir="ltr"` כי זו כתובת
              לטינית בתוך עמוד עברי, ובלעדיו הסלאשים קופצים למקום הלא
              נכון. `break-all` כדי שלא תדחוף גלילה אופקית במובייל. */}
          <div
            dir="ltr"
            className="mt-2 rounded-lg bg-gray-50 border border-gray-200 px-2.5 py-2 text-xs text-gray-700 font-mono break-all"
          >
            {url || "…"}
          </div>

          <button
            onClick={copy}
            className="mt-2 w-full rounded-lg bg-white border border-gray-200 py-2 text-sm font-medium flex items-center justify-center gap-1.5"
          >
            {copied ? (
              <>
                <Check size={14} aria-hidden />
                הקישור הועתק
              </>
            ) : (
              <>
                <Copy size={14} aria-hidden />
                העתקת הקישור
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
