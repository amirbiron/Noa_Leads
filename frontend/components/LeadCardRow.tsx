"use client";

import Link from "next/link";
import { ChevronLeft } from "lucide-react";
import { STATE_COLORS } from "@/lib/colors";
import {
  labelCategory,
  labelStatus,
  labelSubtype,
} from "@/lib/hebrew";
import type { LeadCard } from "@/lib/types";
import { cn } from "@/lib/utils";
import { StateDot } from "./StateBadge";

// כרטיס ליד דחוס לתצוגה ברשימות הדשבורד (פניות חדשות / ממתין / וכו').
// פס צד שמאלי בצבע מצב (border-inline-start ל-RTL).
export function LeadCardRow({ lead }: { lead: LeadCard }) {
  const cls = STATE_COLORS[lead.state_color];
  // אייקון ⏳ ליד שם הליד כשהכדור אצל הלקוח (לפי האפיון יב). מחכה לי
  // (ברירת מחדל) = אין סימון, כי רוב הלידים בכל מקרה אצל נועה.
  // האייקון מופיע אחרי הלייבל ("הלקוח ⏳") — סדר קריאה טבעי ב-RTL.
  const waitingOnClient = lead.waiting_on === "CLIENT";
  // has_recent_reply נדלק גם על create_booking_request (booking.py קובע
  // reply_boost_until). הלייבל מותאם לפי המקור — last_activity_type
  // מבחין בין בקשת תור (meeting_requested) להודעה אמיתית. status בלבד
  // לא מספיק: ליד BOOKING_PENDING עם הודעה אמיתית מהלקוח (inbound) צריך
  // עדיין "תגובה חדשה", לא "בקשת תור חדשה".
  const recentReplyLabel =
    lead.last_activity_type === "meeting_requested"
      ? "בקשת תור חדשה"
      : "תגובה חדשה";
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
            {waitingOnClient && (
              <span
                className="text-xs text-gray-500 inline-flex items-center gap-1"
                aria-label="ממתין ללקוח"
                title="ממתין ללקוח"
              >
                הלקוח <span aria-hidden>⏳</span>
              </span>
            )}
            {lead.has_recent_reply && (
              <span className="text-[10px] font-semibold text-state-orange bg-state-orange/15 px-1.5 py-0.5 rounded">
                {recentReplyLabel}
              </span>
            )}
          </div>
          <div className="mt-1 text-sm text-gray-600 truncate">
            {labelCategory(lead.service_category)}
            {lead.service_subtype && ` · ${labelSubtype(lead.service_subtype)}`}
          </div>
          <div className="mt-1.5 text-xs text-gray-500">
            {labelStatus(lead.status)}
          </div>
        </div>
        <ChevronLeft className="text-gray-300 shrink-0 mt-1" size={18} aria-hidden />
      </div>
    </Link>
  );
}
