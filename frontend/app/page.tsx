"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Moon, Sparkles, TrendingUp } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { useDashboardPollContext } from "@/components/DashboardPollProvider";
import { EmptyState } from "@/components/EmptyState";
import { LeadCardRow } from "@/components/LeadCardRow";
import { SectionHeader } from "@/components/SectionHeader";
import { TodayActionRow } from "@/components/TodayActionRow";
import { api, ApiError } from "@/lib/api";
import { plusOneIsoDate, toIsraelISODate } from "@/lib/date";
import { labelCategory } from "@/lib/hebrew";
import type { DailySummary, HomeDashboard } from "@/lib/types";

export default function HomePage() {
  const [data, setData] = useState<HomeDashboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  async function load() {
    setError(null);
    try {
      const d = await api.getHome();
      setData(d);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "שגיאה בטעינה");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  // auto-refresh כשהפולינג זיהה לידים חדשים / תגובות. ה-pollVersion
  // עולה רק כש-delta non-empty, אז אין רענון מיותר.
  const { pollVersion } = useDashboardPollContext();
  useEffect(() => {
    if (pollVersion === 0) return; // השינוי הראשוני (mount) כבר טוען
    void load();
  }, [pollVersion]);

  return (
    <AppShell title="בית">
      {loading && (
        <div className="text-center text-gray-400 py-10 text-sm">טוען…</div>
      )}

      {error && (
        <div className="text-sm text-state-red bg-state-red/10 rounded-lg px-3 py-2">
          {error}
        </div>
      )}

      {data && (
        <>
          {/* F-07: סיכום יומי — bubble. נשמר ב-daily_summaries ע"י cron 19:00.
              לפי Spec §16.2: לא נשלח לטלגרם — מוצג רק בדשבורד. */}
          {data.daily_summary && (
            <DailySummaryBubble summary={data.daily_summary} />
          )}

          {/* פעולות היום */}
          <SectionHeader
            title={
              data.today_actions.length > 0
                ? `${data.today_actions.length} משימות מחכות לך היום`
                : "אין משימות דחופות היום"
            }
          />
          {data.today_actions.length === 0 ? (
            <EmptyState
              title="אין משימות דחופות היום"
              hint="אפשר להתחיל את היום ברוגע ✓"
              icon={<Sparkles size={24} aria-hidden />}
            />
          ) : (
            <ul className="space-y-2">
              {data.today_actions.map((item) => (
                <li key={item.task_id}>
                  <TodayActionRow item={item} onChanged={load} />
                </li>
              ))}
            </ul>
          )}

          {/* פניות חדשות */}
          {data.new_leads.length > 0 && (
            <>
              <SectionHeader
                title="פניות חדשות שעוד לא ענית עליהן"
                count={data.new_leads.length}
              />
              <ul className="space-y-2">
                {data.new_leads.map((lead) => (
                  <li key={lead.id}>
                    <LeadCardRow lead={lead} />
                  </li>
                ))}
              </ul>
            </>
          )}

          {/* ממתין לטיפול */}
          {data.pending.length > 0 && (
            <>
              <SectionHeader
                title="ממתין לטיפול"
                count={data.pending.length}
              />
              <ul className="space-y-2">
                {data.pending.map((lead) => (
                  <li key={lead.id}>
                    <LeadCardRow lead={lead} />
                  </li>
                ))}
              </ul>
            </>
          )}

          {/* תובנות השבוע */}
          <SectionHeader title="תובנות השבוע" />
          <div className="bg-white rounded-xl border border-gray-200 p-4">
            <div className="grid grid-cols-3 gap-3 text-center">
              <Stat
                value={data.weekly_insights.new_leads_count}
                label="נכנסו השבוע"
              />
              <Stat
                value={data.weekly_insights.responded_in_time_count}
                label="קיבלו מענה בזמן"
              />
              {/* תובנת §13.9 — תצוגה בלבד. ה-stat הזה סופר *כל* ליד שעבר
                  due_at (אפילו יום אחד), ואילו /tasks/stuck מציג רק 7+ ימים
                  לפי §22.7 + §16.2. קישור ישיר היה מבלבל כי המספר וה-list
                  לא היו מתאימים. הקישור הנפרד למטה מוביל לחתך ה-7+ ימים. */}
              <Stat
                value={data.weekly_insights.stuck_count}
                label="לא טופלו בזמן"
                tone={data.weekly_insights.stuck_count > 0 ? "red" : "gray"}
              />
            </div>
            {/* כניסה לעמוד "ממתין לטיפול" — חתך מצומצם של הלידים שתקועים
                7+ ימים (Spec §22.7). זמין תמיד מהדשבורד, גם אם stuck_count=0
                (העמוד יראה empty state). זה ה-entry point היחיד למסך הזה. */}
            <Link
              href="/tasks/stuck"
              className="mt-3 flex items-center justify-center gap-1 text-xs text-gray-600 hover:text-gray-900 py-1 active:opacity-70"
            >
              צפי במשימות תקועות (7+ ימים) ←
            </Link>
          </div>

          {/* "השעה הרווחית שלך השבוע" — תובנה עסקית מהאפיון */}
          {data.weekly_insights.most_profitable_service && (
            <div className="mt-3 bg-gradient-to-bl from-state-green/10 to-state-green/5 border border-state-green/30 rounded-xl p-4">
              <div className="flex items-start gap-3">
                <TrendingUp
                  size={20}
                  className="text-state-green shrink-0 mt-0.5"
                  aria-hidden
                />
                <div className="min-w-0">
                  <div className="text-xs text-gray-600 mb-0.5">
                    השעה הרווחית שלך השבוע
                  </div>
                  <div className="font-semibold text-base">
                    {labelCategory(
                      data.weekly_insights.most_profitable_service
                        .service_category,
                    )}
                  </div>
                  <div className="text-2xl font-bold text-state-green tabular-nums mt-1">
                    {Math.round(
                      Number(
                        data.weekly_insights.most_profitable_service
                          .hourly_rate,
                      ),
                    ).toLocaleString("he-IL")}{" "}
                    <span className="text-sm font-normal text-gray-500">
                      ₪/שעה
                    </span>
                  </div>
                  <div className="text-xs text-gray-500 mt-1">
                    {data.weekly_insights.most_profitable_service.deals_count}{" "}
                    עסקאות ·{" "}
                    {Number(
                      data.weekly_insights.most_profitable_service.total_hours,
                    ).toLocaleString("he-IL")}{" "}
                    שעות עבודה
                  </div>
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </AppShell>
  );
}

function DailySummaryBubble({ summary }: { summary: DailySummary }) {
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
  // get_latest_daily_summary מחזיר את הסיכום של אתמול. בלי label דינמי
  // המשתמש רואה "סיכום יומי · יום שני 25 במאי" ביום שלישי בבוקר וחושב
  // שזה היום (בלבול שדווח). מציינים מפורשות "אתמול" / "היום" / תאריך מלא.
  // השוואת תאריכים ב-Asia/Jerusalem TZ כדי שלא תהיה הזזה בלילה.
  const isStale = computeIsStale(summary.summary_date);
  const titlePrefix = isStale === "today"
    ? "סיכום היום"
    : isStale === "yesterday"
      ? "סיכום אתמול"
      : "סיכום";
  return (
    <div className="bg-gradient-to-bl from-indigo-500/10 to-indigo-500/5 border border-indigo-300/40 rounded-xl p-4">
      <div className="flex items-start gap-3">
        <Moon
          size={20}
          className="text-indigo-500 shrink-0 mt-0.5"
          aria-hidden
        />
        <div className="min-w-0 w-full">
          <div className="text-xs text-gray-600 mb-1">
            {titlePrefix} · {dateLabel}
          </div>
          <div className="grid grid-cols-2 gap-2 mt-2">
            <SummaryStat
              value={summary.new_leads_today}
              label="פניות חדשות"
            />
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
        </div>
      </div>
    </div>
  );
}

// משווה summary_date (YYYY-MM-DD מ-Israel TZ ב-backend) לתאריך הנוכחי
// ב-Asia/Jerusalem. שני העזר (toIsraelISODate, plusOneIsoDate) ב-
// `lib/date.ts` — מתועדים שם, כולל ההיגיון מאחורי options מפורשות
// ו-UTC arithmetic.
function computeIsStale(
  summaryDate: string,
): "today" | "yesterday" | "older" {
  const todayIsrael = toIsraelISODate();
  if (summaryDate === todayIsrael) return "today";
  if (plusOneIsoDate(summaryDate) === todayIsrael) return "yesterday";
  return "older";
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

function Stat({
  value,
  label,
  tone = "gray",
}: {
  value: number;
  label: string;
  tone?: "gray" | "red";
}) {
  return (
    <div>
      <div
        className={`text-2xl font-semibold ${tone === "red" ? "text-state-red" : "text-gray-900"}`}
      >
        {value}
      </div>
      <div className="text-xs text-gray-500 mt-0.5">{label}</div>
    </div>
  );
}
