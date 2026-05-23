"use client";

import Link from "next/link";
import { ChevronLeft } from "lucide-react";
import { STATE_COLORS } from "@/lib/colors";
import {
  formatRelativeHebrew,
  labelCategory,
  labelStatus,
  labelSubtype,
  labelWaiting,
} from "@/lib/hebrew";
import type { LeadCard } from "@/lib/types";
import { cn } from "@/lib/utils";
import { StateDot } from "./StateBadge";

// כרטיס ליד דחוס לתצוגה ברשימות הדשבורד (פניות חדשות / ממתין / וכו').
// פס צד שמאלי בצבע מצב (border-inline-start ל-RTL).
export function LeadCardRow({ lead }: { lead: LeadCard }) {
  const cls = STATE_COLORS[lead.state_color];
  return (
    <Link
      href={`/leads/${lead.id}`}
      className={cn(
        "block bg-white rounded-xl border border-gray-200 px-3.5 py-3 active:bg-gray-50",
        "border-s-4",
        cls.border,
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <StateDot color={lead.state_color} />
            <span className="font-medium truncate">{lead.full_name}</span>
            {lead.has_recent_reply && (
              <span className="text-[10px] font-semibold text-state-orange bg-state-orange/15 px-1.5 py-0.5 rounded">
                תגובה חדשה
              </span>
            )}
          </div>
          <div className="mt-1 text-sm text-gray-600 truncate">
            {labelCategory(lead.service_category)}
            {lead.service_subtype && ` · ${labelSubtype(lead.service_subtype)}`}
          </div>
          <div className="mt-1.5 flex items-center gap-3 text-xs text-gray-500">
            <span>{labelStatus(lead.status)}</span>
            <span>•</span>
            <span>ממתין: {labelWaiting(lead.waiting_on)}</span>
            {lead.next_action_due_at && (
              <>
                <span>•</span>
                <span>{formatRelativeHebrew(lead.next_action_due_at)}</span>
              </>
            )}
          </div>
        </div>
        <ChevronLeft className="text-gray-300 shrink-0 mt-1" size={18} aria-hidden />
      </div>
    </Link>
  );
}
