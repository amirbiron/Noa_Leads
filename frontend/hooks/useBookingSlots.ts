"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { ApiError } from "@/lib/api";
import {
  dateAtNoonUTC,
  daysInMonth,
  formatDate,
  monthKeyOf,
  monthLabel,
  parseISODate,
  type BookingMonth,
} from "@/lib/bookingDates";
import type { AvailabilityResponse, TimeSlot } from "@/lib/types";

/**
 * מנגנון הרשת החודשית של דפי קביעת הפגישה.
 *
 * **למה זה hook משותף ולא קוד בתוך כל דף:** שני מסלולי הקביעה — קישור
 * של ליד וקישור פתוח — חייבים להציג בדיוק את אותם מועדים. הטפסים
 * שלהם שונים בצדק (אחד מבקש שם, השני לא), אבל *מה נחשב מועד פנוי*
 * חייב להיות תשובה אחת. עותק שני של הלוגיקה הזו היה נסחף בשינוי
 * הראשון, ואז רשת אחת הייתה מציעה מועד שהשנייה כבר תפסה.
 *
 * מה שנשאר בפנים: חישוב החודשים מ-`today`/`horizonEnd` של השרת, טעינה
 * פר-חודש עם הגנה מפני תגובה מיושנת, ומיפוי יום ← סלוטים.
 */
export function useBookingSlots({
  today,
  horizonEnd,
  loadAvailability,
  enabled,
}: {
  /** התאריך של היום, בשעון ישראל, **כפי שהשרת חישב אותו**. */
  today: string | null;
  /** היום האחרון שאפשר לקבוע בו, גם הוא מהשרת. */
  horizonEnd: string | null;
  loadAvailability: (from: string, to: string) => Promise<AvailabilityResponse>;
  /** כשהוא false הטעינה הראשונית לא רצה (למשל כשהליד הגיע לתקרה). */
  enabled: boolean;
}) {
  // זמינות, טעינה ושגיאה — כולן פר-חודש. כישלון בטעינת החודש הבא לא
  // צריך למחוק חודש שכבר נטען בהצלחה, וחשוב מכך: "אין סלוטים פנויים"
  // (יום עמוס לגיטימי) ו-"ה-fetch נכשל" חייבים להישאר נפרדים, אחרת
  // הלקוח רואה "אין מועדים" ומסיק שהחודש סגור.
  const [monthAvailability, setMonthAvailability] = useState<
    Record<string, AvailabilityResponse>
  >({});
  const [monthLoading, setMonthLoading] = useState<Record<string, boolean>>({});
  const [monthError, setMonthError] = useState<Record<string, string | null>>(
    {},
  );
  const [openMonthCount, setOpenMonthCount] = useState(1);
  const [selectedDate, setSelectedDate] = useState<string>("");

  // החודשים נגזרים משני ערכים שהשרת חישב בשעון ישראל, ולא משעון
  // המכשיר. כך הגריד מתאר בדיוק את מה שהשרת מוכן לקבל. הלולאה כללית
  // בכוונה: אם האופק בשרת ישתנה, ה-UI יעקוב בלי שינוי קוד.
  const months = useMemo<BookingMonth[]>(() => {
    if (!today || !horizonEnd) return [];
    const start = parseISODate(today);
    const horizon = parseISODate(horizonEnd);
    const result: BookingMonth[] = [];
    let year = start.year;
    let month = start.month;
    while (
      year < horizon.year ||
      (year === horizon.year && month <= horizon.month)
    ) {
      const isFirstMonth = year === start.year && month === start.month;
      const isLastMonth = year === horizon.year && month === horizon.month;
      const fromDay = isFirstMonth ? start.day : 1;
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
  }, [today, horizonEnd]);

  const visibleMonths = useMemo(
    () => months.slice(0, openMonthCount),
    [months, openMonthCount],
  );
  const nextMonth = months[openMonthCount] ?? null;

  const lastBookableDate = useMemo(() => {
    if (!horizonEnd) return null;
    const { year, month, day } = parseISODate(horizonEnd);
    return dateAtNoonUTC(year, month, day);
  }, [horizonEnd]);

  // מונה בקשות פר-חודש — "הבקשה האחרונה מנצחת". חודשים שונים לא
  // דורסים זה את זה (כל תגובה נכתבת למפתח שלה), אבל שתי בקשות לאותו
  // חודש כן: לחיצה כפולה על "נסי שוב" ברשת חלשה יכולה להחזיר קודם את
  // ההצלחה ואז את הכישלון הישן, והלקוח היה רואה שגיאה על חודש תקין.
  const monthRequestIdRef = useRef<Record<string, number>>({});
  // `loadAvailability` נוצרת מחדש בכל render אצל הקורא. שמירה ב-ref
  // מונעת מ-`fetchMonth` להשתנות בכל render, ואיתה לולאת useEffect.
  //
  // ומה אם מקור הזמינות עצמו מתחלף (token אחר)? ה-hook לא מאפס את
  // עצמו, ובכוונה: Next מחליף את כל עץ ה-React כשערך של segment דינמי
  // משתנה, כך שהדף — ואיתו ה-state כאן — נבנה מחדש.
  // מקור: next/dist/client/components/layout-router.js ("state key").
  const loadRef = useRef(loadAvailability);
  loadRef.current = loadAvailability;

  const fetchMonth = useMemo(
    () => async (month: BookingMonth) => {
      const requestId = (monthRequestIdRef.current[month.key] ?? 0) + 1;
      monthRequestIdRef.current[month.key] = requestId;
      const isStale = () => monthRequestIdRef.current[month.key] !== requestId;

      setMonthLoading((prev) => ({ ...prev, [month.key]: true }));
      setMonthError((prev) => ({ ...prev, [month.key]: null }));
      try {
        const result = await loadRef.current(month.from, month.to);
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
          [month.key]:
            err instanceof ApiError ? err.message : "שגיאה בטעינת זמינות",
        }));
      } finally {
        // רק הבקשה הפעילה מכבה את מצב הטעינה; בקשה מיושנת מותירה אותו
        // דולק עבור הבקשה שעדיין רצה.
        if (!isStale()) {
          setMonthLoading((prev) => ({ ...prev, [month.key]: false }));
        }
      }
    },
    [],
  );

  // טעינה ראשונית: החודש הנוכחי בלבד. החודש הבא נטען רק אם הלקוח פותח
  // אותו — רוב הלקוחות קובעים בחודש הקרוב, ואין טעם בקריאה שנייה
  // ל-FreeBusy בכל כניסה לדף.
  useEffect(() => {
    if (!enabled || !today) return;
    const first = months[0];
    if (!first) return;
    setSelectedDate((prev) => prev || today);
    void fetchMonth(first);
  }, [enabled, today, months, fetchMonth]);

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

  const selectedMonthKey = selectedDate ? monthKeyOf(selectedDate) : "";
  const selectedMonth = months.find((m) => m.key === selectedMonthKey) ?? null;

  // ההערה על סנכרון היומן זהה לכל החודשים שנטענו.
  const includesGoogleBusy = useMemo(() => {
    const loaded = Object.values(monthAvailability);
    return loaded.length === 0 || loaded.every((r) => r.includes_google_busy);
  }, [monthAvailability]);

  // אחרי 409 ("הסלוט כבר תפוס. בחרי מועד אחר מהרשימה המעודכנת") —
  // בלי טעינה מחדש "הרשימה המעודכנת" היא הרשימה הישנה, והמועד שנתפס
  // עדיין מוצע: הלקוח לוחץ עליו שוב ומקבל את אותה שגיאה.
  function reloadSelectedMonth() {
    if (selectedMonth) void fetchMonth(selectedMonth);
  }

  return {
    months,
    visibleMonths,
    nextMonth,
    showNextMonth,
    lastBookableDate,
    selectedDate,
    setSelectedDate,
    dayLookup,
    // המפות עצמן, לגריד שמציג מצב פר-יום בתוך כל חודש.
    monthLoading,
    monthError,
    slotsForSelectedDate,
    selectedMonth,
    selectedMonthLoading: !!monthLoading[selectedMonthKey],
    selectedMonthError: monthError[selectedMonthKey] ?? null,
    includesGoogleBusy,
    fetchMonth,
    reloadSelectedMonth,
  };
}

/** מה שה-hook מחזיר — הטיפוס ש-`BookingSlotPicker` מקבל. */
export type BookingSlots = ReturnType<typeof useBookingSlots>;
