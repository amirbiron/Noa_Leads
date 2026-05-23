import type { Metadata } from "next";
import { Heebo } from "next/font/google";
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
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="he" dir="rtl" className={heebo.variable}>
      <body>{children}</body>
    </html>
  );
}
