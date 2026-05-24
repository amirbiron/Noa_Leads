"use client";

import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { QuickActionChip } from "@/lib/types";

// צ'יפים לסיכום שיחה — נטענים מ-API (editable מ-/settings).
// chip.requires_content=true → פתיחת textarea לטקסט חופשי לפני שליחה
// (כמו "הוסיפי הערה"). אחרת — קליק ישיר מפעיל action.
export function QuickActions({
  leadId,
  onActionDone,
}: {
  leadId: string;
  onActionDone: () => void;
}) {
  const [chips, setChips] = useState<QuickActionChip[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [contentText, setContentText] = useState("");
  const [contentChip, setContentChip] = useState<QuickActionChip | null>(null);

  useEffect(() => {
    api
      .listChips(true)
      .then(setChips)
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : "שגיאה בטעינת צ'יפים"),
      );
  }, []);

  async function run(
    action: string,
    payload: { content?: string } = {},
  ) {
    setBusy(action);
    setError(null);
    try {
      await api.performAction(leadId, action, payload);
      onActionDone();
      setContentChip(null);
      setContentText("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "שגיאה בביצוע הפעולה");
    } finally {
      setBusy(null);
    }
  }

  if (chips.length === 0 && !error) {
    return null;  // אין צ'יפים פעילים — לא להציג כלל
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        {chips.map((chip) => (
          <button
            key={chip.id}
            disabled={busy !== null}
            onClick={() => {
              if (chip.requires_content) {
                setContentChip(chip);
              } else {
                void run(chip.action_type);
              }
            }}
            className="px-3 py-2 rounded-full border border-gray-300 bg-white text-sm font-medium active:bg-gray-100 disabled:opacity-50"
          >
            {busy === chip.action_type ? "…" : chip.label}
          </button>
        ))}
      </div>

      {contentChip && (
        <div className="bg-white rounded-lg border border-gray-200 p-3 space-y-2">
          <textarea
            value={contentText}
            onChange={(e) => setContentText(e.target.value)}
            rows={3}
            placeholder="טקסט חופשי (לא נשלח ללקוח)."
            className="w-full text-sm border border-gray-200 rounded-md px-2 py-1.5 focus:outline-none focus:border-gray-900"
          />
          <div className="flex justify-end gap-2">
            <button
              onClick={() => {
                setContentChip(null);
                setContentText("");
              }}
              className="text-sm text-gray-500"
            >
              ביטול
            </button>
            <button
              disabled={!contentText.trim() || busy !== null}
              onClick={() =>
                run(contentChip.action_type, {
                  content: contentText.trim(),
                })
              }
              className="text-sm bg-gray-900 text-white px-3 py-1.5 rounded-md disabled:opacity-50"
            >
              שמירה
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
  );
}
