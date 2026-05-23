"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Search } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { EmptyState } from "@/components/EmptyState";
import { StateDot } from "@/components/StateBadge";
import { api, ApiError } from "@/lib/api";
import {
  labelCategory,
  labelStatus,
  labelSubtype,
  labelWaiting,
} from "@/lib/hebrew";
import type { LeadListItem } from "@/lib/types";
import { cn } from "@/lib/utils";
import { STATE_COLORS } from "@/lib/colors";

// אומדן צבע בצד הלקוח עבור list view (אין state_color מהשרת ב-LeadListItem)
function inferColor(lead: LeadListItem): "red" | "orange" | "green" | "gray" {
  if (["WON", "LOST", "ARCHIVED"].includes(lead.status)) return "gray";
  if (lead.needs_attention) return "red";
  return "green";
}

export default function LeadsPage() {
  const [items, setItems] = useState<LeadListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("");

  useEffect(() => {
    setLoading(true);
    const params: Record<string, string | number> = { page: 1, page_size: 100 };
    if (statusFilter) params.status = statusFilter;
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
  }, [statusFilter]);

  const filtered = useMemo(() => {
    if (!search.trim()) return items;
    const q = search.trim().toLowerCase();
    return items.filter((l) => {
      if (l.full_name.toLowerCase().includes(q)) return true;
      if (l.organization_name?.toLowerCase().includes(q)) return true;
      return false;
    });
  }, [items, search]);

  return (
    <AppShell title={`לידים${total ? ` (${total})` : ""}`}>
      {/* פילטרים */}
      <div className="space-y-2 mb-4">
        <div className="relative">
          <Search
            size={16}
            className="absolute top-3 inset-inline-start-3 text-gray-400 pointer-events-none"
            aria-hidden
          />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="חיפוש לפי שם או ארגון…"
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
          <option value="WON">נסגרה עסקה</option>
          <option value="LOST">סגור ללא עסקה</option>
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
      {!loading && !error && filtered.length === 0 && (
        <EmptyState
          title={search ? "לא נמצאו התאמות" : "אין לידים עדיין"}
          hint="לחיצה על הכפתור הכחול בפינה לפתיחת ליד חדש."
        />
      )}

      <ul className="space-y-2">
        {filtered.map((lead) => {
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
