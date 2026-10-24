"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AppShell } from "@/components/AppShell";
import { EmptyState } from "@/components/EmptyState";
import { SectionHeader } from "@/components/SectionHeader";
import { StateDot } from "@/components/StateBadge";
import { STATE_COLORS } from "@/lib/colors";
import { labelCategory } from "@/lib/hebrew";
import { api, ApiError } from "@/lib/api";
import type { ProposalCard } from "@/lib/types";
import { cn } from "@/lib/utils";

export default function ProposalsPage() {
  const [items, setItems] = useState<ProposalCard[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .getProposals()
      .then((d) => setItems(d.items))
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : "שגיאה בטעינה"),
      )
      .finally(() => setLoading(false));
  }, []);

  return (
    <AppShell title="הצעות פתוחות" titleTermKey="page_proposals">
      {loading && (
        <div className="text-center text-gray-400 py-10 text-sm">טוען…</div>
      )}
      {error && (
        <div className="text-sm text-state-red bg-state-red/10 rounded-lg px-3 py-2">
          {error}
        </div>
      )}
      {!loading && !error && items.length === 0 && (
        <EmptyState
          title="אין הצעות פתוחות"
          hint="לוחצים על 'מה עכשיו?' בכרטיס ליד כדי לשלוח הצעה."
        />
      )}
      <SectionHeader title="ממתינות לתשובה" count={items.length || undefined} />
      <ul className="space-y-2">
        {items.map((p) => {
          const cls = STATE_COLORS[p.state_color];
          return (
            <li key={p.id}>
              <Link
                href={`/leads/${p.id}`}
                className={cn(
                  "block bg-white rounded-xl border border-gray-200 px-3.5 py-3 active:bg-gray-50 border-s-4",
                  cls.border,
                )}
              >
                <div className="flex items-center gap-2">
                  <StateDot color={p.state_color} />
                  <span className="font-medium truncate">{p.full_name}</span>
                </div>
                <div className="mt-1 text-sm text-gray-600 truncate">
                  {labelCategory(p.service_category)}
                </div>
                {p.days_since_proposal !== null && (
                  <div className="mt-1.5 text-xs text-gray-500">
                    נשלחה לפני{" "}
                    <strong className="text-gray-700">
                      {p.days_since_proposal}
                    </strong>{" "}
                    ימים
                  </div>
                )}
              </Link>
            </li>
          );
        })}
      </ul>
    </AppShell>
  );
}
