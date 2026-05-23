"use client";

import { useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { EmptyState } from "@/components/EmptyState";
import { LeadCardRow } from "@/components/LeadCardRow";
import { api, ApiError } from "@/lib/api";
import type { LeadCard } from "@/lib/types";

export default function PendingPage() {
  const [items, setItems] = useState<LeadCard[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .getPending()
      .then((d) => setItems(d.items))
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : "שגיאה בטעינה"),
      )
      .finally(() => setLoading(false));
  }, []);

  return (
    <AppShell title="ממתין לטיפול">
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
          title="אין לידים שממתינים לטיפול"
          hint="כל מה שדחוף כבר ביד שלך."
        />
      )}
      <ul className="space-y-2 mt-1">
        {items.map((lead) => (
          <li key={lead.id}>
            <LeadCardRow lead={lead} />
          </li>
        ))}
      </ul>
    </AppShell>
  );
}
