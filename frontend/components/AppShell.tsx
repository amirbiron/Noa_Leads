"use client";

import Link from "next/link";
import { Settings as SettingsIcon } from "lucide-react";
import { AuthGuard } from "./AuthGuard";
import { BottomNav } from "./BottomNav";
import { FloatingNewLeadButton } from "./FloatingNewLeadButton";
import { TermHint } from "./TermHint";
import type { TermKey } from "@/lib/glossary";

// עוטף עמוד מאומת: AuthGuard + תוכן + ניווט תחתון + כפתור צף.
// בכותרת — גלגל שיניים שמוביל ל-/settings (כניסה לתפריט הגדרות+logout).
//
// `headerActions` — slot אופציונלי לתוכן נוסף בהדר משמאל לגלגל הגדרות
// (למשל הבועה של טוגל הסיכום היומי ב-`/` — C.1/C.2 §6.8).
//
// `titleTermKey` — ⓘ צמוד ל-title שמסביר את הדף (page_today / page_pending
// /...). מופיע רק אם הפיצ'ר flag דלוק.
export function AppShell({
  title,
  titleTermKey,
  hideSettings = false,
  headerActions,
  children,
}: {
  title?: string;
  titleTermKey?: TermKey;
  hideSettings?: boolean;
  headerActions?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <AuthGuard>
      <div className="min-h-screen pb-24 bg-gray-50">
        {title && (
          <header className="bg-white border-b border-gray-200 sticky top-0 z-20">
            <div className="max-w-2xl mx-auto px-4 py-3.5 flex items-center justify-between">
              <h1 className="text-lg font-semibold flex items-center">
                {title}
                {titleTermKey && (
                  <TermHint termKey={titleTermKey} iconSize={16} />
                )}
              </h1>
              <div className="flex items-center gap-2">
                {headerActions}
                {!hideSettings && (
                  <Link
                    href="/settings"
                    aria-label="הגדרות"
                    className="text-gray-400 hover:text-gray-700 p-1.5 -m-1.5"
                  >
                    <SettingsIcon size={20} aria-hidden />
                  </Link>
                )}
              </div>
            </div>
          </header>
        )}
        <main className="max-w-2xl mx-auto px-4 py-4">{children}</main>
        <FloatingNewLeadButton />
        <BottomNav />
      </div>
    </AuthGuard>
  );
}
