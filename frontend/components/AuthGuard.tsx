"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { isLoggedIn } from "@/lib/auth";

// עוטף עמודים שדורשים auth — מפנה ל-/login אם אין token.
// נמנע מ-rendering של הילדים עד שהבדיקה הסתיימה כדי לא להבליח UI.
export function AuthGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!isLoggedIn()) {
      router.replace("/login");
      return;
    }
    setReady(true);
  }, [router]);

  if (!ready) {
    return (
      <div className="min-h-screen flex items-center justify-center text-gray-400 text-sm">
        טוען…
      </div>
    );
  }
  return <>{children}</>;
}
