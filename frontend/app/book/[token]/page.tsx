"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { AlertCircle, Calendar, CheckCircle2, Clock, Info } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { labelCategory, labelSubtype, pluralizeMinutes } from "@/lib/hebrew";
import type {
  AvailabilityResponse,
  BookingPageInfo,
  TimeSlot,
} from "@/lib/types";
import { cn } from "@/lib/utils";

// דף קביעת תור ציבורי. לא ב-AuthGuard — הליד מגיע מקישור ש-נועה שלחה
// לו ב-WhatsApp/מייל. הtoken בURL הוא ה-credential היחיד.

const ISRAEL_TZ = "Asia/Jerusalem";
const DAYS_TO_SHOW = 14;

function formatDate(d: Date): string {
  // YYYY-MM-DD בTZ ישראל. en-CA מפיק נטיב YYYY-MM-DD ועם timeZone
  // ה-Intl מטפל בהמרה בלי round-trip של string דרך new Date — שזה היה
  // שביר (toLocaleString("en-US") מחזיר פורמט implementation-defined,
  // ובדפדפנים מסוימים `new Date("12/25/2026, 15:00:00")` נכשל → NaN,
  // והמפתחות בlookup נשברו ולא תאמו את ה-days[].date מהAPI).
  return d.toLocaleDateString("en-CA", {
    timeZone: ISRAEL_TZ,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });
}

function shortDayName(d: Date): string {
  return d.toLocaleDateString("he-IL", {
    weekday: "short",
    timeZone: ISRAEL_TZ,
  });
}

function shortDate(d: Date): string {
  return d.toLocaleDateString("he-IL", {
    day: "2-digit",
    month: "2-digit",
    timeZone: ISRAEL_TZ,
  });
}

function slotLabel(iso: string): string {
  return new Date(iso).toLocaleTimeString("he-IL", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: ISRAEL_TZ,
  });
}

function fullSlotLabel(start: string, end: string): string {
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

export default function BookingPage() {
  const params = useParams<{ token: string }>();
  const token = params.token;

  const [info, setInfo] = useState<BookingPageInfo | null>(null);
  const [availability, setAvailability] = useState<AvailabilityResponse | null>(
    null,
  );
  const [loading, setLoading] = useState(true);
  const [loadingSlots, setLoadingSlots] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // מצב שגיאה נפרד לטעינת זמינות. חיוני להבחין בין "אין סלוטים פנויים"
  // (יום עמוס לגיטימי) לבין "ה-fetch נכשל" (רשת/שרת/גוגל). אחרת הליד
  // רואה "אין סלוטים" ומניח שאין מועדים כלל ב-14 הימים.
  const [availabilityError, setAvailabilityError] = useState<string | null>(null);

  // טווח ימים זמין לבחירה — מהיום ועד DAYS_TO_SHOW
  const allDates = useMemo(() => {
    const today = new Date();
    const arr: Date[] = [];
    for (let i = 0; i < DAYS_TO_SHOW; i++) {
      const d = new Date(today);
      d.setDate(today.getDate() + i);
      arr.push(d);
    }
    return arr;
  }, []);

  const [selectedDate, setSelectedDate] = useState<string>(formatDate(new Date()));
  const [selectedSlot, setSelectedSlot] = useState<TimeSlot | null>(null);
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState<{
    start: string;
    end: string;
  } | null>(null);

  // טעינת מידע ראשוני + זמינות
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

  const fetchAvailability = useMemo(
    () => async () => {
      if (!token || !info || info.has_active_booking) return;
      setLoadingSlots(true);
      setAvailabilityError(null);
      const first = allDates[0];
      const last = allDates[allDates.length - 1];
      try {
        const result = await api.getBookingAvailability(
          token,
          formatDate(first),
          formatDate(last),
        );
        setAvailability(result);
      } catch (err) {
        setAvailability(null);
        setAvailabilityError(
          err instanceof ApiError ? err.message : "שגיאה בטעינת זמינות",
        );
      } finally {
        setLoadingSlots(false);
      }
    },
    [token, info, allDates],
  );

  useEffect(() => {
    void fetchAvailability();
  }, [fetchAvailability]);

  const slotsForSelectedDate = useMemo(() => {
    if (!availability) return [];
    const day = availability.days.find((d) => d.date === selectedDate);
    return day?.slots ?? [];
  }, [availability, selectedDate]);

  async function submit() {
    if (!selectedSlot) return;
    setSubmitting(true);
    setError(null);
    try {
      const result = await api.createBooking(token, {
        slot_start: selectedSlot.start,
        slot_end: selectedSlot.end,
        notes: notes.trim() || undefined,
      });
      setSuccess({ start: result.slot_start, end: result.slot_end });
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "שגיאה ביצירת הבקשה",
      );
    } finally {
      setSubmitting(false);
    }
  }

  // ===== מצבים שונים =====

  if (loading) {
    return <CenteredCard>טוען…</CenteredCard>;
  }

  if (error && !info) {
    return (
      <CenteredCard>
        <div className="text-state-red text-center">{error}</div>
      </CenteredCard>
    );
  }

  if (!info) return null;

  // 1) הצלחה — אחרי submit
  if (success) {
    return (
      <CenteredCard>
        <div className="text-center space-y-3">
          <CheckCircle2
            className="mx-auto text-state-green"
            size={56}
            aria-hidden
          />
          <div className="text-xl font-semibold">הבקשה התקבלה</div>
          <div className="text-sm text-gray-600">
            המועד המבוקש:
          </div>
          <div className="text-base font-medium text-gray-900">
            {fullSlotLabel(success.start, success.end)}
          </div>
          <div className="text-sm text-gray-500 mt-4">
            נועה תאשר את הפגישה ותחזור אליך בהקדם. תקבלי הודעה בערוץ שלך.
          </div>
        </div>
      </CenteredCard>
    );
  }

  // 2) כבר יש תור פעיל
  if (info.has_active_booking && info.active_booking_at) {
    const statusLabel =
      info.active_booking_status === "approved"
        ? "אושר ע\"י נועה"
        : "ממתין לאישור";
    // active_booking_end עשוי להיות null בלידים ישנים מאוד; fallback ל-start
    const endLabel = info.active_booking_end ?? info.active_booking_at;
    return (
      <CenteredCard>
        <div className="text-center space-y-3">
          <Calendar className="mx-auto text-state-green" size={48} aria-hidden />
          <div className="text-lg font-semibold">כבר יש לך בקשת תור</div>
          <div className="text-base text-gray-900">
            {fullSlotLabel(info.active_booking_at, endLabel)}
          </div>
          <div className="text-sm text-state-orange bg-state-orange/10 rounded-lg px-3 py-2 mt-2">
            {statusLabel}
          </div>
          <div className="text-sm text-gray-500 mt-3">
            אם רוצה להחליף מועד, צרי קשר עם נועה ישירות.
          </div>
        </div>
      </CenteredCard>
    );
  }

  // 3) טופס קביעת תור
  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-200">
        <div className="max-w-2xl mx-auto px-4 py-5">
          <div className="text-xs text-gray-500 mb-1">קביעת תור עם נועה</div>
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
        {availability && !availability.includes_google_busy && (
          <div className="text-xs text-state-orange bg-state-orange/10 rounded-lg px-3 py-2 flex items-start gap-2">
            <Info size={14} className="mt-0.5 shrink-0" aria-hidden />
            סנכרון יומן זמני לא פעיל. ייתכן שחלק מהסלוטים יתבררו כתפוסים
            לאחר האישור.
          </div>
        )}

        {/* בחירת יום */}
        <section>
          <div className="text-sm font-semibold text-gray-700 mb-2">
            בחרי יום
          </div>
          <div className="grid grid-cols-7 gap-1.5">
            {allDates.map((d) => {
              const key = formatDate(d);
              const dayData = availability?.days.find((x) => x.date === key);
              const hasSlots = (dayData?.slots.length ?? 0) > 0;
              const isSelected = selectedDate === key;
              return (
                <button
                  key={key}
                  onClick={() => {
                    setSelectedDate(key);
                    setSelectedSlot(null);
                  }}
                  // כשיש שגיאת fetch — לא מכבים את הכפתורים, אחרת כל
                  // השבועיים נראים אפורים כאילו אין זמינות אמיתית.
                  disabled={
                    !hasSlots && !loadingSlots && !availabilityError
                  }
                  className={cn(
                    "flex flex-col items-center py-2 rounded-lg text-xs border",
                    isSelected
                      ? "bg-gray-900 text-white border-gray-900"
                      : hasSlots || availabilityError
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
        </section>

        {/* סלוטים */}
        <section>
          <div className="text-sm font-semibold text-gray-700 mb-2">
            בחרי שעה
          </div>
          {loadingSlots ? (
            <div className="text-center text-gray-400 text-sm py-6">טוען…</div>
          ) : availabilityError ? (
            // שגיאה אמיתית — לא מציגים "אין סלוטים", כי זה מטעה: אולי
            // היומן עמוס באמת ואולי הקריאה נכשלה. מבדילים ונותנים retry.
            <div className="bg-white rounded-xl border border-state-red/30 px-4 py-5 flex flex-col items-center gap-3">
              <div className="flex items-start gap-2 text-state-red text-sm">
                <AlertCircle size={16} className="mt-0.5 shrink-0" aria-hidden />
                <span>{availabilityError}</span>
              </div>
              <button
                onClick={() => void fetchAvailability()}
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
                    onClick={() => setSelectedSlot(slot)}
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

        {/* אישור + הערה */}
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
              disabled={submitting}
              className="w-full rounded-lg bg-gray-900 text-white py-3 font-medium disabled:opacity-50"
            >
              {submitting ? "שולחת בקשה…" : "אישור בקשת תור"}
            </button>
            <div className="text-xs text-gray-500 text-center">
              המועד עדיין דורש אישור של נועה.
            </div>
          </section>
        )}
      </main>
    </div>
  );
}

function CenteredCard({ children }: { children: React.ReactNode }) {
  return (
    <main className="min-h-screen flex items-center justify-center p-6 bg-gray-50">
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 w-full max-w-md p-6">
        {children}
      </div>
    </main>
  );
}
