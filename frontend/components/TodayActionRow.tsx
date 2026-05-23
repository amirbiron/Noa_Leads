"use client";

import Link from "next/link";
import { ChevronLeft, Clock, Phone, MessageCircle, Mail } from "lucide-react";
import { STATE_COLORS } from "@/lib/colors";
import {
  formatRelativeHebrew,
  labelCategory,
  labelTaskType,
} from "@/lib/hebrew";
import type { TodayActionItem } from "@/lib/types";
import { cn } from "@/lib/utils";
import { StateDot } from "./StateBadge";

const CONTACT_ICONS: Record<string, typeof Phone> = {
  phone: Phone,
  whatsapp: MessageCircle,
  email: Mail,
};

export function TodayActionRow({ item }: { item: TodayActionItem }) {
  const cls = STATE_COLORS[item.state_color];
  const ContactIcon = CONTACT_ICONS[item.preferred_contact] ?? MessageCircle;
  return (
    <Link
      href={`/leads/${item.lead_id}`}
      className={cn(
        "block bg-white rounded-xl border border-gray-200 px-3.5 py-3 active:bg-gray-50",
        "border-s-4",
        cls.border,
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <StateDot color={item.state_color} />
            <span className="font-medium truncate">{item.lead_name}</span>
            {item.is_overdue && (
              <span className="text-[10px] font-semibold text-state-red bg-state-red/15 px-1.5 py-0.5 rounded">
                באיחור
              </span>
            )}
          </div>
          <div className="mt-1 text-sm text-gray-600 truncate">
            {labelTaskType(item.task_type)}
            {" · "}
            {labelCategory(item.service_category)}
          </div>
          <div className="mt-1.5 flex items-center gap-2 text-xs text-gray-500">
            <Clock size={12} aria-hidden />
            <span>{formatRelativeHebrew(item.due_at)}</span>
            <ContactIcon size={12} aria-hidden className="ms-1" />
          </div>
        </div>
        <ChevronLeft className="text-gray-300 shrink-0 mt-1" size={18} aria-hidden />
      </div>
    </Link>
  );
}
