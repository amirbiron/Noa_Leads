"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Sparkles, TrendingUp } from "lucide-react";
import { AiSummaryCard } from "@/components/AiSummaryCard";
import { AppShell } from "@/components/AppShell";
import { useDashboardPollContext } from "@/components/DashboardPollProvider";
import { EmptyState } from "@/components/EmptyState";
import { LeadCardRow } from "@/components/LeadCardRow";
import { SectionHeader } from "@/components/SectionHeader";
import { TodayActionRow } from "@/components/TodayActionRow";
import { api, ApiError } from "@/lib/api";
import { shouldShowAiWeeklySummary, shouldShowDailySummary } from "@/lib/date";
import { labelCategory } from "@/lib/hebrew";
import type { HomeDashboard } from "@/lib/types";

// סיכום יומי — AI נרטיבי בלבד. הסיכום הסטטיסטי (DailySummaryBubble) הוסר
// מה-UI לפי החלטת מוצר; הקומפוננטה נשארת בקוד אם יחזרו אליה.

export default function HomePage() {
  const [data, setData] = useState<HomeDashboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  // ברירת מחדל: הסיכום היומי לא מוצג כלל (אפילו לא מקופל). לחיצה על
  // ה-badge "סיכום יומי" בכותרת חושפת אותו. session-scoped — ביקור חדש
  // מתחיל שוב מ-hidden. אם רוצים persist, להעביר ל-localStorage.
  const [showDailySummary, setShowDailySummary] = useState(false);
  // הערך לא בשימוש — רק מאלץ re-render דקתי כדי שבועת הסיכום תיעלם
  // אוטומטית ב-07:00 (§12.4), ראה ה-useEffect של הטיימר למטה.
  const [, setMinuteTick] = useState(0);

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

  // טיימר דקתי — מאלץ re-render כדי שבועת הסיכום היומי תיעלם אוטומטית
  // ב-07:00 (§12.4) גם אם העמוד נשאר פתוח בלי רענון. לא משתמשים ב-pollVersion
  // כי הוא עולה רק על delta מהשרת (לידים חדשים) — בלילה שקט הוא לא יזוז.
  // העלות זניחה (setState ריק כל דקה); אין fetch.
  useEffect(() => {
    const id = setInterval(() => setMinuteTick((t) => t + 1), 60_000);
    return () => clearInterval(id);
  }, []);

  // C.1/C.2 §6.8: badge מוצג כשיש סיכום יומי AI בחלון.
  const hasAiDailyInWindow =
    !!data?.ai_daily_summary &&
    shouldShowDailySummary(data.ai_daily_summary.date_range_end);
  const hasWeeklyInWindow =
    !!data?.ai_weekly_summary &&
    shouldShowAiWeeklySummary(data.ai_weekly_summary.date_range_end);

  // ה-badge "סיכום יומי" — לחיצה חושפת את AiSummaryCard. ברירת מחדל
  // hidden לחלוטין; כל לחיצה מציבה showDailySummary=true. הbadge עצמו
  // נשאר מוצג גם אחרי החשיפה (לא מתחלף ל"סגור"), אבל לחיצה חוזרת
  // לא עושה כלום (state כבר true) — תואם לבקשת המשתמשת "לחיצה מראה".
  const dailyTogglePill = hasAiDailyInWindow ? (
    <button
      type="button"
      onClick={() => setShowDailySummary(true)}
      aria-label="פתח סיכום יומי"
      className="rounded-full bg-indigo-50 hover:bg-indigo-100 text-indigo-700 text-xs font-medium px-3 py-1 flex items-center gap-1"
    >
      <Sparkles size={12} aria-hidden />
      <span>סיכום יומי</span>
    </button>
  ) : null;

  return (
    <AppShell title="בית" headerActions={dailyTogglePill}>
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
          {/* C.1/C.2 §6.8: סיכומי הבית.
              - Daily slot: AI נרטיבי בלבד (C.1). חלון 19:00→07:00.
                **ברירת מחדל: מוסתר לחלוטין.** ה-badge "סיכום יומי" בכותרת
                חושף — showDailySummary controls visibility.
              - Weekly slot: AI נרטיבי, חלון ראשון 08:00→שני 07:00. פתוח
                כברירת מחדל (קיפול פנימי דרך chevron + localStorage).
              Stacked בכל הbreakpoints: Daily מעל Weekly. */}

          {((showDailySummary && hasAiDailyInWindow) || hasWeeklyInWindow) && (
            <div className="flex flex-col gap-3 lg:gap-4 mb-3">
              {showDailySummary && hasAiDailyInWindow && (
                <AiSummaryCard
                  summary={data.ai_daily_summary!}
                  collapsible
                />
              )}

              {hasWeeklyInWindow && (
                <AiSummaryCard
                  summary={data.ai_weekly_summary!}
                  collapsible
                />
              )}
            </div>
          )}

          {/* פעולות היום */}
          <SectionHeader
            title={
              data.today_actions.length > 0
                ? `${data.today_actions.length} משימות מחכות לך היום`
                : "אין משימות דחופות היום"
            }
            termKey="page_today"
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
                    {/* hideStatus: כל הפניות כאן NEW — "חדש" מיותר (§12.1). */}
                    <LeadCardRow lead={lead} hideStatus />
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
                termKey="page_pending"
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
