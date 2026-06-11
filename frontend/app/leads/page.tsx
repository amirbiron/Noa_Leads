"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Search } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { useDashboardPollContext } from "@/components/DashboardPollProvider";
import { EmptyState } from "@/components/EmptyState";
import { StateDot } from "@/components/StateBadge";
import { api, ApiError } from "@/lib/api";
import {
  formatLeadAge,
  labelCategory,
  labelStatus,
  labelSubtype,
  labelWaiting,
} from "@/lib/hebrew";
import type { LeadListItem } from "@/lib/types";
import { cn } from "@/lib/utils";
import { STATE_COLORS } from "@/lib/colors";

// צבע מצב לliקd ברשימה (Spec §12.9 — 3 צבעים בשימוש, אדום שמור לעתיד).
// real-time check על next_action_due_at, לא תלוי ב-needs_attention שcron
// מעדכן כל 15 דק'. חייב להישאר עקבי עם derive_state_color (backend) +
// inferStateColor (lead detail page).
function inferColor(lead: LeadListItem): "red" | "orange" | "green" | "gray" {
  if (["WON", "LOST", "ARCHIVED"].includes(lead.status)) return "gray";
  if (lead.next_action_due_at) {
    const due = new Date(lead.next_action_due_at).getTime();
    if (due <= Date.now()) return "orange";
  }
  return "green";
}

export default function LeadsPage() {
  const [items, setItems] = useState<LeadListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState(""); // debounced
  const [statusFilter, setStatusFilter] = useState<string>("");

  // debounce כדי לא להציף את ה-API בכל הקלדה
  useEffect(() => {
    const t = setTimeout(() => setSearch(searchInput.trim()), 300);
    return () => clearTimeout(t);
  }, [searchInput]);

  // pollVersion ב-deps → רענון אוטומטי כשפולינג זיהה ליד חדש / תגובה.
  // (העלות זהה ל-refetch רגיל; הרשימה היא list view ולא מאבדת focus.)
  const { pollVersion } = useDashboardPollContext();
  useEffect(() => {
    setLoading(true);
    setError(null);
    const params: Record<string, string | number> = { page: 1, page_size: 100 };
    if (statusFilter) params.status = statusFilter;
    if (search) params.search = search;
    api
      .listLeads(params)
      .then((d) => {
        setItems(d.items);
        setTotal(d.total);
      })
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : "שגיאה בטעינה"),
      )
      .finally(() => setLoading(false));
  }, [statusFilter, search, pollVersion]);

  // סינון פעיל = יש חיפוש או סטטוס נבחר. מבדיל בין "אין לידים בכלל" (מערכת ריקה)
  // ל"הסינון לא החזיר תוצאות" — שני מצבי empty-state שונים.
  const hasActiveFilter = Boolean(search) || Boolean(statusFilter);

  return (
    <AppShell
      title={`לידים${total ? ` (${total})` : ""}`}
      titleTermKey="page_leads"
    >
      {/* פילטרים */}
      <div className="space-y-2 mb-4">
        <div className="relative">
          <Search
            size={16}
            className="absolute top-3 inset-inline-start-3 text-gray-400 pointer-events-none"
            aria-hidden
          />
          <input
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="שם, ארגון, או 4 ספרות אחרונות של טלפון…"
            className="w-full ps-9 pe-3 py-2.5 bg-white border border-gray-200 rounded-lg text-sm focus:outline-none focus:border-gray-900"
          />
        </div>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="w-full bg-white border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-gray-900"
        >
          <option value="">כל הסטטוסים</option>
          <option value="NEW">חדש</option>
          <option value="IN_PROGRESS">בטיפול</option>
          <option value="PROPOSAL_SENT">נשלחה הצעה</option>
          <option value="BOOKING_PENDING">ממתין לאישור תור</option>
          <option value="BOOKED">פגישה מאושרת</option>
          {/* WON/LOST/ARCHIVED הוסרו: לידים סגורים בטאב הארכיון בלבד
              לפי §12.12. שמירתם כאופציות הייתה מציגה "לא נמצאו תוצאות"
              מבלבל (ה-backend ב-/leads ממילא חוסם). */}
        </select>
      </div>

      {loading && (
        <div className="text-center text-gray-400 py-10 text-sm">טוען…</div>
      )}
      {error && (
        <div className="text-sm text-state-red bg-state-red/10 rounded-lg px-3 py-2">
          {error}
        </div>
      )}
      {!loading && !error && items.length === 0 &&
        (hasActiveFilter ? (
          <EmptyState
            title="לא נמצאו תוצאות"
            hint="נסי לשנות את הסינון או לנקות אותו."
          />
        ) : (
          <EmptyState
            title="אין לידים עדיין"
            hint="לחיצה על הכפתור הכחול בפינה לפתיחת ליד חדש."
          />
        ))}

      <ul className="space-y-2">
        {items.map((lead) => {
          const color = inferColor(lead);
          const cls = STATE_COLORS[color];
          return (
            <li key={lead.id}>
              <Link
                href={`/leads/${lead.id}`}
                className={cn(
                  "block bg-white rounded-xl border border-gray-200 px-3.5 py-3 active:bg-gray-50 border-s-4",
                  cls.border,
                )}
              >
                <div className="flex items-center gap-2">
                  <StateDot color={color} />
                  <span className="font-medium truncate">{lead.full_name}</span>
                  {lead.organization_name && (
                    <span className="text-xs text-gray-500 truncate">
                      · {lead.organization_name}
                    </span>
                  )}
                  {/* badge "גיל" (§12.1) — דחוף לקצה הפנימי של השורה. */}
                  <span className="ms-auto text-xs text-gray-500 shrink-0">
                    {formatLeadAge(lead.last_activity_at, lead.created_at)}
                  </span>
                </div>
                <div className="mt-1 text-sm text-gray-600 truncate">
                  {labelCategory(lead.service_category)}
                  {lead.service_subtype &&
                    ` · ${labelSubtype(lead.service_subtype)}`}
                </div>
                <div className="mt-1.5 flex items-center gap-2 text-xs text-gray-500">
                  <span>{labelStatus(lead.status)}</span>
                  <span>•</span>
                  <span>{labelWaiting(lead.waiting_on)}</span>
                </div>
              </Link>
            </li>
          );
        })}
      </ul>
    </AppShell>
  );
}
