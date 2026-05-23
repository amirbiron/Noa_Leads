"use client";

import { useEffect, useState } from "react";
import { X } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { ClosureReason } from "@/lib/types";

// 7 סיבות סגירה לפי האפיון. closure_reason חובה רק כשסוגרים כ-LOST.
const CLOSURE_REASONS: { value: ClosureReason; label: string }[] = [
  { value: "no_response", label: "אין מענה" },
  { value: "not_relevant", label: "לא רלוונטי" },
  { value: "price", label: "מחיר" },
  { value: "timing", label: "תזמון" },
  { value: "went_with_other", label: "בחר בספק אחר" },
  { value: "duplicate", label: "כפילות" },
  { value: "other", label: "אחר" },
];

interface Props {
  leadId: string;
  open: boolean;
  onClose: () => void;
  onClosed: () => void;
}

export function CloseLeadModal({ leadId, open, onClose, onClosed }: Props) {
  const [target, setTarget] = useState<"WON" | "LOST" | "ARCHIVED">("WON");
  const [reason, setReason] = useState<ClosureReason>("no_response");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // איפוס מצב בכל פתיחה / החלפת ליד — מונע ערכים ישנים מסשן קודם
  useEffect(() => {
    if (!open) return;
    setTarget("WON");
    setReason("no_response");
    setNote("");
    setBusy(false);
    setError(null);
  }, [open, leadId]);

  if (!open) return null;

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      await api.closeLead(leadId, {
        target_status: target,
        closure_reason: target === "LOST" ? reason : undefined,
        note: note.trim() || undefined,
      });
      onClosed();
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "שגיאה בסגירה");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 bg-black/40 flex items-end sm:items-center justify-center">
      <div className="bg-white w-full sm:max-w-md sm:rounded-2xl rounded-t-2xl shadow-xl">
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100">
          <h2 className="font-semibold">סגירת ליד</h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600"
            aria-label="סגירה"
          >
            <X size={20} />
          </button>
        </div>

        <div className="p-4 space-y-4">
          {/* בחירת סטטוס יעד — שלוש אפשרויות */}
          <div className="grid grid-cols-3 gap-2">
            {[
              { v: "WON" as const, label: "עסקה ✓" },
              { v: "LOST" as const, label: "לא נסגרה" },
              { v: "ARCHIVED" as const, label: "ארכיון" },
            ].map((opt) => (
              <button
                key={opt.v}
                onClick={() => setTarget(opt.v)}
                className={`py-2.5 rounded-lg text-sm font-medium border ${
                  target === opt.v
                    ? "bg-gray-900 text-white border-gray-900"
                    : "bg-white text-gray-700 border-gray-200"
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>

          {/* סיבה — רק ל-LOST */}
          {target === "LOST" && (
            <label className="block">
              <div className="text-sm font-medium text-gray-700 mb-1.5">
                סיבה
              </div>
              <select
                value={reason}
                onChange={(e) => setReason(e.target.value as ClosureReason)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-base focus:border-gray-900 focus:outline-none"
              >
                {CLOSURE_REASONS.map((r) => (
                  <option key={r.value} value={r.value}>
                    {r.label}
                  </option>
                ))}
              </select>
            </label>
          )}

          <label className="block">
            <div className="text-sm font-medium text-gray-700 mb-1.5">
              הערה (אופציונלי)
            </div>
            <textarea
              value={note}
              onChange={(e) => setNote(e.target.value)}
              rows={2}
              placeholder="לדוגמה: רצה לחזור בקיץ הבא"
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-gray-900 focus:outline-none"
            />
          </label>

          {error && (
            <div className="text-sm text-state-red bg-state-red/10 rounded-lg px-3 py-2">
              {error}
            </div>
          )}

          <button
            onClick={submit}
            disabled={busy}
            className="w-full rounded-lg bg-gray-900 text-white py-3 font-medium disabled:opacity-50"
          >
            {busy ? "סוגרת…" : "סגירת ליד"}
          </button>
        </div>
      </div>
    </div>
  );
}
