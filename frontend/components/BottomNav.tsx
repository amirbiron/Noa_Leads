"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Archive,
  CalendarClock,
  FileText,
  Home,
  Inbox,
  Users,
} from "lucide-react";
import { cn } from "@/lib/utils";

// ניווט תחתון מובייל-first — כפתורים גדולים, נגישים לאגודל.
// "הצעות" נגישות מדף הבית; "ממתין" מקבל מקום קבוע כי שם הולכים פולואפים.
// "ארכיון" — גישה ללידים סגורים (WON/LOST/ARCHIVED), §12.12.
const ITEMS = [
  { href: "/", label: "בית", icon: Home },
  { href: "/today", label: "היום", icon: CalendarClock },
  { href: "/leads", label: "לידים", icon: Users },
  { href: "/pending", label: "ממתין", icon: Inbox },
  { href: "/templates", label: "תבניות", icon: FileText },
  { href: "/archive", label: "ארכיון", icon: Archive },
];

export function BottomNav() {
  const pathname = usePathname();
  return (
    <nav
      className="fixed bottom-0 inset-x-0 z-30 bg-white border-t border-gray-200 pb-safe"
      dir="rtl"
    >
      <ul className="flex items-stretch justify-around">
        {ITEMS.map(({ href, label, icon: Icon }) => {
          const active =
            href === "/"
              ? pathname === "/"
              : pathname === href || pathname.startsWith(href + "/");
          return (
            <li key={href} className="flex-1">
              <Link
                href={href}
                className={cn(
                  "flex flex-col items-center gap-1 py-2.5 text-xs",
                  active ? "text-gray-900" : "text-gray-400",
                )}
              >
                <Icon
                  size={22}
                  strokeWidth={active ? 2.4 : 1.8}
                  aria-hidden
                />
                <span>{label}</span>
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
