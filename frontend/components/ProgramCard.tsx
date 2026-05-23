"use client";

import { useState } from "react";
import { CheckCircle2, Minus, Plus, XCircle } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { labelProgramStatus, labelProgramType } from "@/lib/hebrew";
import type { Program } from "@/lib/types";
import { cn } from "@/lib/utils";

// כרטיס תוכנית עם:
// - שם סוג + סטטוס
// - bar התקדמות (completed/total)
// - כפתורי + / - לעדכון מפגשים שבוצעו
// - הצגת תזכורת "תוכנית מתקרבת לסיום" כשנשאר מפגש אחד
export function ProgramCard({
  program,
  onChanged,
}: {
  program: Program;
  onChanged: () => void;
}) {
  const [busy, setBusy] = useState<"inc" | "dec" | "cancel" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const sessionsLeft = program.total_sessions - program.completed_sessions;
  const progress = Math.min(
    100,
    Math.round((program.completed_sessions / program.total_sessions) * 100),
  );
  const isActive = program.status === "active";
  const isNearEnd = isActive && sessionsLeft === 1;
  const isCompleted = program.status === "completed";

  async function increment() {
    setBusy("inc");
    setError(null);
    try {
      await api.updateProgram(program.id, {
        completed_sessions: program.completed_sessions + 1,
      });
      onChanged();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "שגיאה");
    } finally {
      setBusy(null);
    }
  }

  async function decrement() {
    if (program.completed_sessions === 0) return;
    setBusy("dec");
    setError(null);
    try {
      await api.updateProgram(program.id, {
        completed_sessions: program.completed_sessions - 1,
      });
      onChanged();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "שגיאה");
    } finally {
      setBusy(null);
    }
  }

  async function cancel() {
    if (!confirm("לבטל את התוכנית?")) return;
    setBusy("cancel");
    setError(null);
    try {
      await api.cancelProgram(program.id);
      onChanged();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "שגיאה");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div
      className={cn(
        "bg-white rounded-xl border border-gray-200 p-4 space-y-3",
        !isActive && "opacity-75",
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="font-medium text-sm">
            {labelProgramType(program.program_type)}
          </div>
          {!isActive && (
            <div className="text-xs text-gray-500 mt-0.5">
              {labelProgramStatus(program.status)}
            </div>
          )}
        </div>
        {program.total_price && (
          <div className="text-xs text-gray-500 shrink-0">
            {Number(program.total_price).toLocaleString("he-IL")} ₪
          </div>
        )}
      </div>

      {/* Progress bar + מספרים */}
      <div>
        <div className="flex items-baseline justify-between mb-1.5">
          <span className="text-2xl font-semibold tabular-nums">
            {program.completed_sessions}
            <span className="text-gray-300 mx-1">/</span>
            <span className="text-gray-500 text-base">
              {program.total_sessions}
            </span>
          </span>
          <span className="text-xs text-gray-500">מפגשים</span>
        </div>
        <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
          <div
            className={cn(
              "h-full transition-all",
              isCompleted ? "bg-state-green" : "bg-gray-700",
            )}
            style={{ width: `${progress}%` }}
          />
        </div>
      </div>

      {/* התראת קרוב לסיום */}
      {isNearEnd && (
        <div className="flex items-start gap-2 bg-state-orange/10 border border-state-orange/30 rounded-lg px-3 py-2 text-sm">
          <CheckCircle2
            size={16}
            className="text-state-orange mt-0.5 shrink-0"
            aria-hidden
          />
          <div className="text-gray-800">
            <strong>נשאר מפגש אחד.</strong> שווה להציע המשך, תוכנית חדשה,
            או סיכום.
          </div>
        </div>
      )}

      {/* פעולות — רק לתוכנית פעילה */}
      {isActive && (
        <div className="flex items-center gap-2">
          <button
            onClick={decrement}
            disabled={busy !== null || program.completed_sessions === 0}
            aria-label="הפחת מפגש"
            className="w-9 h-9 rounded-lg border border-gray-200 bg-white text-gray-700 disabled:opacity-40 flex items-center justify-center"
          >
            <Minus size={16} aria-hidden />
          </button>
          <button
            onClick={increment}
            disabled={
              busy !== null ||
              program.completed_sessions >= program.total_sessions
            }
            className="flex-1 rounded-lg bg-gray-900 text-white py-2 text-sm font-medium disabled:opacity-50 flex items-center justify-center gap-1.5"
          >
            <Plus size={15} aria-hidden />
            {busy === "inc" ? "מעדכנת…" : "מפגש בוצע"}
          </button>
          <button
            onClick={cancel}
            disabled={busy !== null}
            aria-label="ביטול תוכנית"
            className="w-9 h-9 rounded-lg border border-gray-200 bg-white text-gray-400 hover:text-state-red disabled:opacity-50 flex items-center justify-center"
          >
            <XCircle size={16} aria-hidden />
          </button>
        </div>
      )}

      {error && (
        <div className="text-xs text-state-red bg-state-red/10 rounded px-2 py-1.5">
          {error}
        </div>
      )}
    </div>
  );
}
