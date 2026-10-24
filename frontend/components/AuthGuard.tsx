"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { enterPublicAccess } from "@/lib/api";
import { isLoggedIn } from "@/lib/auth";

// שומר על הדפים המאומתים. אין יותר מסך התחברות — פתיחת הכתובת היא
// הכניסה: אם אין token, מבקשים אחד מהשרת ונכנסים כנועה.
//
// שני מצבי קצה שמטופלים כאן:
// - DB ריק (לפני התקנה) → `/auth/public-access` מחזיר 401 כי אין
//   owner, ואנחנו מפנים ל-`/setup` ליצירת המשתמש הראשון.
// - הכניסה נכשלה מסיבה אחרת → מסך שגיאה בעברית, **בלי** רענון עצמי
//   ובלי הפניה חוזרת. דף שמנסה להיכנס שוב ושוב בלולאה גרוע ממסך
//   שאומר מה קרה.
export function AuthGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  // הערך ההתחלתי חייב להיות קבוע ולא תלוי ב-localStorage: את ה-HTML
  // הראשוני מייצר השרת, ושם אין localStorage. אתחול שקורא token היה
  // נותן "ready" בדפדפן מול "checking" בשרת — hydration mismatch
  // (React error #418), ו-React זורק את ה-HTML של השרת ומרנדר מחדש.
  // הבדיקה בפועל נעשית ב-useEffect, שרץ רק בדפדפן.
  const [state, setState] = useState<"checking" | "ready" | "failed">(
    "checking",
  );

  useEffect(() => {
    if (state !== "checking") return;
    // כבר יש token — אין סיבה לבקש אחד חדש בכל טעינת דף.
    if (isLoggedIn()) {
      setState("ready");
      return;
    }
    // דגל ביטול: הקומפוננטה עלולה להתפרק בזמן שהבקשה באוויר.
    let cancelled = false;
    (async () => {
      const entered = await enterPublicAccess();
      if (cancelled) return;
      if (entered) {
        setState("ready");
        return;
      }
      // אין owner → צריך התקנה ראשונית. `/setup` בודק את זה בעצמו
      // ומפנה הלאה אם כבר יש משתמש, אז אין כאן סיכון ללולאה.
      const { setup_needed } = await import("@/lib/api").then((m) =>
        m.api.getSetupStatus().catch(() => ({ setup_needed: false })),
      );
      if (cancelled) return;
      if (setup_needed) {
        router.replace("/setup");
        return;
      }
      setState("failed");
    })();
    return () => {
      cancelled = true;
    };
  }, [state, router]);

  if (state === "checking") {
    return (
      <div className="min-h-screen flex items-center justify-center text-gray-400 text-sm">
        טוען…
      </div>
    );
  }

  if (state === "failed") {
    return (
      <div className="min-h-screen flex items-center justify-center p-6">
        <div className="bg-white rounded-2xl border border-gray-200 max-w-sm w-full p-6 text-center space-y-2">
          <div className="text-lg font-semibold">לא הצלחנו להיכנס למערכת</div>
          <p className="text-sm text-gray-600">
            נסי לרענן את הדף. אם זה חוזר, צרי קשר עם המתאם.
          </p>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
