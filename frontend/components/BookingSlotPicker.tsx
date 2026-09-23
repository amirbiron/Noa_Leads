"use client";

import { AlertCircle, ChevronDown, Clock } from "lucide-react";
import type { BookingSlots } from "@/hooks/useBookingSlots";
import {
  formatDate,
  shortDate,
  shortDayName,
  slotLabel,
} from "@/lib/bookingDates";
import type { TimeSlot } from "@/lib/types";
import { cn } from "@/lib/utils";

/**
 * בחירת יום ושעה — משותף לשני דפי הקביעה.
 *
 * **למה רכיב משותף ולא עותק בכל דף:** מה שהלקוח רואה כאן הוא התשובה
 * לשאלה "מתי אפשר לקבוע", והיא חייבת להיות אחת בשני המסלולים. הטפסים
 * שמסביב שונים בצדק (בקישור הפתוח יש שם, בקישור של ליד יש הערה), אבל
 * הגריד, מצבי הטעינה והשגיאה, והמעבר לחודש הבא — אלה אותו דבר, ועותק
 * שני שלהם היה נסחף בשינוי הראשון.
 *
 * הרכיב לא מחזיק state משלו: הכל מגיע מ-`useBookingSlots` ומהסלוט
 * שהדף בחר, כך שאין ערך מקומי שיכול להתיישן מול ה-props.
 */
export function BookingSlotPicker({
  slots,
  selectedSlot,
  onSelectSlot,
}: {
  slots: BookingSlots;
  selectedSlot: TimeSlot | null;
  /** `null` כשהלקוח עובר ליום אחר — הסלוט שנבחר קודם כבר לא מוצג. */
  onSelectSlot: (slot: TimeSlot | null) => void;
}) {
  const {
    visibleMonths,
    nextMonth,
    showNextMonth,
    lastBookableDate,
    selectedDate,
    setSelectedDate,
    dayLookup,
    monthLoading,
    monthError,
    slotsForSelectedDate,
    selectedMonth,
    selectedMonthLoading,
    selectedMonthError,
    fetchMonth,
  } = slots;

  return (
    <>
      {/* בחירת יום */}
      <section>
        <div className="text-sm font-semibold text-gray-700 mb-2">
          בחרי יום
        </div>

        {/* גריד לכל חודש פתוח. החודש הנוכחי מוצג מהיום ועד סופו;
            החודש הבא נפתח בכפתור ומוצג במלואו. מעבר לזה אין — האופק
            מגיע מהשרת (`booking_horizon_end`) ולא מחושב כאן. */}
        {visibleMonths.map((month) => (
          <div key={month.key} className="mb-3 last:mb-0">
            {/* כותרת החודש מוצגת רק כששני החודשים פתוחים — בחודש
                יחיד היא רעש, כי אין ממה להבדיל. */}
            {visibleMonths.length > 1 && (
              <div className="text-xs font-medium text-gray-500 mb-1.5">
                {month.label}
              </div>
            )}
            <div className="grid grid-cols-7 gap-1.5">
              {month.dates.map((d, indexInMonth) => {
                const key = formatDate(d);
                // היום הראשון בכל חודש מוצב בעמודה של יום השבוע שלו,
                // כך שהגריד נקרא כלוח שנה: כל השבתות בעמודה אחת. שאר
                // הימים זורמים אחריו. ב-RTL עמודה 1 היא הימנית, ולכן
                // ראשון=1 ... שבת=7 מייצר בדיוק את הסדר העברי.
                // getUTCDay נכון כאן כי כל יום נבנה כ-12:00 UTC.
                const gridColumnStart =
                  indexInMonth === 0 ? d.getUTCDay() + 1 : undefined;
                const daySlots = dayLookup.get(key);
                const hasSlots = (daySlots?.length ?? 0) > 0;
                const isSelected = selectedDate === key;
                const isLoading = !!monthLoading[month.key];
                const hasError = !!monthError[month.key];
                return (
                  <button
                    key={key}
                    style={{ gridColumnStart }}
                    onClick={() => {
                      setSelectedDate(key);
                      onSelectSlot(null);
                    }}
                    // כשיש שגיאת fetch — לא מכבים את הכפתורים, אחרת כל
                    // החודש נראה אפור כאילו אין זמינות אמיתית.
                    disabled={!hasSlots && !isLoading && !hasError}
                    className={cn(
                      "flex flex-col items-center py-2 rounded-lg text-xs border",
                      isSelected
                        ? "bg-gray-900 text-white border-gray-900"
                        : hasSlots || hasError
                        ? "bg-white border-gray-200 text-gray-700"
                        : "bg-gray-50 border-gray-100 text-gray-300",
                    )}
                  >
                    <span>{shortDayName(d)}</span>
                    <span className="font-semibold mt-0.5">{shortDate(d)}</span>
                  </button>
                );
              })}
            </div>
          </div>
        ))}

        {/* פתיחת החודש הבא — האפשרות היחידה להתקדם קדימה. אין בורר
            תאריכים חופשי: הוא אפשר לבחור כל תאריך בכל שנה, והשרת ממילא
            דוחה כל מועד מעבר לאופק. */}
        {nextMonth ? (
          <button
            onClick={showNextMonth}
            className="mt-1 w-full rounded-lg border border-gray-200 bg-white py-2.5 text-sm text-gray-700 flex items-center justify-center gap-1.5 active:bg-gray-50"
          >
            <ChevronDown size={14} aria-hidden />
            הצגת {nextMonth.label}
          </button>
        ) : lastBookableDate ? (
          <div className="mt-1 text-xs text-gray-500 text-center">
            אפשר לקבוע פגישה עד {shortDate(lastBookableDate)}.
          </div>
        ) : null}
      </section>

      {/* סלוטים */}
      <section>
        <div className="text-sm font-semibold text-gray-700 mb-2">
          בחרי שעה
        </div>
        {selectedMonthLoading ? (
          <div className="text-center text-gray-400 text-sm py-6">טוען…</div>
        ) : selectedMonthError ? (
          // שגיאה אמיתית בטעינת החודש — לא מציגים "אין סלוטים", כי זה
          // מטעה: אולי היומן עמוס באמת ואולי הקריאה נכשלה. retry לאותו חודש.
          <div className="bg-white rounded-xl border border-state-red/30 px-4 py-5 flex flex-col items-center gap-3">
            <div className="flex items-start gap-2 text-state-red text-sm">
              <AlertCircle size={16} className="mt-0.5 shrink-0" aria-hidden />
              <span>{selectedMonthError}</span>
            </div>
            <button
              onClick={() => selectedMonth && void fetchMonth(selectedMonth)}
              className="text-sm rounded-lg border border-gray-200 px-4 py-2 hover:bg-gray-50"
            >
              נסי שוב
            </button>
          </div>
        ) : slotsForSelectedDate.length === 0 ? (
          <div className="bg-white rounded-xl border border-dashed border-gray-200 px-4 py-6 text-center text-sm text-gray-400">
            אין סלוטים פנויים ביום זה.
          </div>
        ) : (
          <div className="grid grid-cols-3 gap-2">
            {slotsForSelectedDate.map((slot) => {
              const isSelected =
                selectedSlot?.start === slot.start &&
                selectedSlot?.end === slot.end;
              return (
                <button
                  key={slot.start}
                  onClick={() => onSelectSlot(slot)}
                  className={cn(
                    "py-2.5 rounded-lg text-sm border flex items-center justify-center gap-1",
                    isSelected
                      ? "bg-gray-900 text-white border-gray-900"
                      : "bg-white border-gray-200 text-gray-800",
                  )}
                >
                  <Clock size={12} aria-hidden />
                  {slotLabel(slot.start)}
                </button>
              );
            })}
          </div>
        )}
      </section>
    </>
  );
}
