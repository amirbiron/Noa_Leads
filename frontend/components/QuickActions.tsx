"use client";

import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { labelTaskType } from "@/lib/hebrew";
import type { Lead, QuickActionChip } from "@/lib/types";

// צ'יפים לסיכום שיחה — Spec v2.1 §16.4.
// כל קליק קורא ל-/leads/{lead_id}/apply-chip/{chip_id} שמבצע את 4 הפעולות
// אטומית: status, waiting_on, יצירת task, activity. אין יותר מסכי ביניים
// (textarea / mark_proposal_sent modal) — הצ'יפ הוא declarative.
//
// מציגים רק chips ש-target_status מאוכלס (אחרת אי אפשר לקרוא ל-apply).
// אחרי הצלחה — toast קצר עם המשמעות של הפולואפ שנוצר (UX educator).

const TOAST_DURATION_MS = 4500;

function pluralizeDays(days: number): string {
  if (days === 1) return "מחר";
  if (days === 2) return "מחרתיים";
  if (days === 30) return "בעוד חודש";
  if (days === 60) return "בעוד 60 יום";
  return `בעוד ${days} ימים`;
}

function toastMessage(chip: QuickActionChip): string {
  // chip.followup_task_type ו-auto_followup_days מובטחים non-null אחרי
  // הפילטר ב-useEffect.
  const when = pluralizeDays(chip.auto_followup_days!);
  const action = labelTaskType(chip.followup_task_type!);
  return `${action} — תזכורת תיווצר ${when}`;
}

export function QuickActions({
  lead,
  onActionDone,
}: {
  lead: Lead;
  onActionDone: () => void;
}) {
  const [chips, setChips] = useState<QuickActionChip[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  useEffect(() => {
    api
      .listChips(true)
      .then((data) =>
        // סינון: רק chips ש-4 השדות הסמנטיים שלהם מאוכלסים.
        // צ'יפ ללא target_status / waiting_on / followup_task_type / days
        // לא יודע מה לעשות בקליק. ייערך דרך /settings/chips.
        setChips(
          data.filter(
            (c) =>
              c.target_status !== null &&
              c.waiting_on !== null &&
              c.followup_task_type !== null &&
              c.auto_followup_days !== null,
          ),
        ),
      )
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : "שגיאה בטעינת צ'יפים"),
      );
  }, []);

  // ה-toast נעלם אוטומטית אחרי TOAST_DURATION_MS. ה-cleanup חיוני —
  // אחרת לחיצה חוזרת תרשום setTimeout כפול.
  useEffect(() => {
    if (toast === null) return;
    const t = setTimeout(() => setToast(null), TOAST_DURATION_MS);
    return () => clearTimeout(t);
  }, [toast]);

  async function applyChip(chip: QuickActionChip) {
    setBusy(chip.id);
    setError(null);
    try {
      await api.applyChip(lead.id, chip.id);
      setToast(toastMessage(chip));
      onActionDone();
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "שגיאה בהפעלת הצ'יפ",
      );
    } finally {
      setBusy(null);
    }
  }

  if (chips.length === 0 && !error) {
    return null;
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        {chips.map((chip) => (
          <button
            key={chip.id}
            disabled={busy !== null}
            onClick={() => void applyChip(chip)}
            className="px-3 py-2 rounded-full border border-gray-300 bg-white text-sm font-medium active:bg-gray-100 disabled:opacity-50"
          >
            {busy === chip.id ? "…" : chip.label}
          </button>
        ))}
      </div>

      {error && (
        <div className="text-sm text-state-red bg-state-red/10 rounded-lg px-3 py-2">
          {error}
        </div>
      )}

      {/* Toast: לתחתית המסך, מעל ה-BottomNav (z-30 שלו). aria-live כדי
          שקוראי מסך יקראו את ההודעה. role=status — לא מפריע. */}
      {toast && (
        <div
          role="status"
          aria-live="polite"
          className="fixed inset-x-0 bottom-20 z-40 flex justify-center pointer-events-none"
        >
          <div className="bg-gray-900 text-white text-sm rounded-full px-4 py-2 shadow-lg max-w-[90vw] text-center pointer-events-auto">
            {toast}
          </div>
        </div>
      )}
    </div>
  );
}
