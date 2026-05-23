"use client";

import { AuthGuard } from "./AuthGuard";
import { BottomNav } from "./BottomNav";
import { FloatingNewLeadButton } from "./FloatingNewLeadButton";

// עוטף עמוד מאומת: AuthGuard + תוכן + ניווט תחתון + כפתור צף.
export function AppShell({
  title,
  children,
}: {
  title?: string;
  children: React.ReactNode;
}) {
  return (
    <AuthGuard>
      <div className="min-h-screen pb-24 bg-gray-50">
        {title && (
          <header className="bg-white border-b border-gray-200 sticky top-0 z-20">
            <div className="max-w-2xl mx-auto px-4 py-3.5">
              <h1 className="text-lg font-semibold">{title}</h1>
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
