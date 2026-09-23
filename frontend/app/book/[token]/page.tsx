"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { Calendar, Info } from "lucide-react";
import { BookingCenteredCard } from "@/components/BookingCenteredCard";
import { BookingPhoneField } from "@/components/BookingPhoneField";
import { BookingSlotPicker } from "@/components/BookingSlotPicker";
import { BookingSuccessCard } from "@/components/BookingSuccessCard";
import { api, ApiError } from "@/lib/api";
import { fullSlotLabel } from "@/lib/bookingDates";
import { labelCategory, labelSubtype, pluralizeMinutes } from "@/lib/hebrew";
import type { BookingPageInfo, TimeSlot } from "@/lib/types";
import { useBookingSlots } from "@/hooks/useBookingSlots";

// דף קביעת תור ציבורי. לא ב-AuthGuard — הליד מגיע מקישור ש-נועה שלחה
// לו ב-WhatsApp/מייל. הtoken בURL הוא ה-credential היחיד.

export default function BookingPage() {
  const params = useParams<{ token: string }>();
  const token = params.token;

  const [info, setInfo] = useState<BookingPageInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [selectedSlot, setSelectedSlot] = useState<TimeSlot | null>(null);
  const [phone, setPhone] = useState("");
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState<{
    start: string;
    end: string;
  } | null>(null);

  // טעינת מידע ראשוני
  useEffect(() => {
    if (!token) return;
    api
      .getBookingPageInfo(token)
      .then(setInfo)
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : "שגיאה בטעינה"),
      )
      .finally(() => setLoading(false));
  }, [token]);

  // מנגנון הרשת החודשית משותף לשני מסלולי הקביעה — ראה
  // `hooks/useBookingSlots.ts` ו-`components/BookingSlotPicker.tsx`.
  // מה שנשאר כאן הוא רק מה ששייך לליד: התקרה, הפגישות הקיימות, וההערה.
  // נקרא לפני כל return מוקדם (Rules of Hooks).
  const slots = useBookingSlots({
    today: info?.today ?? null,
    horizonEnd: info?.booking_horizon_end ?? null,
    // בעבר היה כאן גם `has_active_booking`, וזה מה שעצר את טעינת
    // הזמינות כשללקוח כבר הייתה פגישה. עכשיו רק התקרה עוצרת.
    enabled: !!info?.can_book_more,
    loadAvailability: (from, to) =>
      api.getBookingAvailability(token, from, to),
  });

  async function submit() {
    if (!selectedSlot) return;
    setSubmitting(true);
    setError(null);
    try {
      const result = await api.createBooking(token, {
        slot_start: selectedSlot.start,
        slot_end: selectedSlot.end,
        contact_phone: phone.trim(),
        notes: notes.trim() || undefined,
      });
      setSuccess({ start: result.slot_start, end: result.slot_end });
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "שגיאה ביצירת הבקשה",
      );
      // המועד נתפס בינתיים — ההודעה מבקשת לבחור "מהרשימה המעודכנת",
      // ולכן הרשימה חייבת להתעדכן באמת. הסלוט שנבחר **נשאר** במקומו:
      // איפוס שלו היה מסתיר את כל סעיף הטופס, ואיתו את ההודעה עצמה.
      if (err instanceof ApiError && err.status === 409) {
        slots.reloadSelectedMonth();
      }
    } finally {
      setSubmitting(false);
    }
  }

  // בחירת מועד אחר מנקה את שגיאת הקביעה הקודמת — היא דיברה על המועד
  // הקודם, ובלי זה "הסלוט כבר תפוס" היה נשאר מתחת למועד חדש ופנוי.
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

  // 1) הצלחה — אחרי submit. הפגישה כבר קבועה; אין שלב אישור.
  if (success) {
    return <BookingSuccessCard start={success.start} end={success.end} />;
  }

  // 2) הגעת לתקרת הפגישות — המצב היחיד שחוסם את הדף.
  //    פגישה קיימת לבדה **אינה** חוסמת יותר: היא מוצגת כבאנר למטה,
  //    והלקוח יכול לקבוע מועד נוסף. זו הייתה המגבלה שהוסרה.
  if (!info.can_book_more) {
    return (
      <BookingCenteredCard>
        <div className="text-center space-y-3">
          <Calendar className="mx-auto text-state-green" size={48} aria-hidden />
          <div className="text-lg font-semibold">
            {info.upcoming_bookings.length === 1
              ? "כבר קבועה לך פגישה"
              : `כבר קבועות לך ${info.upcoming_bookings.length} פגישות`}
          </div>
          <div className="space-y-1">
            {info.upcoming_bookings.map((b) => (
              <div key={b.start} className="text-base text-gray-900">
                {fullSlotLabel(b.start, b.end)}
              </div>
            ))}
          </div>
          <div className="text-sm text-gray-500 mt-3">
            כדי לקבוע פגישה נוספת או לשנות מועד, צרי קשר עם נועה ישירות.
          </div>
        </div>
      </BookingCenteredCard>
    );
  }

  // 3) טופס קביעת פגישה
  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-200">
        <div className="max-w-2xl mx-auto px-4 py-5">
          <div className="text-xs text-gray-500 mb-1">קביעת פגישה עם נועה</div>
          <h1 className="text-xl font-semibold">{info.lead_name}</h1>
          <div className="text-sm text-gray-600 mt-0.5">
            {labelCategory(info.service_category)}
            {info.service_subtype && ` · ${labelSubtype(info.service_subtype)}`}
            {" · "}
            <span className="text-gray-500">
              {pluralizeMinutes(info.default_duration_minutes)}
            </span>
          </div>
        </div>
      </header>

      <main className="max-w-2xl mx-auto p-4 space-y-5">
        {!slots.includesGoogleBusy && (
          <div className="text-xs text-state-orange bg-state-orange/10 rounded-lg px-3 py-2 flex items-start gap-2">
            <Info size={14} className="mt-0.5 shrink-0" aria-hidden />
            סנכרון יומן זמני לא פעיל. ייתכן שחלק מהסלוטים יתבררו כתפוסים
            בהמשך.
          </div>
        )}

        {/* פגישות שכבר קבועות. באנר בלבד — הבורר נשאר פתוח מתחתיו,
            כי אפשר לקבוע פגישה נוספת. */}
        {info.upcoming_bookings.length > 0 && (
          <div className="bg-white border border-gray-200 rounded-xl px-4 py-3">
            <div className="flex items-start gap-2">
              <Calendar
                size={15}
                className="text-state-green mt-0.5 shrink-0"
                aria-hidden
              />
              <div className="text-sm">
                <div className="font-medium text-gray-900">
                  {info.upcoming_bookings.length === 1
                    ? "כבר קבועה לך פגישה"
                    : `כבר קבועות לך ${info.upcoming_bookings.length} פגישות`}
                </div>
                <ul className="text-gray-600 mt-1 space-y-0.5">
                  {info.upcoming_bookings.map((b) => (
                    <li key={b.start}>{fullSlotLabel(b.start, b.end)}</li>
                  ))}
                </ul>
                <div className="text-xs text-gray-500 mt-1.5">
                  אפשר לקבוע פגישה נוספת למטה.
                </div>
              </div>
            </div>
          </div>
        )}

        <BookingSlotPicker
          slots={slots}
          selectedSlot={selectedSlot}
          onSelectSlot={selectSlot}
        />

        {/* אישור + הערה */}
        {selectedSlot && (
          <section className="space-y-3 bg-white rounded-xl border border-gray-200 p-4">
            <div className="text-sm">
              <span className="text-gray-500">מועד נבחר: </span>
              <span className="font-medium">
                {fullSlotLabel(selectedSlot.start, selectedSlot.end)}
              </span>
            </div>

            <BookingPhoneField value={phone} onChange={setPhone} />

            <label className="block">
              <div className="text-xs text-gray-500 mb-1">
                הערה לנועה (אופציונלי)
              </div>
              <textarea
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                rows={2}
                maxLength={500}
                placeholder="לדוגמה: זה הביקור הראשון שלי"
                className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:border-gray-900"
              />
            </label>

            {error && (
              <div className="text-sm text-state-red bg-state-red/10 rounded-lg px-3 py-2">
                {error}
              </div>
            )}

            <button
              onClick={submit}
              disabled={submitting || phone.trim().length === 0}
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
