"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { AppShell } from "@/components/AppShell";
import { useDashboardPollContext } from "@/components/DashboardPollProvider";
import { EmptyState } from "@/components/EmptyState";
import { StateDot } from "@/components/StateBadge";
import { api, ApiError } from "@/lib/api";
import {
  formatDateTimeHebrew,
  formatLeadAge,
  labelCategory,
  labelStatus,
  labelSubtype,
} from "@/lib/hebrew";
import type { LeadListItem } from "@/lib/types";
import { cn } from "@/lib/utils";
import { STATE_COLORS } from "@/lib/colors";

// טאב הארכיון (§12.12) — כל הלידים הסגורים (WON/LOST/ARCHIVED) ממוינים לפי
// תאריך סגירה יורד. השרת מסנן וממיין (closed=true). כל הסגורים מסומנים אפור
// (עקבי עם inferColor בעמוד הלידים).
export default function ArchivePage() {
  const [items, setItems] = useState<LeadListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [reopeningId, setReopeningId] = useState<string | null>(null);

  const { pollVersion } = useDashboardPollContext();

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    return api
      .listLeads({ closed: true, page: 1, page_size: 100 })
      .then((d) => {
        setItems(d.items);
        setTotal(d.total);
      })
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : "שגיאה בטעינה"),
      )
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    void load();
  }, [load, pollVersion]);

  // פתיחה מחדש מהשורה — מחוץ ל-Link כדי שלא ינווט. אחרי הצלחה הליד כבר
  // IN_PROGRESS, אז refetch מסיר אותו מהארכיון. §6.3.
  async function handleReopen(id: string) {
    setReopeningId(id);
    setError(null);
    try {
      await api.reopenLead(id);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "שגיאה בפתיחה מחדש");
    } finally {
      setReopeningId(null);
    }
  }

  const grayBorder = STATE_COLORS["gray"].border;

  return (
    <AppShell title={`ארכיון${total ? ` (${total})` : ""}`}>
      {loading && (
        <div className="text-center text-gray-400 py-10 text-sm">טוען…</div>
      )}
      {error && (
        <div className="text-sm text-state-red bg-state-red/10 rounded-lg px-3 py-2 mb-3">
          {error}
        </div>
      )}
      {!loading && !error && items.length === 0 && (
        <EmptyState
          title="אין לידים בארכיון"
          hint="לידים סגורים (עסקה שנסגרה, סגור ללא עסקה, או ארכוב) יופיעו כאן."
        />
      )}

      <ul className="space-y-2">
        {items.map((lead) => {
          const closedLabel = formatDateTimeHebrew(lead.closed_at);
          return (
            <li
              key={lead.id}
              className={cn(
                "bg-white rounded-xl border border-gray-200 border-s-4",
                grayBorder,
              )}
            >
              <Link
                href={`/leads/${lead.id}`}
                className="block px-3.5 py-3 active:bg-gray-50"
              >
                <div className="flex items-center gap-2">
                  <StateDot color="gray" />
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
                  {closedLabel && (
                    <>
                      <span>•</span>
                      <span>נסגר ב-{closedLabel}</span>
                    </>
                  )}
                </div>
              </Link>
              <div className="border-t border-gray-100 px-3.5 py-2">
                <button
                  onClick={() => handleReopen(lead.id)}
                  disabled={reopeningId === lead.id}
                  className="rounded-lg bg-white border border-gray-300 text-gray-700 px-3 py-1.5 text-sm font-medium disabled:opacity-50"
                >
                  {reopeningId === lead.id ? "פותחת…" : "פתח מחדש"}
                </button>
              </div>
            </li>
          );
        })}
      </ul>
    </AppShell>
  );
}
