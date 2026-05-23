"use client";

import { useEffect, useState } from "react";
import { Sparkles } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { EmptyState } from "@/components/EmptyState";
import { LeadCardRow } from "@/components/LeadCardRow";
import { SectionHeader } from "@/components/SectionHeader";
import { TodayActionRow } from "@/components/TodayActionRow";
import { api, ApiError } from "@/lib/api";
import type { HomeDashboard } from "@/lib/types";

export default function HomePage() {
  const [data, setData] = useState<HomeDashboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    api
      .getHome()
      .then((d) => {
        if (active) setData(d);
      })
      .catch((err) => {
        if (!active) return;
        setError(err instanceof ApiError ? err.message : "שגיאה בטעינה");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  return (
    <AppShell title="בית">
      {loading && (
        <div className="text-center text-gray-400 py-10 text-sm">טוען…</div>
      )}

      {error && (
        <div className="text-sm text-state-red bg-state-red/10 rounded-lg px-3 py-2">
          {error}
        </div>
      )}

      {data && (
        <>
          {/* פעולות היום */}
          <SectionHeader
            title={
              data.today_actions.length > 0
                ? `${data.today_actions.length} משימות מחכות לך היום`
                : "אין משימות דחופות היום"
            }
          />
          {data.today_actions.length === 0 ? (
            <EmptyState
              title="אין משימות דחופות היום"
              hint="אפשר להתחיל את היום ברוגע ✓"
              icon={<Sparkles size={24} aria-hidden />}
            />
          ) : (
            <ul className="space-y-2">
              {data.today_actions.map((item) => (
                <li key={item.task_id}>
                  <TodayActionRow item={item} />
                </li>
              ))}
            </ul>
          )}

          {/* פניות חדשות */}
          {data.new_leads.length > 0 && (
            <>
              <SectionHeader
                title="פניות חדשות שעוד לא ענית עליהן"
                count={data.new_leads.length}
              />
              <ul className="space-y-2">
                {data.new_leads.map((lead) => (
                  <li key={lead.id}>
                    <LeadCardRow lead={lead} />
                  </li>
                ))}
              </ul>
            </>
          )}

          {/* ממתין לטיפול */}
          {data.pending.length > 0 && (
            <>
              <SectionHeader
                title="ממתין לטיפול"
                count={data.pending.length}
              />
              <ul className="space-y-2">
                {data.pending.map((lead) => (
                  <li key={lead.id}>
                    <LeadCardRow lead={lead} />
                  </li>
                ))}
              </ul>
            </>
          )}

          {/* תובנות השבוע */}
          <SectionHeader title="תובנות השבוע" />
          <div className="bg-white rounded-xl border border-gray-200 p-4">
            <div className="grid grid-cols-3 gap-3 text-center">
              <Stat
                value={data.weekly_insights.new_leads_count}
                label="נכנסו השבוע"
              />
              <Stat
                value={data.weekly_insights.responded_in_time_count}
                label="קיבלו מענה בזמן"
              />
              <Stat
                value={data.weekly_insights.stuck_count}
                label="נתקעו ללא צעד הבא"
                tone={data.weekly_insights.stuck_count > 0 ? "red" : "gray"}
              />
            </div>
          </div>
        </>
      )}
    </AppShell>
  );
}

function Stat({
  value,
  label,
  tone = "gray",
}: {
  value: number;
  label: string;
  tone?: "gray" | "red";
}) {
  return (
    <div>
      <div
        className={`text-2xl font-semibold ${tone === "red" ? "text-state-red" : "text-gray-900"}`}
      >
        {value}
      </div>
      <div className="text-xs text-gray-500 mt-0.5">{label}</div>
    </div>
  );
}
