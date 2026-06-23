"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AlertTriangle, CalendarRange, Sparkles, TrendingUp, UserPlus } from "lucide-react";
import { AiSummaryCard } from "@/components/AiSummaryCard";
import { AppShell } from "@/components/AppShell";
import { useDashboardPollContext } from "@/components/DashboardPollProvider";
import { SectionHeader } from "@/components/SectionHeader";
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
  // ברירת מחדל: שני הסיכומים (יומי + שבועי) לא מוצגים כלל. כל badge
  // בכותרת מתפקד כ-toggle: click → show, click again → hide.
  // session-scoped — ביקור חדש מתחיל שוב מ-hidden. אם רוצים persist,
  // להעביר ל-localStorage.
  const [showDailySummary, setShowDailySummary] = useState(false);
  const [showWeeklySummary, setShowWeeklySummary] = useState(false);
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

  // ה-badges בכותרת — toggle של כל סיכום בנפרד. visual feedback:
  // כש-active (הסיכום מוצג) → רקע מלא + טקסט לבן. כש-inactive →
  // רקע מואר + טקסט צבעוני. aria-pressed מסמן את המצב לקוראי מסך.
  const dailyTogglePill = hasAiDailyInWindow ? (
    <button
      type="button"
      onClick={() => setShowDailySummary((v) => !v)}
      aria-label={showDailySummary ? "סגור סיכום יומי" : "פתח סיכום יומי"}
      aria-pressed={showDailySummary}
      className={`rounded-full text-xs font-medium px-3 py-1 flex items-center gap-1 ${
        showDailySummary
          ? "bg-indigo-600 hover:bg-indigo-700 text-white"
          : "bg-indigo-50 hover:bg-indigo-100 text-indigo-700"
      }`}
    >
      <Sparkles size={12} aria-hidden />
      <span>סיכום יומי</span>
    </button>
  ) : null;

  const weeklyTogglePill = hasWeeklyInWindow ? (
    <button
      type="button"
      onClick={() => setShowWeeklySummary((v) => !v)}
      aria-label={showWeeklySummary ? "סגור סיכום שבועי" : "פתח סיכום שבועי"}
      aria-pressed={showWeeklySummary}
      className={`rounded-full text-xs font-medium px-3 py-1 flex items-center gap-1 ${
        showWeeklySummary
          ? "bg-emerald-600 hover:bg-emerald-700 text-white"
          : "bg-emerald-50 hover:bg-emerald-100 text-emerald-700"
      }`}
    >
      <CalendarRange size={12} aria-hidden />
      <span>סיכום שבועי</span>
    </button>
  ) : null;

  // שני ה-badges ב-headerActions. weekly לפני daily כי בעברית RTL
  // הוא יופיע אחרי daily ב-flex (הקצה ה"פנימי" הוא ראשון), וזה
  // נראה טבעי: יומי קרוב יותר לכותרת (מימין), שבועי במרחק (משמאל).
  const summaryToggles = (dailyTogglePill || weeklyTogglePill) ? (
    <div className="flex items-center gap-2">
      {weeklyTogglePill}
      {dailyTogglePill}
    </div>
  ) : null;

  return (
    <AppShell title="בית" headerActions={summaryToggles}>
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
              - Daily slot: AI נרטיבי. חלון 19:00→07:00.
                **ברירת מחדל: מוסתר.** ה-badge "סיכום יומי" toggle.
              - Weekly slot: AI נרטיבי. חלון ראשון 08:00→שני 07:00.
                **ברירת מחדל: מוסתר.** ה-badge "סיכום שבועי" toggle.
              שני הסיכומים מוסתרים עד שהמשתמשת לוחצת על ה-badge המתאים.
              Stacked בכל הbreakpoints: Daily מעל Weekly. */}

          {((showDailySummary && hasAiDailyInWindow) ||
            (showWeeklySummary && hasWeeklyInWindow)) && (
            <div className="flex flex-col gap-3 lg:gap-4 mb-3">
              {showDailySummary && hasAiDailyInWindow && (
                <AiSummaryCard summary={data.ai_daily_summary!} />
              )}

              {showWeeklySummary && hasWeeklyInWindow && (
                <AiSummaryCard summary={data.ai_weekly_summary!} />
              )}
            </div>
          )}

          {/* "לוח בוקר" — בלוקי סטטוס + פעולה.
              Block 1 (פגישות מהיומן) יבוא ב-PR נפרד אחרי שאינטגרציית
              היומן תתייצב; כאן 2 בלוקים, הגריד יעבור ל-cols-3 בעתיד. */}
          <MorningBlocks
            newLeadsCount={data.new_leads_24h_count}
            urgentCount={data.urgent_no_first_response_count}
          />

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

// "לוח בוקר" — 2 בלוקי סטטוס + פעולה. כל בלוק = מספר גדול + label +
// כפתור כניסה לדף הייעודי. גריד 2 עמודות (Block 1 יתווסף ב-PR הבא).
function MorningBlocks({
  newLeadsCount,
  urgentCount,
}: {
  newLeadsCount: number;
  urgentCount: number;
}) {
  return (
    <div className="grid grid-cols-2 gap-3 mb-4">
      {/* Block 2: לידים חדשים (24h) — מד נפח, כפתור לטאב הלידים */}
      <Link
        href="/leads"
        className="block bg-white rounded-xl border border-gray-200 p-4 hover:border-indigo-300 hover:shadow-sm active:opacity-70 transition"
      >
        <div className="flex items-center gap-2 text-indigo-600 mb-2">
          <UserPlus size={18} aria-hidden />
          <span className="text-xs font-medium">פניות חדשות (24 שעות)</span>
        </div>
        <div className="text-3xl font-bold text-gray-900 tabular-nums">
          {newLeadsCount}
        </div>
        <div className="text-xs text-gray-500 mt-1">לכל הלידים ←</div>
      </Link>

      {/* Block 3: דחוף — ללא מענה ראשון 48h+. כפתור ל-/today (שם
          ה-FIRST_RESPONSE/LECTURE_INQUIRY overdue כבר מופיעים עם כפתורי
          one-tap טלפון/וואטסאפ/מייל). */}
      <Link
        href="/today"
        className={`block rounded-xl border p-4 hover:shadow-sm active:opacity-70 transition ${
          urgentCount > 0
            ? "bg-state-red/5 border-state-red/30 hover:border-state-red/50"
            : "bg-white border-gray-200 hover:border-state-red/20"
        }`}
      >
        <div
          className={`flex items-center gap-2 mb-2 ${urgentCount > 0 ? "text-state-red" : "text-gray-500"}`}
        >
          <AlertTriangle size={18} aria-hidden />
          <span className="text-xs font-medium">דחוף — ללא מענה 48 שעות</span>
        </div>
        <div
          className={`text-3xl font-bold tabular-nums ${urgentCount > 0 ? "text-state-red" : "text-gray-900"}`}
        >
          {urgentCount}
        </div>
        <div className="text-xs text-gray-500 mt-1">
          {urgentCount > 0 ? "טפלי עכשיו ←" : "אין דחופים ✓"}
        </div>
      </Link>
    </div>
  );
}
