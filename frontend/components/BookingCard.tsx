"use client";

import { useState } from "react";
import { Calendar, Phone, MessageSquare, XCircle, AlertTriangle } from "lucide-react";
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

// כרטיס פגישה קבועה, בראש דף הליד.
//
// החליף את PendingBookingCard: אין יותר שלב אישור — הפגישה נקבעת מיד
// כשהליד בוחר מועד. מה שנועה צריכה כאן הוא לראות את הפרטים (מתי,
// באיזה טלפון להשיג, ומה הלקוח כתב) ולבטל אם צריך.
export function BookingCard({
  booking,
  onChanged,
}: {
  booking: BookingRead;
  onChanged: () => void | Promise<void>;
}) {
  const [canceling, setCanceling] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // שורות שנוצרו לפני ביטול שלב האישור. אין להן אירוע ביומן ואין מי
  // שיאשר אותן, ולכן מוצג הסבר קצר במקום להשאיר מסך שנראה תקוע.
  const isLegacyPending = booking.status === "pending_approval";
  const isPast = new Date(booking.requested_slot_end).getTime() < Date.now();

  async function handleCancel() {
    if (!confirm("לבטל את הפגישה? האירוע יימחק גם מיומן Google.")) return;
    setError(null);
    setCanceling(true);
    try {
      await api.cancelBooking(booking.id);
      await onChanged();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "שגיאה בביטול");
    } finally {
      setCanceling(false);
    }
  }

  return (
    <div className="bg-state-green/5 border border-state-green/40 rounded-xl p-4">
      <div className="flex items-start gap-2 mb-2">
        <Calendar size={18} className="text-state-green mt-0.5" aria-hidden />
        <div className="text-sm font-semibold text-gray-900">
          {isPast ? "פגישה שהסתיימה" : "פגישה קבועה"}
        </div>
      </div>

      <div className="text-sm text-gray-800">
        {slotLabel(booking.requested_slot_start, booking.requested_slot_end)}
      </div>

      {booking.contact_phone && (
        <a
          href={`tel:${booking.contact_phone}`}
          className="mt-2 flex items-center gap-1.5 text-sm text-gray-700"
        >
          <Phone size={13} className="shrink-0" aria-hidden />
          {/* bdo מכריח את המספר להיקרא משמאל לימין בתוך משפט עברי —
              אחרת מקפים וסימנים בקצוות מתהפכים. */}
          <bdo dir="ltr">{booking.contact_phone}</bdo>
        </a>
      )}

      {booking.notes && (
        <div className="mt-2 flex items-start gap-1.5 text-sm text-gray-700">
          <MessageSquare size={13} className="mt-0.5 shrink-0" aria-hidden />
          <span className="whitespace-pre-wrap">{booking.notes}</span>
        </div>
      )}

      {isLegacyPending && (
        <div className="mt-3 flex items-start gap-2 bg-state-orange/10 border border-state-orange/30 rounded-lg px-3 py-2 text-xs text-gray-700">
          <AlertTriangle
            size={13}
            className="text-state-orange mt-0.5 shrink-0"
            aria-hidden
          />
          <span>
            בקשה ישנה שהמתינה לאישור. המערכת כבר לא דורשת אישור — אפשר
            לבטל ולשלוח ללקוח קישור לקביעה מחדש.
          </span>
        </div>
      )}

      {error && (
        <div className="text-sm text-state-red bg-state-red/10 rounded-lg px-3 py-2 mt-2">
          {error}
        </div>
      )}

      {!isPast && (
        <>
          <button
            onClick={handleCancel}
            disabled={canceling}
            className="mt-3 w-full rounded-lg bg-white border border-state-red/40 text-state-red py-2.5 text-sm font-medium flex items-center justify-center gap-1.5 disabled:opacity-50"
          >
            <XCircle size={16} aria-hidden />
            {canceling ? "מבטלת…" : "ביטול פגישה"}
          </button>
          <div className="text-xs text-gray-500 text-center mt-2">
            הביטול מוחק את האירוע מיומן Google.
          </div>
        </>
      )}
    </div>
  );
}
