"use client";

import { useState } from "react";
import { MessageSquareReply } from "lucide-react";
import { api, ApiError } from "@/lib/api";

// כפתור משלים בכרטיס הליד: "תעד הודעה נכנסת".
//
// ה-trigger ל-perform_action("log_inbound_message") — המסלול היחיד
// (chokepoint) שמפעיל את כל ה-side-effects של inbound על ליד קיים:
// סגירת warm_followup ("פולואפ חם"), reply_boost (קפיצה לראש הדשבורד),
// waiting_on=NOAH (הכדור חוזר לנועה), auto-progress NEW→IN_PROGRESS,
// last_inbound_at. **לא** עוקף את ה-chokepoint — קורא אך ורק דרך
// performAction, שמגיע ל-register_inbound ב-backend.
//
// inline-expand (לא modal): לחיצה פותחת textarea אופציונלי. נועה יכולה
// לתעד עם תוכן (מה הלקוח אמר) או רק לסמן שהיה inbound בלי טקסט.
export function LogInboundButton({
  leadId,
  onLogged,
}: {
  leadId: string;
  onLogged: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [content, setContent] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function reset() {
    setOpen(false);
    setContent("");
    setError(null);
  }

  async function handleSave() {
    setBusy(true);
    setError(null);
    try {
      // content אופציונלי — trim ל-undefined כשריק (סימון inbound נקי).
      // register_inbound ב-backend תומך ב-content=None.
      await api.performAction(leadId, "log_inbound_message", {
        content: content.trim() || undefined,
      });
      reset();
      onLogged(); // רענון הדף — ה-timeline + סגירת warm_followup ישתקפו.
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "שגיאה בתיעוד ההודעה");
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="w-full rounded-lg bg-white border border-gray-200 py-2.5 text-sm font-medium flex items-center justify-center gap-1.5"
      >
        <MessageSquareReply size={15} aria-hidden className="rtl:-scale-x-100" />
        תעד הודעה נכנסת
      </button>
    );
  }

  return (
    <div className="rounded-lg bg-white border border-gray-200 p-3 space-y-2.5">
      <div className="text-sm font-medium text-gray-800 flex items-center gap-1.5">
        <MessageSquareReply size={15} aria-hidden className="rtl:-scale-x-100" />
        תעד הודעה נכנסת
      </div>
      <textarea
        value={content}
        onChange={(e) => setContent(e.target.value)}
        rows={2}
        autoFocus
        placeholder="מה הלקוח אמר/כתב? (אופציונלי)"
        disabled={busy}
        className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-gray-900 focus:outline-none"
      />
      {error && <div className="text-xs text-state-red">{error}</div>}
      <div className="flex gap-2">
        <button
          type="button"
          onClick={reset}
          disabled={busy}
          className="flex-1 rounded-lg bg-gray-100 text-gray-800 py-2 text-sm font-medium disabled:opacity-50"
        >
          ביטול
        </button>
        <button
          type="button"
          onClick={handleSave}
          disabled={busy}
          className="flex-1 rounded-lg bg-gray-900 text-white py-2 text-sm font-medium disabled:opacity-50"
        >
          {busy ? "שומרת…" : "שמירה"}
        </button>
      </div>
    </div>
  );
}
