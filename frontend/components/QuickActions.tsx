"use client";

import { useState } from "react";
import { api, ApiError } from "@/lib/api";

// 6 צ'יפים לסיכום שיחה (לפי האפיון).
// כל צ'יפ מבצע action ב-backend ומעדכן את הליד.
const CHIPS: { label: string; action: string }[] = [
  { label: "אין מענה", action: "log_call_no_answer" },
  { label: "סיכמתי שיחה", action: "log_call_completed" },
  { label: "שלחתי תבנית", action: "mark_template_sent" },
  { label: "שלחתי הצעה", action: "mark_proposal_sent" },
  { label: "הוסיפי הערה", action: "add_internal_note" },
  { label: "הודעה נכנסת", action: "log_inbound_message" },
];

export function QuickActions({
  leadId,
  onActionDone,
}: {
  leadId: string;
  onActionDone: () => void;
}) {
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [noteText, setNoteText] = useState("");
  const [noteOpen, setNoteOpen] = useState(false);

  async function run(action: string, payload: { content?: string } = {}) {
    setBusy(action);
    setError(null);
    try {
      await api.performAction(leadId, action, payload);
      onActionDone();
      setNoteOpen(false);
      setNoteText("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "שגיאה בביצוע הפעולה");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        {CHIPS.map((chip) => (
          <button
            key={chip.action}
            disabled={busy !== null}
            onClick={() => {
              if (chip.action === "add_internal_note") {
                setNoteOpen(true);
              } else {
                void run(chip.action);
              }
            }}
            className="px-3 py-2 rounded-full border border-gray-300 bg-white text-sm font-medium active:bg-gray-100 disabled:opacity-50"
          >
            {busy === chip.action ? "…" : chip.label}
          </button>
        ))}
      </div>

      {noteOpen && (
        <div className="bg-white rounded-lg border border-gray-200 p-3 space-y-2">
          <textarea
            value={noteText}
            onChange={(e) => setNoteText(e.target.value)}
            rows={3}
            placeholder="הערה פנימית — לא נשלח ללקוח."
            className="w-full text-sm border border-gray-200 rounded-md px-2 py-1.5 focus:outline-none focus:border-gray-900"
          />
          <div className="flex justify-end gap-2">
            <button
              onClick={() => {
                setNoteOpen(false);
                setNoteText("");
              }}
              className="text-sm text-gray-500"
            >
              ביטול
            </button>
            <button
              disabled={!noteText.trim() || busy !== null}
              onClick={() => run("add_internal_note", { content: noteText.trim() })}
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
