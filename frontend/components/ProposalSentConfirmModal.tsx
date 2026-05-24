"use client";

import { useState } from "react";
import { X } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { toWhatsAppDigits } from "@/lib/phone";
import type { Lead } from "@/lib/types";

// מודאל אישור הצעה — תרחיש 2-שלבים לפי phase-2.5-plan.md §7.2:
// 1. נועה לוחצת "שלחי הצעה" → המודאל נפתח.
// 2. אופציה א': "פתח וואטסאפ" — נפתח wa.me, המודאל נשאר פתוח.
// 3. אופציה ב': "כן, ההצעה נשלחה" — קריאת mark_proposal_sent ב-backend
//    (סטטוס → PROPOSAL_SENT, task PROPOSAL_FOLLOWUP נוצר).
// 4. אופציה ג': "ביטול" — סגירה בלי שינוי.
//
// העיקרון: הסטטוס משתנה רק כשנועה מאשרת שהיא באמת שלחה. עקבי עם
// עיקרון "שליחה תמיד ידנית" באפיון.
export function ProposalSentConfirmModal({
  lead,
  open,
  onClose,
  onConfirmed,
}: {
  lead: Lead;
  open: boolean;
  onClose: () => void;
  onConfirmed: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!open) return null;

  const waDigits = toWhatsAppDigits(lead.phone);

  async function confirmSent() {
    setBusy(true);
    setError(null);
    try {
      await api.performAction(lead.id, "mark_proposal_sent");
      onConfirmed();
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "שגיאה");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 bg-black/40 flex items-end sm:items-center justify-center">
      <div className="bg-white w-full sm:max-w-md rounded-t-2xl sm:rounded-2xl shadow-xl">
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100">
          <h2 className="font-semibold">שליחת הצעת מחיר</h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600"
            aria-label="סגירה"
          >
            <X size={20} />
          </button>
        </div>

        <div className="p-4 space-y-3">
          <p className="text-sm text-gray-700">
            פתחי וואטסאפ ושלחי את ההצעה ל{lead.full_name}.
            <br />
            כשסיימת — חזרי לכאן וסמני שההצעה נשלחה.
          </p>

          {waDigits && (
            <a
              href={`https://wa.me/${waDigits}`}
              target="_blank"
              rel="noopener noreferrer"
              className="block w-full text-center bg-state-green text-white rounded-lg py-3 text-sm font-medium"
            >
              פתח וואטסאפ
            </a>
          )}

          {error && (
            <div className="text-sm text-state-red bg-state-red/10 rounded-lg px-3 py-2">
              {error}
            </div>
          )}

          <div className="grid grid-cols-2 gap-2 pt-2">
            <button
              onClick={onClose}
              disabled={busy}
              className="rounded-lg bg-gray-100 text-gray-700 py-2.5 text-sm font-medium disabled:opacity-50"
            >
              ביטול
            </button>
            <button
              onClick={confirmSent}
              disabled={busy}
              className="rounded-lg bg-gray-900 text-white py-2.5 text-sm font-medium disabled:opacity-50"
            >
              {busy ? "מעדכנת…" : "כן, ההצעה נשלחה"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
