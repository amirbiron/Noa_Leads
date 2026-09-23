"use client";

import { useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { FollowupRulesSection } from "@/components/FollowupRulesSection";
import { api, ApiError } from "@/lib/api";
import type { User } from "@/lib/types";

// עמוד ייעודי לחוקי הפולואף (§17.1). הוצא מ-/settings (היה inline ומתפזר
// על העמוד) לתת-עמוד נפרד, בעקבות דפוס /settings/chips ו-/settings/rates.
//
// owner: עריכה מלאה. assistant: readonly (FollowupRulesSection מקבל isOwner).
// ה-enforcement האמיתי הוא ב-backend (PATCH דורש owner); כאן רק UI.
export default function FollowupRulesSettingsPage() {
  const [me, setMe] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .getMe()
      .then(setMe)
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : "שגיאה בטעינה"),
      )
      .finally(() => setLoading(false));
  }, []);

  const isOwner = me?.role === "owner";

  return (
    <AppShell title="חוקי פולואף">
      {loading && (
        <div className="text-center text-gray-400 py-10 text-sm">טוען…</div>
      )}
      {error && (
        <div className="text-sm text-state-red bg-state-red/10 rounded-lg px-3 py-2 mb-3">
          {error}
        </div>
      )}

      {!loading && !error && (
        <>
          <p className="text-sm text-gray-600 mb-3 leading-relaxed">
            {isOwner
              ? "כמה זמן אחרי כל אירוע נוצרת תזכורת, וכמה תזכורות חוזרות. שינויים יחולו על תזכורות שייווצרו מעכשיו — תזכורות פעילות ימשיכו לפי הזמן הראשוני שלהן, אך החזרות שלהן יקבלו את ההגדרה החדשה."
              : "כמה זמן אחרי כל אירוע נוצרת תזכורת. תצוגה בלבד — עריכה ניתנת לבעלים."}
          </p>
          <FollowupRulesSection isOwner={isOwner} />
        </>
      )}
    </AppShell>
  );
}
