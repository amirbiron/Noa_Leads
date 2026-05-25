"use client";

import { useEffect, useState } from "react";
import { X } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { ClosureReason, Lead, ServiceRate } from "@/lib/types";

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

// regex לולידציית מספר חיובי עם עד 2 ספרות עשרוניות.
// תואם ל-decimal_places=2 ב-Pydantic backend (Numeric(10,2) / Numeric(6,2)).
// parseFloat("12abc") מחזיר 12, לכן regex הכרחי לפני הפרסור.
const NUMERIC_RE = /^\d+(\.\d{1,2})?$/;

function defaultsFromRate(
  rate: ServiceRate | undefined,
): { price: string; hours: string } {
  if (!rate) return { price: "", hours: "" };
  return {
    price: rate.default_price !== null ? String(rate.default_price) : "",
    hours: rate.total_hours !== null ? String(rate.total_hours) : "",
  };
}

interface Props {
  lead: Lead;
  open: boolean;
  onClose: () => void;
  onClosed: () => void;
}

export function CloseLeadModal({ lead, open, onClose, onClosed }: Props) {
  const [target, setTarget] = useState<"WON" | "LOST" | "ARCHIVED">("WON");
  const [reason, setReason] = useState<ClosureReason>("no_response");
  const [note, setNote] = useState("");
  const [closedValue, setClosedValue] = useState("");
  const [actualHours, setActualHours] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // התעריפים נטענים פעם אחת ב-mount של המודאל מ-/settings/service-rates.
  // אם נועה עורכת מחיר ב-/settings/rates, הסגירה הבאה תראה את הערך החדש
  // (כל פתיחה של עמוד הליד מ-mount-ת את המודאל מחדש).
  // null = עוד לא נטען (defaults יישארו ריקים בפתיחה); [] = נטען אבל כשל.
  const [rates, setRates] = useState<ServiceRate[] | null>(null);

  useEffect(() => {
    api
      .listServiceRates()
      .then(setRates)
      .catch(() => setRates([])); // fail silent — נועה תזין ידנית
  }, []);

  // איפוס מלא של הטופס בכל פתיחה — דורס קלט קודם (זה התרחיש הצפוי
  // כשפותחים מחדש). לא תלוי ב-rates — ערכי ברירת מחדל יתמלאו ב-effect
  // הבא ברגע שיהיו זמינים.
  useEffect(() => {
    if (!open) return;
    setTarget("WON");
    setReason("no_response");
    setNote("");
    setClosedValue("");
    setActualHours("");
    setBusy(false);
    setError(null);
  }, [open, lead.id, lead.service_subtype]);

  // הצבת defaults מ-rates: ברגע שrates זמינים *ו* המודאל פתוח, ממלאים
  // את closedValue/actualHours רק אם הם ריקים. כך נשמרים גם:
  // (א) ערכי defaults כשrates מגיעים אחרי הפתיחה,
  // (ב) קלט של נועה אם היא כבר התחילה להקליד.
  useEffect(() => {
    if (!open || !rates) return;
    // filter על is_active: ה-UI של /settings/rates מתאר "תעריף פעיל
    // (יוצע ב-CloseLeadModal)". תעריף שנועה ביטלה לא צריך לזרום ל-defaults.
    const subtypeMatch = rates.find(
      (r) => r.service_subtype === lead.service_subtype && r.is_active,
    );
    const defaults = defaultsFromRate(subtypeMatch);
    setClosedValue((prev) => (prev === "" ? defaults.price : prev));
    setActualHours((prev) => (prev === "" ? defaults.hours : prev));
  }, [open, lead.id, lead.service_subtype, rates]);

  const hourlyRate =
    closedValue &&
    actualHours &&
    NUMERIC_RE.test(closedValue) &&
    NUMERIC_RE.test(actualHours) &&
    parseFloat(actualHours) > 0
      ? Math.round(parseFloat(closedValue) / parseFloat(actualHours))
      : null;

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      let value: number | null = null;
      let hours: number | null = null;
      if (target === "WON") {
        if (closedValue.trim()) {
          if (!NUMERIC_RE.test(closedValue.trim())) {
            throw new Error("שווי לא תקין");
          }
          const parsed = parseFloat(closedValue);
          // NaN/Infinity check לפי כלל 4 ב-CLAUDE.md — NUMERIC_RE כבר חוסם
          // אבל double-guard מונע הפתעות אם הקלט מגיע ממקור עתידי אחר.
          if (!Number.isFinite(parsed)) {
            throw new Error("שווי לא תקין");
          }
          value = parsed;
        }
        if (actualHours.trim()) {
          if (!NUMERIC_RE.test(actualHours.trim())) {
            throw new Error("מספר שעות לא תקין");
          }
          const parsed = parseFloat(actualHours);
          if (!Number.isFinite(parsed)) {
            throw new Error("מספר שעות לא תקין");
          }
          hours = parsed;
        }
      }
      await api.closeLead(lead.id, {
        target_status: target,
        closure_reason: target === "LOST" ? reason : undefined,
        note: note.trim() || undefined,
        closed_value: value,
        actual_hours: hours,
      });
      onClosed();
      onClose();
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else if (err instanceof Error) setError(err.message);
      else setError("שגיאה בסגירה");
    } finally {
      setBusy(false);
    }
  }

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 bg-black/40 flex items-end sm:items-center justify-center">
      <div className="bg-white w-full sm:max-w-md sm:rounded-2xl rounded-t-2xl shadow-xl max-h-[95dvh] flex flex-col">
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100 shrink-0">
          <h2 className="font-semibold">סגירת ליד</h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600"
            aria-label="סגירה"
          >
            <X size={20} />
          </button>
        </div>

        <div className="overflow-y-auto p-4 space-y-4">
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

          {/* כלכלת ה-deal — רק ל-WON */}
          {target === "WON" && (
            <div className="space-y-3 bg-gray-50 rounded-lg p-3 border border-gray-100">
              <div className="text-xs text-gray-500">
                ערך הסגירה — לחישוב רווחיות בתובנות השבועיות. ניתן להשאיר ריק.
              </div>
              <div className="grid grid-cols-2 gap-3">
                <label className="block">
                  <div className="text-sm font-medium text-gray-700 mb-1.5">
                    שווי (₪)
                  </div>
                  <input
                    type="text"
                    inputMode="decimal"
                    value={closedValue}
                    onChange={(e) => setClosedValue(e.target.value)}
                    placeholder="0"
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 text-base focus:border-gray-900 focus:outline-none"
                  />
                </label>
                <label className="block">
                  <div className="text-sm font-medium text-gray-700 mb-1.5">
                    שעות בפועל
                  </div>
                  <input
                    type="text"
                    inputMode="decimal"
                    value={actualHours}
                    onChange={(e) => setActualHours(e.target.value)}
                    placeholder="0"
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 text-base focus:border-gray-900 focus:outline-none"
                  />
                </label>
              </div>
              {hourlyRate !== null && (
                <div className="text-sm text-state-green bg-state-green/10 rounded-lg px-3 py-2 font-medium">
                  ≈ {hourlyRate.toLocaleString("he-IL")} ₪/שעה
                </div>
              )}
            </div>
          )}

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
        </div>

        <div className="border-t border-gray-100 p-3 shrink-0">
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
