"use client";

import { createContext, useContext } from "react";
import { X } from "lucide-react";
import { useDashboardPoll } from "@/hooks/useDashboardPoll";

// Context שמעביר ל-pages את ה-pollVersion + recentlyUpdatedLeadIds.
// ה-Provider עוטף את כל ה-app ב-layout.tsx. pages שצריכים auto-refresh
// קוראים `useDashboardPollContext()` ומשתמשים ב-pollVersion כdep ב-useEffect.
interface DashboardPollContextValue {
  pollVersion: number;
  recentlyUpdatedLeadIds: Set<string>;
}

const DashboardPollContext = createContext<DashboardPollContextValue>({
  pollVersion: 0,
  recentlyUpdatedLeadIds: new Set(),
});

export function useDashboardPollContext(): DashboardPollContextValue {
  return useContext(DashboardPollContext);
}

export function DashboardPollProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const { pollVersion, recentlyUpdatedLeadIds, toastMessage, dismissToast } =
    useDashboardPoll();

  return (
    <DashboardPollContext.Provider
      value={{ pollVersion, recentlyUpdatedLeadIds }}
    >
      {children}
      {toastMessage && (
        // positioning ב-bottom-20 כדי לא לכסות navbar בתחתית (h-16 ≈ bottom-16).
        // sm:right-4 — pinned לפינה במחשב; mobile = רוחב מלא עם padding.
        // role="status" + aria-live="polite" — קורא מסך מקריא את ה-message
        // בלי להפסיק את מה שנועה עושה.
        <div
          role="status"
          aria-live="polite"
          className="fixed bottom-20 inset-x-4 sm:inset-x-auto sm:right-4 sm:max-w-sm z-40
                     bg-gray-900 text-white rounded-lg px-4 py-3 text-sm shadow-lg
                     flex items-center justify-between gap-3"
        >
          <span className="flex-1">{toastMessage}</span>
          <button
            type="button"
            onClick={dismissToast}
            aria-label="סגירת הודעה"
            className="text-gray-300 hover:text-white shrink-0"
          >
            <X size={16} />
          </button>
        </div>
      )}
    </DashboardPollContext.Provider>
  );
}
