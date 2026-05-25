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
import type { TodayActionItem } from "@/lib/types";
import { cn } from "@/lib/utils";
import { api, ApiError } from "@/lib/api";
import { SmartSnoozeMenu } from "./SmartSnoozeMenu";
import { StateDot } from "./StateBadge";

const CONTACT_ICONS: Record<string, typeof Phone> = {
  phone: Phone,
  whatsapp: MessageCircle,
  email: Mail,
};

interface Props {
  item: TodayActionItem;
  onChanged: () => void; // לרענון הרשימה אחרי snooze/complete
}

// שורת משימה עם 3 אזורים: ניווט לליד | סיום | דחייה.
// הכפתורים עוצרים את הניווט (stopPropagation) כדי שקליק עליהם
// יבצע את הפעולה ולא יפתח את כרטיס הליד.
export function TodayActionRow({ item, onChanged }: Props) {
  const cls = STATE_COLORS[item.state_color];
  const ContactIcon = CONTACT_ICONS[item.preferred_contact] ?? MessageCircle;
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
          <div className="mt-1.5 flex items-center gap-2 text-xs text-gray-500">
            <ContactIcon size={12} aria-hidden />
          </div>
        </Link>

        {/* אזור פעולות — סיום + דחייה */}
        <div className="flex items-stretch border-s border-gray-100 shrink-0">
          <button
            onClick={complete}
            disabled={busy}
            aria-label="סימון כהושלם"
            className="px-3 hover:bg-state-green/10 active:bg-state-green/20 disabled:opacity-50 text-state-green flex items-center"
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
            className="px-3 border-s border-gray-100 hover:bg-gray-50 active:bg-gray-100 disabled:opacity-50 text-gray-500 flex items-center"
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
