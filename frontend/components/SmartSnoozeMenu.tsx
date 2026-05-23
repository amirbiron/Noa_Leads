"use client";

import { useState } from "react";
import { X } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { SnoozePreset } from "@/lib/types";

// 5 קיצורי הדרך מהאפיון — מטרת ה-snooze היא לא לפתוח טופס תאריך
// בכל פעם. תאריך מותאם נשמר ל-edge cases בלבד.
const PRESETS: { value: SnoozePreset; label: string; hint: string }[] = [
  { value: "today_afternoon", label: "היום אחר הצהריים", hint: "15:00" },
  { value: "tomorrow_morning", label: "מחר בבוקר", hint: "09:00" },
  { value: "sunday_morning", label: "ראשון בבוקר", hint: "ראשון 09:00" },
  { value: "after_holiday", label: "אחרי החג", hint: "יום העבודה הבא" },
];

interface Props {
  taskId: string;
  open: boolean;
  onClose: () => void;
  onSnoozed: () => void;
}

export function SmartSnoozeMenu({ taskId, open, onClose, onSnoozed }: Props) {
  const [busy, setBusy] = useState<SnoozePreset | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [customMode, setCustomMode] = useState(false);
  const [customDate, setCustomDate] = useState("");

  if (!open) return null;

  async function pick(preset: SnoozePreset, customUntil?: string) {
    setBusy(preset);
    setError(null);
    try {
      await api.snoozeTask(taskId, preset, customUntil);
      onSnoozed();
      onClose();
      setCustomMode(false);
      setCustomDate("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "שגיאה בדחיה");
    } finally {
      setBusy(null);
    }
  }

  function submitCustom() {
    if (!customDate) return;
    // datetime-local נשלח ללא TZ. ה-backend מתייחס אליו כ-Asia/Jerusalem
    // (שם נועה נמצאת) — בדיוק מה שהיא הקלידה.
    void pick("custom", customDate);
  }

  return (
    <div className="fixed inset-0 z-50 bg-black/40 flex items-end justify-center">
      <div className="bg-white w-full sm:max-w-md rounded-t-2xl shadow-xl">
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100">
          <h2 className="font-semibold">דחיית משימה</h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600"
            aria-label="סגירה"
          >
            <X size={20} />
          </button>
        </div>

        <div className="p-3 space-y-2">
          {!customMode &&
            PRESETS.map((p) => (
              <button
                key={p.value}
                disabled={busy !== null}
                onClick={() => pick(p.value)}
                className="w-full flex items-center justify-between rounded-lg border border-gray-200 bg-white px-3.5 py-3 active:bg-gray-50 disabled:opacity-50"
              >
                <span className="font-medium text-sm">{p.label}</span>
                <span className="text-xs text-gray-400">{p.hint}</span>
              </button>
            ))}

          {!customMode && (
            <button
              onClick={() => setCustomMode(true)}
              className="w-full text-start rounded-lg border border-dashed border-gray-300 bg-white px-3.5 py-3 text-sm text-gray-600 active:bg-gray-50"
            >
              תאריך מותאם…
            </button>
          )}

          {customMode && (
            <div className="space-y-2">
              <input
                type="datetime-local"
                value={customDate}
                onChange={(e) => setCustomDate(e.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-base focus:border-gray-900 focus:outline-none"
              />
              <div className="flex gap-2">
                <button
                  onClick={() => {
                    setCustomMode(false);
                    setCustomDate("");
                  }}
                  className="flex-1 rounded-lg bg-gray-100 text-gray-700 py-2.5 text-sm font-medium"
                >
                  חזרה
                </button>
                <button
                  onClick={submitCustom}
                  disabled={!customDate || busy !== null}
                  className="flex-1 rounded-lg bg-gray-900 text-white py-2.5 text-sm font-medium disabled:opacity-50"
                >
                  {busy === "custom" ? "דוחה…" : "אישור"}
                </button>
              </div>
            </div>
          )}

          {error && (
            <div className="text-sm text-state-red bg-state-red/10 rounded-lg px-3 py-2">
              {error}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
