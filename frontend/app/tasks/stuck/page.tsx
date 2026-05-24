"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AlertTriangle, ChevronLeft } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { EmptyState } from "@/components/EmptyState";
import { api, ApiError } from "@/lib/api";
import { labelCategory, labelTaskType } from "@/lib/hebrew";
import type { StuckTaskItem } from "@/lib/types";

// "משימות תקועות" — עמוד נפרד לכל ה-tasks שלא טופלו 7+ ימים אחרי due_at.
// לפי האפיון יב סעיף 477: "אם לא טופל אחרי כל ההתראות → עובר לעמוד נפרד".
// מיון לפי וותק (הישנים קודם) מהשרת.
export default function StuckTasksPage() {
  const [items, setItems] = useState<StuckTaskItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .listStuckTasks()
      .then(setItems)
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : "שגיאה בטעינה"),
      )
      .finally(() => setLoading(false));
  }, []);

  return (
    <AppShell title="משימות תקועות">
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
          title="אין משימות תקועות"
          hint="כל הטיפולים בזמן ✓"
          icon={<AlertTriangle size={24} aria-hidden />}
        />
      )}

      {items.length > 0 && (
        <>
          <p className="text-sm text-gray-500 mb-3">
            משימות שלא טופלו במועד — מסודר לפי וותק (ישנים קודם).
          </p>
          <ul className="space-y-2">
            {items.map((item) => (
              <li key={item.task_id}>
                <Link
                  href={`/leads/${item.lead_id}`}
                  className="block bg-white rounded-xl border border-gray-200 px-3.5 py-3 active:bg-gray-50 border-s-4 border-state-red"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="font-medium truncate">
                          {item.lead_name}
                        </span>
                        {item.waiting_on === "CLIENT" && (
                          <span
                            className="text-sm"
                            aria-label="מחכה ללקוח"
                            title="מחכה ללקוח"
                          >
                            ⏳
                          </span>
                        )}
                      </div>
                      <div className="mt-1 text-sm text-gray-600 truncate">
                        {labelTaskType(item.task_type)}
                        {" · "}
                        {labelCategory(item.service_category)}
                      </div>
                      <div className="mt-1.5 text-xs text-state-red font-medium">
                        {item.days_stuck === 0
                          ? "באיחור היום"
                          : item.days_stuck === 1
                            ? "באיחור יום"
                            : item.days_stuck === 2
                              ? "באיחור יומיים"
                              : `באיחור ${item.days_stuck} ימים`}
                      </div>
                    </div>
                    <ChevronLeft
                      className="text-gray-300 shrink-0 mt-1"
                      size={18}
                      aria-hidden
                    />
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        </>
      )}
    </AppShell>
  );
}
