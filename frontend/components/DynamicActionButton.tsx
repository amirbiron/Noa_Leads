"use client";

import { useEffect, useMemo, useState } from "react";
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

// הפגישה שכבר הסתיימה, אם יש כזו. `bookings` מגיע ממוין בסדר עולה,
// ולכן `findLast` מחזיר את האחרונה שהסתיימה — לא את הראשונה. הגרסה
// הקודמת קיבלה פגישה *אחת* מהשרת, והשרת החזיר את הרחוקה ביותר; לליד
// עם פגישה שהסתיימה ועוד אחת עתידית הכפתור פשוט לא הופיע.
function lastFinished(bookings: BookingRead[]): BookingRead | null {
  const now = Date.now();
  for (let i = bookings.length - 1; i >= 0; i--) {
    if (new Date(bookings[i].requested_slot_end).getTime() <= now) {
      return bookings[i];
    }
  }
  return null;
}

function nextAction(
  lead: Lead,
  bookings: BookingRead[],
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
    // BOOKING_PENDING נשאר רק לשורות legacy — פגישה נקבעת מאושרת
    // מיד, ואין יותר פעולת "אשרי פגישה". הפעולה הישנה הועברה את הליד
    // ל-BOOKED **בלי** ליצור אירוע ביומן ובלי לגעת בשורת ה-Booking,
    // ולכן היא נמחקה גם מה-state machine בשרת.
    case "BOOKED": {
      // מציע "סמני שהפגישה התקיימה" רק אחרי שהפגישה הסתיימה (slot_end).
      // ה-backend ממשיך להחזיר APPROVED past-end booking כל עוד הליד
      // עדיין BOOKED — פגישות קצרות (<30 דק') ופגישות שעבר זמנן עובדות.
      if (!lastFinished(bookings)) return null;
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
  bookings,
  onActionDone,
}: {
  lead: Lead;
  bookings: BookingRead[];
  onActionDone: () => void;
}) {
  // Tick לרענון UI כשעוברת הפגישה **הקרובה ביותר** בזמן שהמסך פתוח.
  // עם כמה פגישות, טיימר על האחרונה היה מפספס את הרגע שבו הראשונה
  // מסתיימת והכפתור אמור להופיע.
  const [, forceRender] = useState(0);
  const nextEndMs = useMemo(() => {
    if (lead.status !== "BOOKED") return null;
    const now = Date.now();
    const future = bookings
      .filter((b) => b.status === "approved")
      .map((b) => new Date(b.requested_slot_end).getTime())
      .filter((t) => t > now);
    return future.length > 0 ? Math.min(...future) : null;
  }, [lead.status, bookings]);

  useEffect(() => {
    if (nextEndMs === null) return;
    const msUntilEnd = nextEndMs - Date.now();
    if (msUntilEnd <= 0) return;
    const t = setTimeout(() => forceRender((n) => n + 1), msUntilEnd + 1000);
    return () => clearTimeout(t);
  }, [nextEndMs]);

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sheet, setSheet] = useState<SheetState | null>(null);

  const next = nextAction(lead, bookings);
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
      // *כל* כשל ב-getTemplateAuto → fallback ל-manual picker, לא רק 404:
      // - 404 = הקנונית בוטלה/נמחקה (תרחיש מכוון).
      // - 500 / network / timeout = transient — manual picker עובד עצמאית
      //   (api.listTemplates נקרא בתוך ה-sheet, endpoint נפרד; אם הוא
      //   גם נופל, ה-sheet יציג את ה-error משלו).
      // לפני התיקון, רק 404 נפל ל-fallback; שאר השגיאות חסמו את ה-flow
      // הראשי לחלוטין (תיקון bugbot).
      if (!(err instanceof ApiError && err.status === 404)) {
        // ב-dev — לסייע ב-debug. ב-prod — לא מציפים את המשתמשת.
        // eslint-disable-next-line no-console
        console.warn("getTemplateAuto failed, falling back to manual:", err);
      }
      setSheet({ presetId: undefined, forceChannel, actionType });
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
    const n = nextAction(lead, bookings);
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
