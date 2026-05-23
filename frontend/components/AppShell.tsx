"use client";

import Link from "next/link";
import { Settings as SettingsIcon } from "lucide-react";
import { AuthGuard } from "./AuthGuard";
import { BottomNav } from "./BottomNav";
import { FloatingNewLeadButton } from "./FloatingNewLeadButton";

// עוטף עמוד מאומת: AuthGuard + תוכן + ניווט תחתון + כפתור צף.
// בכותרת — גלגל שיניים שמוביל ל-/settings (כניסה לתפריט הגדרות+logout).
export function AppShell({
  title,
  hideSettings = false,
  children,
}: {
  title?: string;
  hideSettings?: boolean;
  children: React.ReactNode;
}) {
  return (
    <AuthGuard>
      <div className="min-h-screen pb-24 bg-gray-50">
        {title && (
          <header className="bg-white border-b border-gray-200 sticky top-0 z-20">
            <div className="max-w-2xl mx-auto px-4 py-3.5 flex items-center justify-between">
              <h1 className="text-lg font-semibold">{title}</h1>
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
          </header>
        )}
        <main className="max-w-2xl mx-auto px-4 py-4">{children}</main>
        <FloatingNewLeadButton />
        <BottomNav />
      </div>
    </AuthGuard>
  );
}
