"use client";

import { useEffect, useState } from "react";
import { X } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { ProgramType } from "@/lib/types";

// ברירות מחדל לפי האפיון (product-spec.md, "תעריפי ברירת מחדל")
const PROGRAM_DEFAULTS: Record<
  ProgramType,
  { label: string; sessions: number; price: number | null }
> = {
  voice_rehab_8: { label: "שיקום קול (8 מפגשים)", sessions: 8, price: 2400 },
  public_speaking_8: {
    label: "עמידה מול קהל (8 מפגשים)",
    sessions: 8,
    price: 2400,
  },
  stage_arts_4: { label: "אומניות הבמה (3–4 מפגשים)", sessions: 4, price: 7000 },
  production_3months: { label: "ליווי הפקה", sessions: 12, price: 9600 },
  digital_course_12: { label: "קורס דיגיטלי", sessions: 12, price: null },
};

interface Props {
  leadId: string;
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
}

export function AddProgramModal({ leadId, open, onClose, onCreated }: Props) {
  const [type, setType] = useState<ProgramType>("voice_rehab_8");
  const [sessions, setSessions] = useState<number>(8);
  const [price, setPrice] = useState<string>("2400");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // איפוס + עדכון ברירות מחדל בכל פתיחה
  useEffect(() => {
    if (!open) return;
    const def = PROGRAM_DEFAULTS.voice_rehab_8;
    setType("voice_rehab_8");
    setSessions(def.sessions);
    setPrice(def.price?.toString() ?? "");
    setBusy(false);
    setError(null);
  }, [open]);

  // כשנבחר סוג חדש — עדכון ברירות מחדל (אבל לא דריסה אם המשתמשת כבר ערכה)
  function handleTypeChange(newType: ProgramType) {
    setType(newType);
    const def = PROGRAM_DEFAULTS[newType];
    setSessions(def.sessions);
    setPrice(def.price?.toString() ?? "");
  }

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      // ולידציה מחמירה — parseFloat("12abc") מחזיר 12 ולא NaN, אז
      // נדרש regex כדי לחסום קלט חלקית מספרי
      const trimmed = price.trim();
      let priceNum: number | null = null;
      if (trimmed) {
        // עד 2 ספרות עשרוניות (תואם decimal_places=2 ב-Pydantic)
        if (!/^\d+(\.\d{1,2})?$/.test(trimmed)) {
          throw new Error("מחיר חייב להיות מספר חיובי (עד 2 ספרות עשרוניות)");
        }
        priceNum = parseFloat(trimmed);
      }
      await api.createProgram({
        lead_id: leadId,
        program_type: type,
        total_sessions: sessions,
        total_price: priceNum,
      });
      onCreated();
      onClose();
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else if (err instanceof Error) setError(err.message);
      else setError("שגיאה ביצירה");
    } finally {
      setBusy(false);
    }
  }

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 bg-black/40 flex items-end sm:items-center justify-center">
      <div className="bg-white w-full sm:max-w-md sm:rounded-2xl rounded-t-2xl shadow-xl">
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100">
          <h2 className="font-semibold">הוספת תוכנית מתמשכת</h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600"
            aria-label="סגירה"
          >
            <X size={20} />
          </button>
        </div>

        <div className="p-4 space-y-4">
          <label className="block">
            <div className="text-sm font-medium text-gray-700 mb-1.5">
              סוג תוכנית
            </div>
            <select
              value={type}
              onChange={(e) => handleTypeChange(e.target.value as ProgramType)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-base focus:border-gray-900 focus:outline-none"
            >
              {Object.entries(PROGRAM_DEFAULTS).map(([k, v]) => (
                <option key={k} value={k}>
                  {v.label}
                </option>
              ))}
            </select>
          </label>

          <div className="grid grid-cols-2 gap-3">
            <label className="block">
              <div className="text-sm font-medium text-gray-700 mb-1.5">
                סה&quot;כ מפגשים
              </div>
              <input
                type="number"
                min={1}
                max={100}
                value={sessions}
                onChange={(e) => {
                  const parsed = parseInt(e.target.value);
                  const clamped = Number.isNaN(parsed)
                    ? 1
                    : Math.min(100, Math.max(1, parsed));
                  setSessions(clamped);
                }}
                className="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-base focus:border-gray-900 focus:outline-none"
              />
            </label>

            <label className="block">
              <div className="text-sm font-medium text-gray-700 mb-1.5">
                מחיר כולל (₪)
              </div>
              <input
                type="text"
                inputMode="decimal"
                value={price}
                onChange={(e) => setPrice(e.target.value)}
                placeholder="לבירור"
                className="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-base focus:border-gray-900 focus:outline-none"
              />
            </label>
          </div>

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
            {busy ? "יוצרת…" : "יצירת תוכנית"}
          </button>
        </div>
      </div>
    </div>
  );
}
