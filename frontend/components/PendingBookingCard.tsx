"use client";

import { useState } from "react";
import { Calendar, CheckCircle2, XCircle } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { BookingRead } from "@/lib/types";

const ISRAEL_TZ = "Asia/Jerusalem";

function slotLabel(start: string, end: string): string {
  const s = new Date(start).toLocaleString("he-IL", {
    weekday: "long",
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: ISRAEL_TZ,
  });
  const e = new Date(end).toLocaleTimeString("he-IL", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: ISRAEL_TZ,
  });
  return `${s} - ${e}`;
}

// כרטיס bookings ממתינים — מוצג בראש דף הליד כשהליד ב-BOOKING_PENDING.
// 2 פעולות (אשרי / דחי) קרובות לאצבע, ב-confirm לפני דחייה (פעולה הפיכה
// רק על ידי בקשה חדשה מהליד).
export function PendingBookingCard({
  booking,
  onChanged,
}: {
  booking: BookingRead;
  onChanged: () => void | Promise<void>;
}) {
  const [submitting, setSubmitting] = useState<"approve" | "reject" | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);

  async function handleApprove() {
    setError(null);
    setSubmitting("approve");
    try {
      await api.approveBooking(booking.id);
      await onChanged();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "שגיאה באישור");
    } finally {
      setSubmitting(null);
    }
  }

  async function handleReject() {
    if (!confirm("לדחות את בקשת הפגישה? הליד יחזור לסטטוס 'בטיפול'.")) return;
    setError(null);
    setSubmitting("reject");
    try {
      await api.rejectBooking(booking.id);
      await onChanged();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "שגיאה בדחייה");
    } finally {
      setSubmitting(null);
    }
  }

  const busy = submitting !== null;

  return (
    <div className="bg-state-orange/10 border border-state-orange/40 rounded-xl p-4">
      <div className="flex items-start gap-2 mb-2">
        <Calendar size={18} className="text-state-orange mt-0.5" aria-hidden />
        <div className="text-sm font-semibold text-state-orange">
          בקשת פגישה ממתינה לאישור
        </div>
      </div>
      <div className="text-sm text-gray-800 mb-3">
        {slotLabel(booking.requested_slot_start, booking.requested_slot_end)}
      </div>

      {error && (
        <div className="text-sm text-state-red bg-state-red/10 rounded-lg px-3 py-2 mb-2">
          {error}
        </div>
      )}

      <div className="grid grid-cols-2 gap-2">
        <button
          onClick={handleApprove}
          disabled={busy}
          className="rounded-lg bg-state-green text-white py-2.5 text-sm font-medium flex items-center justify-center gap-1.5 disabled:opacity-50"
        >
          <CheckCircle2 size={16} aria-hidden />
          {submitting === "approve" ? "מאשרת…" : "אישור"}
        </button>
        <button
          onClick={handleReject}
          disabled={busy}
          className="rounded-lg bg-white border border-state-red/40 text-state-red py-2.5 text-sm font-medium flex items-center justify-center gap-1.5 disabled:opacity-50"
        >
          <XCircle size={16} aria-hidden />
          {submitting === "reject" ? "דוחה…" : "דחייה"}
        </button>
      </div>
      <div className="text-xs text-gray-500 text-center mt-2">
        אישור יוצר אירוע ביומן Google של נועה.
      </div>
    </div>
  );
}
