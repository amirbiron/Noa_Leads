import type { Metadata } from "next";
import { Heebo } from "next/font/google";
import { DashboardPollProvider } from "@/components/DashboardPollProvider";
import "./globals.css";

// פונט עברי מ-Google Fonts
const heebo = Heebo({
  subsets: ["hebrew", "latin"],
  variable: "--font-heebo",
  display: "swap",
});

export const metadata: Metadata = {
  title: "ניהול לידים — נועה",
  description: "מערכת ניהול לידים ולקוחות",
  // המערכת נכנסת אוטומטית ללא סיסמה, ודף קביעת הפגישה מוגן בטוקן
  // שב-URL בלבד. שניהם לא אמורים להופיע בתוצאות חיפוש.
  // שכבה 2 מתוך 3 — ראה `app/robots.ts` להסבר על כל השכבות.
  robots: { index: false, follow: false },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="he" dir="rtl" className={heebo.variable}>
      <body>
        {/* polling אוטומטי לדשבורד — ה-hook בפנים גוארד ב-isLoggedIn()
            כך שלא רץ ב-/login, /booking/*, או לפני התחברות. */}
        <DashboardPollProvider>{children}</DashboardPollProvider>
      </body>
    </html>
  );
}
