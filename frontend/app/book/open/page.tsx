"use client";

import { useEffect, useState } from "react";
import { BookingCenteredCard } from "@/components/BookingCenteredCard";
import { BookingPhoneField } from "@/components/BookingPhoneField";
import { BookingSlotPicker } from "@/components/BookingSlotPicker";
import { BookingSuccessCard } from "@/components/BookingSuccessCard";
import { api, ApiError } from "@/lib/api";
import { fullSlotLabel } from "@/lib/bookingDates";
import { pluralizeMinutes } from "@/lib/hebrew";
import type { OpenBookingPageInfo, TimeSlot } from "@/lib/types";
import { useBookingSlots } from "@/hooks/useBookingSlots";

// הקישור הפתוח לקביעת פגישה — אחד וקבוע, לא קשור לאף ליד. ציבורי: בלי
// AuthGuard ובלי token. ההגנות מפני שימוש לרעה יושבות בשרת (מגבלת קצב
// ותקרת בו-זמניות ב-`routes/booking_page.py`).
//
// מה ששונה מדף הליד, וזה הכל: אין כרטיס ליד שממנו נלקח השם — ולכן שדה
// שם, חובה. אין הערה, כי לא התבקשה. ואין תקרת פגישות או באנר של פגישות
// קיימות — אין ליד שהן שייכות לו. בחירת המועד עצמה משותפת לשני הדפים
// (`BookingSlotPicker` + `useBookingSlots`).
//
// הנתיב הסטטי `open` קודם ל-`[token]` הדינמי באותה תיקייה.
// מקור: next/dist/shared/lib/router/utils/sorted-routes.js (`_smoosh`).

export default function OpenBookingPage() {
  const [info, setInfo] = useState<OpenBookingPageInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [selectedSlot, setSelectedSlot] = useState<TimeSlot | null>(null);
  const [fullName, setFullName] = useState("");
  const [phone, setPhone] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState<{
    start: string;
    end: string;
  } | null>(null);

  useEffect(() => {
    api
      .getOpenBookingPageInfo()
      .then(setInfo)
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : "שגיאה בטעינה"),
      )
      .finally(() => setLoading(false));
  }, []);

  // נקרא לפני כל return מוקדם (Rules of Hooks).
  const slots = useBookingSlots({
    today: info?.today ?? null,
    horizonEnd: info?.booking_horizon_end ?? null,
    enabled: !!info,
    loadAvailability: (from, to) => api.getOpenBookingAvailability(from, to),
  });

  // השם הוא חובה: בלי כרטיס ליד, זה המקור היחיד לשם שייכנס ליומן. השרת
  // אוכף את אותו כלל (ודוחה גם שם של רווחים בלבד) — הבדיקה כאן היא רק
  // כדי שהכפתור לא ייראה זמין כשאי אפשר לשלוח.
  const canSubmit =
    !submitting && fullName.trim().length > 0 && phone.trim().length > 0;

  async function submit() {
    if (!selectedSlot || !canSubmit) return;
    setSubmitting(true);
    setError(null);
    try {
      const result = await api.createOpenBooking({
        slot_start: selectedSlot.start,
        slot_end: selectedSlot.end,
        full_name: fullName.trim(),
        contact_phone: phone.trim(),
      });
      setSuccess({ start: result.slot_start, end: result.slot_end });
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "שגיאה בקביעת הפגישה",
      );
      // ראה את אותו טיפול בדף הליד: "בחרי מועד אחר מהרשימה המעודכנת"
      // מחייב שהרשימה תתעדכן באמת.
      if (err instanceof ApiError && err.status === 409) {
        slots.reloadSelectedMonth();
      }
    } finally {
      setSubmitting(false);
    }
  }

  function selectSlot(slot: TimeSlot | null) {
    setSelectedSlot(slot);
    setError(null);
  }

  // ===== מצבים שונים =====

  if (loading) {
    return <BookingCenteredCard>טוען…</BookingCenteredCard>;
  }

  if (error && !info) {
    return (
      <BookingCenteredCard>
        <div className="text-state-red text-center">{error}</div>
      </BookingCenteredCard>
    );
  }

  if (!info) return null;

  if (success) {
    return <BookingSuccessCard start={success.start} end={success.end} />;
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-200">
        <div className="max-w-2xl mx-auto px-4 py-5">
          <h1 className="text-xl font-semibold">קביעת פגישה עם נועה</h1>
          <div className="text-sm text-gray-500 mt-0.5">
            {pluralizeMinutes(info.default_duration_minutes)}
          </div>
        </div>
      </header>

      <main className="max-w-2xl mx-auto p-4 space-y-5">
        <BookingSlotPicker
          slots={slots}
          selectedSlot={selectedSlot}
          onSelectSlot={selectSlot}
        />

        {selectedSlot && (
          <section className="space-y-3 bg-white rounded-xl border border-gray-200 p-4">
            <div className="text-sm">
              <span className="text-gray-500">מועד נבחר: </span>
              <span className="font-medium">
                {fullSlotLabel(selectedSlot.start, selectedSlot.end)}
              </span>
            </div>

            <label className="block">
              <div className="text-xs text-gray-500 mb-1">
                שם מלא <span className="text-state-red">*</span>
              </div>
              {/* dir="auto": שם יכול להיות בעברית או באנגלית, והדפדפן
                  בוחר כיוון לפי מה שהוקלד. maxLength תואם ל-`full_name`
                  בשרת (200, כמו `leads.full_name`). */}
              <input
                type="text"
                autoComplete="name"
                dir="auto"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                maxLength={200}
                className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm text-start focus:outline-none focus:border-gray-900"
              />
            </label>

            <BookingPhoneField value={phone} onChange={setPhone} />

            {error && (
              <div className="text-sm text-state-red bg-state-red/10 rounded-lg px-3 py-2">
                {error}
              </div>
            )}

            <button
              onClick={submit}
              disabled={!canSubmit}
              className="w-full rounded-lg bg-gray-900 text-white py-3 font-medium disabled:opacity-50"
            >
              {submitting ? "קובעת…" : "קביעת הפגישה"}
            </button>
            <div className="text-xs text-gray-500 text-center">
              הפגישה תיקבע מיד ותיכנס ליומן.
            </div>
          </section>
        )}
      </main>
    </div>
  );
}
