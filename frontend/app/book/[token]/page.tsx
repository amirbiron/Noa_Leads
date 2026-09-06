"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "next/navigation";
import {
  AlertCircle,
  Calendar,
  CheckCircle2,
  ChevronDown,
  Clock,
  Info,
} from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { toIsraelISODate } from "@/lib/date";
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

// formatDate היה wrapper מקומי; הוחלף ב-toIsraelISODate המשותף ב-
// `lib/date.ts`. הוא משתמש באותו `en-CA` עם options מפורשות (year/
// month/day) — כך שהפלט יציב לפורמט YYYY-MM-DD בכל הדפדפנים, ללא
// חשש מ-CLDR defaults שעלולים להחזיר M/d/yyyy.
const formatDate = toIsraelISODate;

// ===== עזרי תאריך לגריד החודשי =====
// כל יום נבנה כ-12:00 UTC. בישראל (UTC+2/+3) זה תמיד אותו תאריך קלנדרי,
// כך שהגריד זהה לחישוב של השרת גם כשהמכשיר מוגדר לאזור זמן אחר. בניית
// `new Date()` מקומי הייתה יכולה להזיז את היום הראשון ביום שלם.
function dateAtNoonUTC(year: number, month: number, day: number): Date {
  return new Date(Date.UTC(year, month - 1, day, 12));
}

function parseISODate(iso: string): { year: number; month: number; day: number } {
  const [year, month, day] = iso.split("-").map(Number);
  return { year, month, day };
}

// יום 0 של החודש הבא = היום האחרון של החודש המבוקש.
function daysInMonth(year: number, month: number): number {
  return new Date(Date.UTC(year, month, 0)).getUTCDate();
}

function monthLabel(year: number, month: number): string {
  return dateAtNoonUTC(year, month, 1).toLocaleDateString("he-IL", {
    month: "long",
    timeZone: ISRAEL_TZ,
  });
}

function monthKeyOf(iso: string): string {
  const { year, month } = parseISODate(iso);
  return `${year}-${month}`;
}

// חודש בחירה אחד בגריד: התוויות שלו והטווח לשליפה מהשרת.
type BookingMonth = {
  key: string;
  label: string;
  dates: Date[];
  from: string;
  to: string;
};

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
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // זמינות נשמרת פר-חודש. שגיאה וטעינה גם הן פר-חודש: כישלון בטעינת
  // החודש הבא לא צריך למחוק את החודש הנוכחי שכבר נטען בהצלחה.
  //
  // ההפרדה בין "אין סלוטים פנויים" (יום עמוס לגיטימי) לבין "ה-fetch נכשל"
  // נשמרת — אחרת הלקוח רואה "אין סלוטים" ומסיק שאין מועדים כלל בחודש.
  const [monthAvailability, setMonthAvailability] = useState<
    Record<string, AvailabilityResponse>
  >({});
  const [monthLoading, setMonthLoading] = useState<Record<string, boolean>>({});
  const [monthError, setMonthError] = useState<Record<string, string | null>>({});
  // כמה חודשים פתוחים בגריד. מתחילים בחודש הנוכחי בלבד; הכפתור פותח
  // את החודש הבא, שהוא גם הסוף — אין חודש שלישי.
  const [openMonthCount, setOpenMonthCount] = useState(1);

  // חודשי הבחירה נגזרים מ-`info.today` ומ-`info.booking_horizon_end` —
  // שני ערכים שהשרת חישב בשעון ישראל. כך הגריד מתאר בדיוק את מה שהשרת
  // מוכן לקבל, ולא את מה ששעון המכשיר מנחש. הלולאה על החודשים כללית
  // בכוונה: אם האופק בשרת ישתנה אי-פעם, ה-UI יעקוב בלי שינוי קוד.
  const months = useMemo<BookingMonth[]>(() => {
    if (!info) return [];
    const today = parseISODate(info.today);
    const horizon = parseISODate(info.booking_horizon_end);
    const result: BookingMonth[] = [];
    let year = today.year;
    let month = today.month;
    while (year < horizon.year || (year === horizon.year && month <= horizon.month)) {
      const isFirstMonth = year === today.year && month === today.month;
      const isLastMonth = year === horizon.year && month === horizon.month;
      const fromDay = isFirstMonth ? today.day : 1;
      const toDay = isLastMonth ? horizon.day : daysInMonth(year, month);
      const dates: Date[] = [];
      for (let day = fromDay; day <= toDay; day++) {
        dates.push(dateAtNoonUTC(year, month, day));
      }
      if (dates.length > 0) {
        result.push({
          key: `${year}-${month}`,
          label: monthLabel(year, month),
          dates,
          from: formatDate(dates[0]),
          to: formatDate(dates[dates.length - 1]),
        });
      }
      month += 1;
      if (month > 12) {
        month = 1;
        year += 1;
      }
    }
    return result;
  }, [info]);

  const visibleMonths = useMemo(
    () => months.slice(0, openMonthCount),
    [months, openMonthCount],
  );
  const nextMonth = months[openMonthCount] ?? null;
  // היום האחרון שאפשר לקבוע בו — לתווית "אפשר לקבוע פגישה עד X".
  const lastBookableDate = useMemo(() => {
    if (!info) return null;
    const { year, month, day } = parseISODate(info.booking_horizon_end);
    return dateAtNoonUTC(year, month, day);
  }, [info]);

  const [selectedDate, setSelectedDate] = useState<string>("");
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

  // מונה בקשות פר-חודש — "הבקשה האחרונה מנצחת". חודשים *שונים* לא
  // יכולים לדרוס זה את זה (כל תגובה נכתבת למפתח שלה), אבל שתי בקשות
  // לאותו חודש כן: לחיצה כפולה על "נסי שוב" ברשת חלשה יכולה להחזיר
  // קודם את ההצלחה ואז את הכישלון הישן, והלקוח היה רואה שגיאה על חודש
  // שנטען בסדר. תגובה שאינה של הבקשה האחרונה נזרקת בשקט.
  const monthRequestIdRef = useRef<Record<string, number>>({});

  // טעינת חודש בודד.
  const fetchMonth = useMemo(
    () => async (month: BookingMonth) => {
      if (!token) return;
      const requestId = (monthRequestIdRef.current[month.key] ?? 0) + 1;
      monthRequestIdRef.current[month.key] = requestId;
      const isStale = () => monthRequestIdRef.current[month.key] !== requestId;

      setMonthLoading((prev) => ({ ...prev, [month.key]: true }));
      setMonthError((prev) => ({ ...prev, [month.key]: null }));
      try {
        const result = await api.getBookingAvailability(
          token,
          month.from,
          month.to,
        );
        if (isStale()) return;
        setMonthAvailability((prev) => ({ ...prev, [month.key]: result }));
      } catch (err) {
        if (isStale()) return;
        setMonthAvailability((prev) => {
          const next = { ...prev };
          delete next[month.key];
          return next;
        });
        setMonthError((prev) => ({
          ...prev,
          [month.key]: err instanceof ApiError ? err.message : "שגיאה בטעינת זמינות",
        }));
      } finally {
        // רק הבקשה הפעילה מכבה את מצב הטעינה; בקשה stale מותירה אותו
        // דולק עבור הבקשה שעדיין רצה.
        if (!isStale()) {
          setMonthLoading((prev) => ({ ...prev, [month.key]: false }));
        }
      }
    },
    [token],
  );

  // טעינה ראשונית: החודש הנוכחי בלבד. החודש הבא נטען רק אם הלקוח
  // פותח אותו — רוב הלקוחות קובעים בחודש הקרוב, ואין טעם בקריאה
  // שנייה ל-FreeBusy בכל כניסה לדף.
  useEffect(() => {
    if (!info || info.has_active_booking) return;
    const first = months[0];
    if (!first) return;
    setSelectedDate((prev) => prev || info.today);
    void fetchMonth(first);
  }, [info, months, fetchMonth]);

  function showNextMonth() {
    if (!nextMonth) return;
    setOpenMonthCount((count) => count + 1);
    if (!monthAvailability[nextMonth.key] && !monthLoading[nextMonth.key]) {
      void fetchMonth(nextMonth);
    }
  }

  // חיפוש יום בכל החודשים שנטענו — התאריך הנבחר יכול להיות בכל אחד מהם.
  const dayLookup = useMemo(() => {
    const map = new Map<string, TimeSlot[]>();
    for (const response of Object.values(monthAvailability)) {
      for (const day of response.days) {
        map.set(day.date, day.slots);
      }
    }
    return map;
  }, [monthAvailability]);

  const slotsForSelectedDate = useMemo(
    () => dayLookup.get(selectedDate) ?? [],
    [dayLookup, selectedDate],
  );

  // מצב הטעינה/שגיאה של החודש שאליו שייך התאריך הנבחר.
  const selectedMonthKey = selectedDate ? monthKeyOf(selectedDate) : "";
  const selectedMonthLoading = !!monthLoading[selectedMonthKey];
  const selectedMonthError = monthError[selectedMonthKey] ?? null;
  const selectedMonth = months.find((m) => m.key === selectedMonthKey) ?? null;

  // ההערה על סנכרון היומן מגיעה מכל חודש שנטען — הדגל זהה לכולם.
  const includesGoogleBusy = useMemo(() => {
    const loaded = Object.values(monthAvailability);
    return loaded.length === 0 || loaded.every((r) => r.includes_google_busy);
  }, [monthAvailability]);

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
          <div className="text-lg font-semibold">כבר יש לך בקשת פגישה</div>
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
        {!includesGoogleBusy && (
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
                  const slots = dayLookup.get(key);
                  const hasSlots = (slots?.length ?? 0) > 0;
                  const isSelected = selectedDate === key;
                  const isLoading = !!monthLoading[month.key];
                  const hasError = !!monthError[month.key];
                  return (
                    <button
                      key={key}
                      style={{ gridColumnStart }}
                      onClick={() => {
                        setSelectedDate(key);
                        setSelectedSlot(null);
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
              {submitting ? "שולחת בקשה…" : "אישור בקשת פגישה"}
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
