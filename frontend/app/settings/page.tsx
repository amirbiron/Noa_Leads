"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  ChevronLeft,
  Coins,
  FileText,
  LogOut,
  Send,
  Sparkles,
} from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { GmailConnectionSection } from "@/components/GmailConnectionSection";
import { GoogleCalendarSection } from "@/components/GoogleCalendarSection";
import { SectionHeader } from "@/components/SectionHeader";
import { api, ApiError } from "@/lib/api";
import { clearTokens } from "@/lib/auth";
import type { User } from "@/lib/types";

const FOLLOWUP_RULES = [
  { label: "פולואפ הצעה תקועה", value: "אחרי 3 ימים ללא תגובה" },
  { label: "סימון ליד רדום", value: "60 ימים ללא אינטראקציה" },
  { label: "סוף יום עבודה", value: "שישי 16:00 — ערב חג גם" },
  { label: "סיכום יומי לטלגרם", value: "כל יום 19:00" },
  { label: "סיכום שבועי", value: "ראשון 08:00" },
];

const ROLE_LABEL: Record<string, string> = {
  owner: "בעלים",
  assistant: "עוזרת",
};

export default function SettingsPage() {
  const router = useRouter();
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

  function handleLogout() {
    if (!confirm("להתנתק מהמערכת?")) return;
    // התנתקות מקומית: מחיקת tokens. הקריאה ל-/auth/logout אופציונלית
    // כי השרת stateless עם JWT.
    void api.logout().catch(() => {}); // best-effort
    clearTokens();
    router.replace("/login");
  }

  return (
    <AppShell title="הגדרות" hideSettings>
      {loading && (
        <div className="text-center text-gray-400 py-10 text-sm">טוען…</div>
      )}
      {error && (
        <div className="text-sm text-state-red bg-state-red/10 rounded-lg px-3 py-2 mb-3">
          {error}
        </div>
      )}

      {me && (
        <div className="bg-white rounded-xl border border-gray-200 p-4">
          <div className="text-xs text-gray-400 mb-0.5">משתמשת מחוברת</div>
          <div className="font-semibold">{me.name}</div>
          <div className="text-sm text-gray-500 mt-0.5">
            {/* dir="ltr" על המייל — אחרת הוא נמצא בטקסט מעורב עם עברית
                והאלגוריתם של bidi עלול להציג את ה-"·" בצד הלא נכון. */}
            <span dir="ltr">{me.email}</span> · {ROLE_LABEL[me.role] ?? me.role}
          </div>
        </div>
      )}

      {/* קישורים */}
      <SectionHeader title="ניהול" />
      <ul className="space-y-2">
        <NavRow href="/templates" icon={<FileText size={18} />} label="תבניות הודעה" />
        <NavRow href="/settings/chips" icon={<Sparkles size={18} />} label="צ'יפים מהירים" />
        {me?.role === "owner" && (
          <NavRow
            href="/settings/rates"
            icon={<Coins size={18} />}
            label="תעריפי שירות"
          />
        )}
        <NavRow href="/proposals" icon={<Send size={18} className="rtl:-scale-x-100" />} label="הצעות פתוחות" />
      </ul>

      {/* אינטגרציות — owner-only: כל מסלולי /google/* דורשים OwnerOnly,
          אז לעוזרת זה היה נראה כשגיאת 403 קבועה במקום אזור מוסתר. */}
      {me?.role === "owner" && (
        <>
          <SectionHeader title="אינטגרציות" />
          <div className="space-y-2">
            <GoogleCalendarSection />
            <GmailConnectionSection />
          </div>
        </>
      )}

      {/* חוקי פולואפ */}
      <SectionHeader
        title="חוקי פולואפ"
        hint="נקבע במערכת — עריכה תתווסף"
      />
      <ul className="bg-white rounded-xl border border-gray-200 divide-y divide-gray-100">
        {FOLLOWUP_RULES.map((r) => (
          <li
            key={r.label}
            className="flex items-baseline justify-between gap-3 px-3.5 py-2.5 text-sm"
          >
            <span className="text-gray-700">{r.label}</span>
            <span className="text-gray-500 text-xs text-end">{r.value}</span>
          </li>
        ))}
      </ul>


      {/* AI status — נכבה תמיד בפאזה 1 */}
      <SectionHeader title="פיצ'רים עתידיים" />
      <div className="bg-white rounded-xl border border-gray-200 p-4">
        <div className="flex items-start gap-3">
          <Sparkles size={18} className="text-gray-300 mt-0.5" aria-hidden />
          <div className="text-sm text-gray-600">
            <div className="font-medium text-gray-700 mb-1">
              סיכומים, ניסוח הצעות, וזיהוי לידים רדומים
            </div>
            <p className="text-xs leading-relaxed">
              שכבת ה-AI תופעל בפאזה 3. גם אז — עוזר בלבד, אף פעם לא שולח
              במקומך.
            </p>
          </div>
        </div>
      </div>

      {/* התנתקות */}
      <div className="mt-6">
        <button
          onClick={handleLogout}
          className="w-full inline-flex items-center justify-center gap-2 bg-white border border-state-red/40 text-state-red rounded-xl py-3 font-medium"
        >
          <LogOut size={18} aria-hidden />
          התנתקות
        </button>
      </div>
    </AppShell>
  );
}

function NavRow({
  href,
  icon,
  label,
}: {
  href: string;
  icon: React.ReactNode;
  label: string;
}) {
  return (
    <li>
      <Link
        href={href}
        className="flex items-center justify-between gap-3 bg-white rounded-xl border border-gray-200 px-3.5 py-3 active:bg-gray-50"
      >
        <span className="flex items-center gap-2.5">
          <span className="text-gray-400">{icon}</span>
          <span className="font-medium text-sm">{label}</span>
        </span>
        <ChevronLeft size={18} className="text-gray-300" aria-hidden />
      </Link>
    </li>
  );
}
