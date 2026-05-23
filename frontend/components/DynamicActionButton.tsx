"use client";

import { useState } from "react";
import { ArrowLeft } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { Lead } from "@/lib/types";

// כפתור "מה עכשיו?" — דינמי לפי סטטוס הליד.
// פעולה אחת ראשית גדולה, מובילה לפעולה הטבעית הבאה.
function nextAction(lead: Lead): {
  label: string;
  action: string;
  description?: string;
} | null {
  // לידים סגורים: לא מציגים פעולה ראשית, גם אם preferred_contact=phone.
  // (אחרת היה מופיע "התקשרי" שנופל ב-backend עם InvalidStateTransition).
  if (lead.status === "WON" || lead.status === "LOST" || lead.status === "ARCHIVED") {
    return null;
  }
  // ליד פתוח שמסומן "עדיף טלפון" — כפתור התקשרות גובר על שאר הסטטוסים
  if (lead.preferred_contact === "phone") {
    return { label: "התקשרי", action: "log_call_completed", description: "ולתעד אחרי" };
  }
  switch (lead.status) {
    case "NEW":
      return { label: "שלחי תבנית פתיחה", action: "mark_template_sent" };
    case "IN_PROGRESS":
      return { label: "שלחי הצעה", action: "mark_proposal_sent" };
    case "PROPOSAL_SENT":
      return { label: "פולואפ על ההצעה", action: "mark_template_sent" };
    case "BOOKING_PENDING":
      return { label: "אשרי פגישה", action: "approve_meeting" };
    case "BOOKED":
      return { label: "סמני שהפגישה התקיימה", action: "log_call_completed" };
    default:
      return null;
  }
}

export function DynamicActionButton({
  lead,
  onActionDone,
}: {
  lead: Lead;
  onActionDone: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const next = nextAction(lead);
  if (!next) return null;

  async function run() {
    if (!next) return;
    setBusy(true);
    setError(null);
    try {
      await api.performAction(lead.id, next.action);
      onActionDone();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "שגיאה");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <button
        onClick={run}
        disabled={busy}
        className="w-full bg-gray-900 text-white rounded-xl py-4 font-semibold text-base flex items-center justify-center gap-2 disabled:opacity-50"
      >
        <span>{busy ? "מבצעת…" : next.label}</span>
        {!busy && <ArrowLeft size={18} aria-hidden />}
      </button>
      {next.description && (
        <div className="mt-1 text-xs text-gray-500 text-center">
          {next.description}
        </div>
      )}
      {error && (
        <div className="mt-2 text-sm text-state-red bg-state-red/10 rounded-lg px-3 py-2">
          {error}
        </div>
      )}
    </div>
  );
}
