"use client";

import { useEffect, useState } from "react";
import { ArrowLeft } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { BookingRead, Lead } from "@/lib/types";
import { TemplatePickerSheet } from "./TemplatePickerSheet";

// כפתור "מה עכשיו?" — דינמי לפי סטטוס הליד.
// פעולה אחת ראשית גדולה, מובילה לפעולה הטבעית הבאה.
//
// Spec §9.3: "לחיצה על 'שלח' פותחת את וואטסאפ עם הטקסט המוכן".
// Spec §12.2: כפתור ראשי מוביל לפעולה אמיתית (לא תיעוד בדיעבד).
// Spec §12.3: סטטוס משתנה *אחרי* שהפעולה בוצעה.
//
// "template" → פותח TemplatePickerSheet עם תבנית קנונית (auto-selected).
//   role מועבר ל-backend (GET /templates/auto) שמחזיר את הקנונית לפי
//   audience (organization vs private). 404 → fallback ל-manual picker.
// "direct" → קריאת API ישירה (call/approve/log) — אין תבנית להציג.
type NextAction =
  | { kind: "template"; role: "opening" | "proposal" | "proposal_followup"; label: string; description?: string }
  | { kind: "direct"; action: string; label: string; description?: string };

function nextAction(
  lead: Lead,
  activeBooking: BookingRead | null,
): NextAction | null {
  // לידים סגורים: לא מציגים פעולה ראשית.
  if (lead.status === "WON" || lead.status === "LOST" || lead.status === "ARCHIVED") {
    return null;
  }
  // ליד פתוח שמסומן "עדיף טלפון" — כפתור התקשרות גובר על שאר הסטטוסים.
  // לא דרך תבנית: התקשרות = הפעולה עצמה, אין מה לרנדר.
  if (lead.preferred_contact === "phone") {
    return {
      kind: "direct",
      action: "log_call_completed",
      label: "התקשרי",
      description: "ולתעד אחרי",
    };
  }

  // ליד שמסומן "עדיף מייל" — label נפרד לתחושה ויזואלית של מייל
  // (האייקון/CTA בתוך ה-sheet כבר מתאים את עצמו לפי forceChannel).
  const useEmail = lead.preferred_contact === "email";
  const openingLabel = useEmail ? "השב במייל" : "שלחי תבנית פתיחה";
  const proposalLabel = useEmail ? "השב במייל" : "שלחי הצעה";
  const followupLabel = useEmail ? "השב במייל" : "פולואף על ההצעה";

  switch (lead.status) {
    case "NEW":
      return { kind: "template", role: "opening", label: openingLabel };
    case "IN_PROGRESS":
      return { kind: "template", role: "proposal", label: proposalLabel };
    case "PROPOSAL_SENT":
      return { kind: "template", role: "proposal_followup", label: followupLabel };
    case "BOOKING_PENDING":
      return { kind: "direct", action: "approve_meeting", label: "אשרי פגישה" };
    case "BOOKED": {
      // מציע "סמני שהפגישה התקיימה" רק אחרי שהפגישה הסתיימה (slot_end).
      // ה-backend ממשיך להחזיר APPROVED past-end booking כל עוד הליד
      // עדיין BOOKED — פגישות קצרות (<30 דק') ופגישות שעבר זמנן עובדות.
      if (!activeBooking) return null;
      const end = new Date(activeBooking.requested_slot_end).getTime();
      if (Date.now() < end) return null;
      return {
        kind: "direct",
        action: "log_call_completed",
        label: "סמני שהפגישה התקיימה",
      };
    }
    default:
      return null;
  }
}

interface SheetState {
  presetId: string | undefined;
  // forceChannel רק כש-preferred_contact='email' — אז נכריח mailto.
  // ב-WA default: undefined → TemplatePickerSheet יקבע לפי template.channel
  // (חשוב למשל לתבניות org T2/T8 שהן email מטבען — גם אם ה-preference WA,
  // הגוף שלהן רשמי ומיועד למייל. שליחת body של email דרך WA תוצאתה
  // הודעת WA ארוכה ולא מותאמת).
  forceChannel: "email" | undefined;
  actionType: "mark_template_sent" | "mark_proposal_sent";
}

export function DynamicActionButton({
  lead,
  activeBooking,
  onActionDone,
}: {
  lead: Lead;
  activeBooking: BookingRead | null;
  onActionDone: () => void;
}) {
  // Tick לרענון UI כשעובר ה-slot_end בזמן שהמסך פתוח.
  const [, forceRender] = useState(0);
  useEffect(() => {
    if (
      lead.status !== "BOOKED" ||
      !activeBooking ||
      activeBooking.status !== "approved"
    ) {
      return;
    }
    const end = new Date(activeBooking.requested_slot_end).getTime();
    const msUntilEnd = end - Date.now();
    if (msUntilEnd <= 0) return;
    const t = setTimeout(() => forceRender((n) => n + 1), msUntilEnd + 1000);
    return () => clearTimeout(t);
  }, [lead.status, activeBooking]);

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sheet, setSheet] = useState<SheetState | null>(null);

  const next = nextAction(lead, activeBooking);
  if (!next) return null;

  async function openTemplateSheet(
    role: "opening" | "proposal" | "proposal_followup",
  ) {
    setBusy(true);
    setError(null);
    const useEmail = lead.preferred_contact === "email";
    const actionType: SheetState["actionType"] =
      role === "proposal" ? "mark_proposal_sent" : "mark_template_sent";
    // רק email-pref כופה mailto. אחרת template.channel קובע (T2/T8 = email,
    // T1/T4/T9 = WA) — מונע שליחת body של email דרך WA או להפך.
    const forceChannel: SheetState["forceChannel"] = useEmail ? "email" : undefined;
    try {
      const tpl = await api.getTemplateAuto(lead.id, role);
      setSheet({ presetId: tpl.id, forceChannel, actionType });
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        // הקנונית בוטלה/נמחקה — fallback ל-manual picker.
        // ה-sheet ייפתח עם רשימה רגילה; נועה תבחר ידנית.
        setSheet({ presetId: undefined, forceChannel, actionType });
      } else {
        setError(err instanceof ApiError ? err.message : "שגיאה בטעינת תבנית");
      }
    } finally {
      setBusy(false);
    }
  }

  async function runDirect(action: string) {
    setBusy(true);
    setError(null);
    try {
      await api.performAction(lead.id, action);
      onActionDone();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "שגיאה");
    } finally {
      setBusy(false);
    }
  }

  async function onClick() {
    // capture next locally — TS לא שומר narrowing של ה-outer scope בתוך
    // async closure שמופעלת ע"י React handler. הקריאה ל-nextAction
    // דטרמיניסטית באותו render, אז זה זהה ל-next שנבדק למעלה.
    const n = nextAction(lead, activeBooking);
    if (!n) return;
    if (n.kind === "template") {
      await openTemplateSheet(n.role);
    } else {
      await runDirect(n.action);
    }
  }

  return (
    <div>
      <button
        onClick={onClick}
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
      {sheet && (
        <TemplatePickerSheet
          lead={lead}
          open
          onClose={() => setSheet(null)}
          onSent={() => {
            setSheet(null);
            onActionDone();
          }}
          presetTemplateId={sheet.presetId}
          forceChannel={sheet.forceChannel}
          actionType={sheet.actionType}
        />
      )}
    </div>
  );
}
