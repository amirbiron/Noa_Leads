"use client";

import { Moon } from "lucide-react";
import { computeDailySummaryStaleness } from "@/lib/date";
import { useLocalStorageState } from "@/lib/useLocalStorage";
import type { DailySummary } from "@/lib/types";
import { CollapseToggleButton } from "./CollapseToggleButton";

// F-07 (Spec §16.3 + Changelog v2.1): סיכום יומי סטטיסטי מ-`daily_summaries`
// מוצג כ-bubble בדשבורד. *לא* נשלח לטלגרם — הדשבורד הוא הערוץ היחיד.
// חלון התצוגה מנוהל מבחוץ (`shouldShowDailySummary`) — הקומפוננטה רק
// מציגה את הנתונים שניתנו לה.
//
// `collapsible` (C.1/C.2 §6.8): כפתור chevron בכל הbreakpoints (גם
// דסקטופ). מצב הקיפול נשמר ב-localStorage תחת
// `noa:summary:daily:collapsed` — אותו key של AiSummaryCard עם type=daily,
// כי שני הקומפוננטות מציגות את אותו Daily slot שמתחלף לפי toggle.
export function DailySummaryBubble({
  summary,
  collapsible = false,
}: {
  summary: DailySummary;
  collapsible?: boolean;
}) {
  // hardcoded ל-"daily" — slot זה תמיד יומי, וה-key חולק עם AiSummaryCard
  // (type=daily) כדי שמצב הקיפול יישמר בעת toggle statistical↔AI.
  const [collapsed, setCollapsed] = useLocalStorageState(
    "noa:summary:daily:collapsed",
    false,
  );

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
              <CollapseToggleButton
                collapsed={collapsed}
                onToggle={() => setCollapsed(!collapsed)}
              />
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
