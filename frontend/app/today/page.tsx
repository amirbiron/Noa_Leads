"use client";

import { useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { EmptyState } from "@/components/EmptyState";
import { TodayActionRow } from "@/components/TodayActionRow";
import { api, ApiError } from "@/lib/api";
import type { TodayActionItem } from "@/lib/types";

export default function TodayPage() {
  const [items, setItems] = useState<TodayActionItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  async function load() {
    setError(null);
    try {
      const d = await api.getToday();
      setItems(d.items);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "שגיאה בטעינה");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  return (
    <AppShell title="פעולות היום">
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
          title="אין משימות להיום"
          hint="הכל מסונכרן ✓"
        />
      )}
      <ul className="space-y-2 mt-1">
        {items.map((item) => (
          <li key={item.task_id}>
            <TodayActionRow item={item} onChanged={load} />
          </li>
        ))}
      </ul>
    </AppShell>
  );
}
