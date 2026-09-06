"use client";

import { useEffect, useState } from "react";
import { AlertTriangle } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { EmptyState } from "@/components/EmptyState";
import { LeadCardRow } from "@/components/LeadCardRow";
import { api, ApiError } from "@/lib/api";
import type { LeadCard } from "@/lib/types";

// היעד של הכרטיס "דחוף — ללא מענה 48 שעות" בבית.
// המסך הזה קיים כדי שהמספר בכרטיס והרשימה שנפתחת בלחיצה עליו יגיעו
// מאותה שאילתה בדיוק (GET /dashboard/urgent). קודם הכפתור הוביל
// ל"פעולות היום", שמסנן חלון due_at משלו — ליד תקוע 7+ ימים נספר
// בכרטיס אבל הופיע רק ב"ממתין לטיפול", ונועה ראתה "3" ורק ליד אחד.
export default function UrgentPage() {
  const [items, setItems] = useState<LeadCard[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .getUrgent()
      .then((d) => setItems(d.items))
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : "שגיאה בטעינה"),
      )
      .finally(() => setLoading(false));
  }, []);

  return (
    <AppShell title="דחוף — ללא מענה 48 שעות">
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
          title="אין לידים ללא מענה"
          hint="כל הפניות מהיומיים האחרונים קיבלו מענה ראשון ✓"
          icon={<AlertTriangle size={24} aria-hidden />}
        />
      )}

      {items.length > 0 && (
        <>
          <p className="text-sm text-gray-500 mb-3">
            פניות שנכנסו לפני 48 שעות ומעלה ועדיין לא נשלח אליהן מענה ראשון.
          </p>
          <ul className="space-y-2">
            {items.map((lead) => (
              <li key={lead.id}>
                <LeadCardRow lead={lead} />
              </li>
            ))}
          </ul>
        </>
      )}
    </AppShell>
  );
}
