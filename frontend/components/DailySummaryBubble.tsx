"use client";

import { useState } from "react";
import { ChevronDown, ChevronUp, Moon } from "lucide-react";
import { computeDailySummaryStaleness } from "@/lib/date";
import type { DailySummary } from "@/lib/types";

// F-07 (Spec §16.3 + Changelog v2.1): סיכום יומי סטטיסטי מ-`daily_summaries`
// מוצג כ-bubble בדשבורד. *לא* נשלח לטלגרם — הדשבורד הוא הערוץ היחיד.
// חלון התצוגה מנוהל מבחוץ (`shouldShowDailySummary`) — הקומפוננטה רק
// מציגה את הנתונים שניתנו לה.
//
// `collapsible` (C.1/C.2 §6.8 — UI מעודכן): במובייל מאפשר לקפל את הכרטיס
// (להציג רק את הכותרת) ולפנות מקום לרשימת המשימות. בדסקטוп הכפתור מוסתר
// כי יש מקום לשני הכרטיסים זה לצד זה.
export function DailySummaryBubble({
  summary,
  collapsible = false,
}: {
  summary: DailySummary;
  collapsible?: boolean;
}) {
  const [collapsed, setCollapsed] = useState(false);

  // summary_date מגיע כ-"YYYY-MM-DD" (date-only). Date(string) מפרסר אותו
  // כ-UTC midnight, מה שגורם להזזת יום כשמשתמש נמצא ב-TZ שלילי. נוסיף
  // T00:00 ונציין timeZone="Asia/Jerusalem" כדי שהיום/חודש/שם-יום יהיו
  // יציבים בכל סביבה.
  const dateLabel = new Date(`${summary.summary_date}T00:00:00`).toLocaleDateString(
    "he-IL",
    {
      weekday: "long",
      day: "numeric",
      month: "long",
      timeZone: "Asia/Jerusalem",
    },
  );

  // ה-cron של 19:00 IL רץ פעם ביום. בבוקר שאחרי (לפני 19:00 הבא),
  // get_latest_daily_summary מחזיר את הסיכום של אתמול. label דינמי כדי
  // שהמשתמש ידע מתי הסיכום נוצר (אחרת בלבול דווח).
  const staleness = computeDailySummaryStaleness(summary.summary_date);
  const titlePrefix =
    staleness === "today"
      ? "סיכום היום"
      : staleness === "yesterday"
        ? "סיכום אתמול"
        : "סיכום";

  return (
    <div className="bg-gradient-to-bl from-indigo-500/10 to-indigo-500/5 border border-indigo-300/40 rounded-xl p-4 lg:flex-1">
      <div className="flex items-start gap-3">
        <Moon
          size={20}
          className="text-indigo-500 shrink-0 mt-0.5"
          aria-hidden
        />
        <div className="min-w-0 w-full">
          <div className="flex items-center justify-between gap-2">
            <div className="text-xs text-gray-600">
              {titlePrefix} · {dateLabel}
            </div>
            {collapsible && (
              <button
                type="button"
                onClick={() => setCollapsed((c) => !c)}
                aria-label={collapsed ? "הרחב סיכום" : "קפל סיכום"}
                aria-expanded={!collapsed}
                className="lg:hidden p-1 -m-1 text-gray-500 hover:text-gray-800"
              >
                {collapsed ? (
                  <ChevronDown size={16} aria-hidden />
                ) : (
                  <ChevronUp size={16} aria-hidden />
                )}
              </button>
            )}
          </div>
          {!collapsed && (
            <div className="grid grid-cols-2 gap-2 mt-2">
              <SummaryStat value={summary.new_leads_today} label="פניות חדשות" />
              <SummaryStat
                value={summary.tasks_done_today}
                label="משימות שבוצעו"
              />
              <SummaryStat
                value={summary.tasks_for_tomorrow}
                label="משימות ליום שאחרי"
              />
              <SummaryStat
                value={summary.urgent_open}
                label="לידים דחופים פתוחים"
                tone={summary.urgent_open > 0 ? "red" : "gray"}
              />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function SummaryStat({
  value,
  label,
  tone = "gray",
}: {
  value: number;
  label: string;
  tone?: "gray" | "red";
}) {
  return (
    <div className="bg-white/60 rounded-lg px-3 py-2">
      <div
        className={`text-xl font-semibold tabular-nums ${tone === "red" ? "text-state-red" : "text-gray-900"}`}
      >
        {value}
      </div>
      <div className="text-[11px] text-gray-500 mt-0.5">{label}</div>
    </div>
  );
}
