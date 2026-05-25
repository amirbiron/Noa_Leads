"use client";

import { useState } from "react";
import Link from "next/link";
import {
  Check,
  Mail,
  MessageCircle,
  MoonStar,
  Phone,
} from "lucide-react";
import { STATE_COLORS } from "@/lib/colors";
import { labelCategory, labelTaskType } from "@/lib/hebrew";
import { toWhatsAppDigits } from "@/lib/phone";
import type { TodayActionItem } from "@/lib/types";
import { cn } from "@/lib/utils";
import { api, ApiError } from "@/lib/api";
import { SmartSnoozeMenu } from "./SmartSnoozeMenu";
import { StateDot } from "./StateBadge";

interface Props {
  item: TodayActionItem;
  onChanged: () => void; // לרענון הרשימה אחרי snooze/complete
}

// Layout: 4 אזורים שמופרדים זה מזה (כל אחד click target נפרד):
//   [Link area: name+task_type] | [Contact button] | [Complete ✓] | [Snooze]
//
// Contact button (F-20): קליק אחד פותח tel:/wa.me/mailto לפי preferred_contact
// של הליד. נועה לא צריכה להיכנס לכרטיס סתם כדי להתקשר. אם השדה החסר
// (טלפון למשל) — הכפתור disabled עם tooltip מסביר.
//
// הכפתורים שלמטה (Complete + Snooze) משתמשים ב-stopPropagation כדי שקליק
// לא יטריגר את ה-Link area של ההורה.
export function TodayActionRow({ item, onChanged }: Props) {
  const cls = STATE_COLORS[item.state_color];
  const [busy, setBusy] = useState(false);
  const [snoozeOpen, setSnoozeOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function complete(e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    setBusy(true);
    setError(null);
    try {
      await api.completeTask(item.task_id);
      onChanged();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "שגיאה");
    } finally {
      // משחררים busy גם בהצלחה — onChanged לא בהכרח unmount את הרכיב
      // (אם ה-component משתמש חוזר עם נתונים מעודכנים), והכפתור היה נשאר מושבת.
      setBusy(false);
    }
  }

  const contactAction = buildContactAction(item);

  return (
    <>
      <div
        className={cn(
          "bg-white rounded-xl border border-gray-200 flex items-stretch overflow-hidden",
          "border-s-4",
          cls.border,
        )}
      >
        {/* אזור ניווט — לחיצה פותחת את כרטיס הליד */}
        <Link
          href={`/leads/${item.lead_id}`}
          className="flex-1 min-w-0 px-3.5 py-3 active:bg-gray-50"
        >
          <div className="flex items-center gap-2">
            <StateDot color={item.state_color} />
            <span className="font-medium truncate">{item.lead_name}</span>
          </div>
          <div className="mt-1 text-sm text-gray-600 truncate">
            {labelTaskType(item.task_type)}
            {" · "}
            {labelCategory(item.service_category)}
          </div>
        </Link>

        {/* אזור פעולות — Contact + Complete + Snooze. min-w-[44px] לכל אחד
            כדי לעמוד ב-touch target accessibility (~44px). */}
        <div className="flex items-stretch border-s border-gray-100 shrink-0">
          <ContactButton action={contactAction} />
          <button
            onClick={complete}
            disabled={busy}
            aria-label="סימון כהושלם"
            className="min-w-[44px] px-3 border-s border-gray-100 hover:bg-state-green/10 active:bg-state-green/20 disabled:opacity-50 text-state-green flex items-center justify-center"
          >
            <Check size={18} aria-hidden />
          </button>
          <button
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              setSnoozeOpen(true);
            }}
            disabled={busy}
            aria-label="דחייה"
            className="min-w-[44px] px-3 border-s border-gray-100 hover:bg-gray-50 active:bg-gray-100 disabled:opacity-50 text-gray-500 flex items-center justify-center"
          >
            <MoonStar size={18} aria-hidden />
          </button>
        </div>
      </div>

      {error && (
        <div className="mt-1 text-xs text-state-red bg-state-red/10 rounded px-2 py-1">
          {error}
        </div>
      )}

      <SmartSnoozeMenu
        taskId={item.task_id}
        open={snoozeOpen}
        onClose={() => setSnoozeOpen(false)}
        onSnoozed={onChanged}
      />
    </>
  );
}

// === Contact button helpers ===

type ContactAction =
  | { kind: "phone"; href: string; label: string }
  | { kind: "whatsapp"; href: string; label: string }
  | { kind: "email"; href: string; label: string }
  | { kind: "disabled"; reason: string; iconKind: "phone" | "whatsapp" | "email" };

function buildContactAction(item: TodayActionItem): ContactAction {
  if (item.preferred_contact === "phone") {
    if (!item.lead_phone) {
      return { kind: "disabled", reason: "אין טלפון בכרטיס", iconKind: "phone" };
    }
    return { kind: "phone", href: `tel:${item.lead_phone}`, label: "התקשרי" };
  }
  if (item.preferred_contact === "whatsapp") {
    const digits = toWhatsAppDigits(item.lead_phone);
    if (!digits) {
      return {
        kind: "disabled",
        reason: "אין טלפון תקין בכרטיס",
        iconKind: "whatsapp",
      };
    }
    return {
      kind: "whatsapp",
      href: `https://wa.me/${digits}`,
      label: "פתחי וואטסאפ",
    };
  }
  if (item.preferred_contact === "email") {
    if (!item.lead_email) {
      return { kind: "disabled", reason: "אין מייל בכרטיס", iconKind: "email" };
    }
    return {
      kind: "email",
      href: `mailto:${item.lead_email}`,
      label: "שלחי מייל",
    };
  }
  // fallback: preferred_contact לא מוכר → לא מציגים פעולה ייעודית. נציג
  // את אייקון WhatsApp כברירת מחדל disabled.
  return {
    kind: "disabled",
    reason: "אין ערוץ תקשורת מועדף",
    iconKind: "whatsapp",
  };
}

function ContactButton({ action }: { action: ContactAction }) {
  const Icon =
    action.kind === "phone" ||
    (action.kind === "disabled" && action.iconKind === "phone")
      ? Phone
      : action.kind === "email" ||
        (action.kind === "disabled" && action.iconKind === "email")
      ? Mail
      : MessageCircle;

  if (action.kind === "disabled") {
    return (
      <button
        disabled
        aria-label={action.reason}
        title={action.reason}
        className="min-w-[44px] px-3 disabled:opacity-30 text-gray-400 flex items-center justify-center"
      >
        <Icon size={18} aria-hidden />
      </button>
    );
  }

  const colorByKind: Record<typeof action.kind, string> = {
    phone: "text-state-green hover:bg-state-green/10 active:bg-state-green/20",
    whatsapp:
      "text-[#25D366] hover:bg-[#25D366]/10 active:bg-[#25D366]/20",
    email: "text-gray-700 hover:bg-gray-100 active:bg-gray-200",
  };

  // target="_blank" + rel רק ל-WhatsApp (פותח web/app חיצוני). tel:/mailto:
  // לא צריכים target ו-rel.
  const isExternal = action.kind === "whatsapp";

  return (
    <a
      href={action.href}
      target={isExternal ? "_blank" : undefined}
      rel={isExternal ? "noopener noreferrer" : undefined}
      aria-label={action.label}
      title={action.label}
      onClick={(e) => e.stopPropagation()}
      className={cn(
        "min-w-[44px] px-3 flex items-center justify-center",
        colorByKind[action.kind],
      )}
    >
      <Icon size={18} aria-hidden />
    </a>
  );
}
