"use client";

import { useEffect, useState } from "react";
import { CalendarRange, Sparkles, ThumbsDown } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { EXPAND_DAILY_SUMMARY_EVENT } from "@/lib/dailySummaryEvents";
import { parseSummaryText } from "@/lib/parseSummaryText";
import { useLocalStorageState } from "@/lib/useLocalStorage";
import type {
  AiSummary,
  AiSummaryOutputDaily,
  AiSummaryOutputWeekly,
} from "@/lib/types";
import { CollapseToggleButton } from "./CollapseToggleButton";

// C.1/C.2 §6.8: כרטיס סיכום AI נרטיבי (יומי/שבועי). מתנהג זהה לשני הסוגים,
// אבל מציג סקציות שונות לפי `summary.type`.
//
// **omitted_sections**: §3.3 / §5.x — סקציות שהושמטו ע"י ה-AI לא מוצגות
// (לא נכלל בהן בלוק ריק). הגנה כפולה: גם בודקים `omitted_sections`, וגם
// בודקים שהשדה עצמו לא ריק (כי במקרה הבסיסי `(string|null) === null`
// ו-`array.length === 0` כבר מוסתרים).
//
// **כפתור "לא מדויק" (§3.7)**: לחיצה → POST ל-endpoint שמעלה
// inaccurate_count ב-1. feedback ויזואלי קצר. counter פנימי (לא מוצג).
//
// **collapsible**: כפתור chevron בכל הbreakpoints (גם דסקטופ). מצב
// הקיפול נשמר ב-localStorage תחת `noa:summary:{type}:collapsed` —
// לפי slot, חולק עם DailySummaryBubble (Daily slot) ועם רענונים/
// breakpoints.

type SubmitState = "idle" | "submitting" | "done" | "error";

export function AiSummaryCard({
  summary,
  collapsible = false,
}: {
  summary: AiSummary;
  collapsible?: boolean;
}) {
  // key נגזר מ-summary.type — `noa:summary:daily:collapsed` או
  // `noa:summary:weekly:collapsed`. ברירת המחדל ל-daily: מקופל
  // (החלטת מוצר — חוסך מקום, הbadge בכותרת פותח). שבועי נשאר פתוח
  // כברירת מחדל כי אין badge מתאים.
  const [collapsed, setCollapsed] = useLocalStorageState(
    `noa:summary:${summary.type}:collapsed`,
    summary.type === "daily",
  );

  // האזנה ל-`noa:expand-daily-summary` — נורה מהbadge "סיכום יומי" בכותרת
  // ה-AppShell בעמוד הבית. פותח את כרטיס הסיכום היומי גם אם נשמר במצב
  // מקופל ב-localStorage. רק לכרטיס "daily" — שבועי מתעלם.
  useEffect(() => {
    if (summary.type !== "daily") return;
    function onExpand() {
      setCollapsed(false);
    }
    window.addEventListener(EXPAND_DAILY_SUMMARY_EVENT, onExpand);
    return () =>
      window.removeEventListener(EXPAND_DAILY_SUMMARY_EVENT, onExpand);
  }, [summary.type, setCollapsed]);
  // אם collapsible=false, אסור לערך השמור ב-localStorage לחסום את ה-body —
  // הכפתור מוסתר וה-משתמשת לא יכולה לפתוח. ה-state עדיין נשמר ל-mode
  // הבא בו collapsible=true.
  const isCollapsed = collapsible && collapsed;
  const [submitState, setSubmitState] = useState<SubmitState>("idle");

  const isDaily = summary.type === "daily";
  const titlePrefix = isDaily ? "סיכום יומי" : "סיכום שבועי";
  const Icon = isDaily ? Sparkles : CalendarRange;
  const accentColor = isDaily ? "indigo" : "emerald";

  // Tailwind requires literal class names — לא להשתמש ב-`bg-${color}-X`.
  const wrapperClass = isDaily
    ? "bg-gradient-to-bl from-indigo-500/10 to-indigo-500/5 border-indigo-300/40 text-indigo-500"
    : "bg-gradient-to-bl from-emerald-500/10 to-emerald-500/5 border-emerald-300/40 text-emerald-600";

  async function handleInaccurate() {
    if (submitState !== "idle") return;
    setSubmitState("submitting");
    try {
      await api.markAiSummaryInaccurate(summary.id);
      setSubmitState("done");
    } catch (err) {
      // לוג בקונסולה, ולא מציגים פירוט למשתמש (כלל 3).
      console.error("markAiSummaryInaccurate failed", err);
      setSubmitState(err instanceof ApiError ? "error" : "error");
    }
  }

  return (
    <div
      className={`border rounded-xl p-4 ${wrapperClass.replace("text-indigo-500", "").replace("text-emerald-600", "")}`}
    >
      <div className="flex items-start gap-3">
        <Icon
          size={20}
          className={`shrink-0 mt-0.5 ${isDaily ? "text-indigo-500" : "text-emerald-600"}`}
          aria-hidden
        />
        <div className="min-w-0 w-full">
          <div className="flex items-center justify-between gap-2">
            <div className="text-xs text-gray-600">{titlePrefix}</div>
            {collapsible && (
              <CollapseToggleButton
                collapsed={isCollapsed}
                onToggle={() => setCollapsed(!isCollapsed)}
              />
            )}
          </div>

          {/* bottom_line (תמיד) — headline מודגש. parseSummaryText מהפך
              markers `[[lead:<uuid>|<text>]]` ל-<Link> ל-/leads/<uuid>. */}
          <div className="text-sm font-semibold text-gray-900 mt-1.5">
            {parseSummaryText(summary.output.bottom_line)}
          </div>

          {!isCollapsed && (
            <>
              {isDaily ? (
                <DailyBody output={summary.output as AiSummaryOutputDaily} />
              ) : (
                <WeeklyBody output={summary.output as AiSummaryOutputWeekly} />
              )}

              {/* כפתור "לא מדויק" — §3.7. ממוקם בתחתית ה-card, פעיל פעם אחת. */}
              <div className="mt-3 flex justify-end">
                <InaccurateButton
                  state={submitState}
                  onClick={handleInaccurate}
                  accent={accentColor}
                />
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function DailyBody({ output }: { output: AiSummaryOutputDaily }) {
  const omitted = new Set(output.omitted_sections);
  // סקציית "היום" הוסרה (החלטת מוצר — backend לא מייצר את השדה,
  // ב-types.ts הוא נמחק). הסיכום מתחיל ישר מ-bottom_line ועובר ללידים
  // בולטים / תשומת לב / מחר.
  return (
    <div className="mt-3 space-y-3 text-sm text-gray-800">
      {!omitted.has("highlights") && output.highlights.length > 0 && (
        <ListSection label="לידים בולטים" items={output.highlights} />
      )}
      {!omitted.has("needs_attention") && output.needs_attention.length > 0 && (
        <ListSection
          label="דורש תשומת לב"
          items={output.needs_attention}
        />
      )}
      {!omitted.has("tomorrow") && output.tomorrow && (
        <Section label="מחר">{output.tomorrow}</Section>
      )}
    </div>
  );
}

function WeeklyBody({ output }: { output: AiSummaryOutputWeekly }) {
  const omitted = new Set(output.omitted_sections);
  return (
    <div className="mt-3 space-y-3 text-sm text-gray-800">
      <Section label="השבוע במבט-על">{output.week_overview}</Section>
      {!omitted.has("trends_vs_last_week") && output.trends_vs_last_week && (
        <Section label="מגמות מול שבוע קודם">
          {output.trends_vs_last_week}
        </Section>
      )}
      {!omitted.has("what_worked") && output.what_worked.length > 0 && (
        <ListSection label="מה עבד" items={output.what_worked} />
      )}
      {!omitted.has("what_stuck") && output.what_stuck.length > 0 && (
        <ListSection label="מה תקוע" items={output.what_stuck} />
      )}
      {!omitted.has("next_week_focus") && output.next_week_focus && (
        <Section label="פוקוס לשבוע הבא">{output.next_week_focus}</Section>
      )}
    </div>
  );
}

function Section({ label, children }: { label: string; children: string }) {
  return (
    <div>
      <div className="text-[11px] uppercase tracking-wide text-gray-500 mb-1">
        {label}
      </div>
      <div className="leading-relaxed">{parseSummaryText(children)}</div>
    </div>
  );
}

function ListSection({ label, items }: { label: string; items: string[] }) {
  return (
    <div>
      <div className="text-[11px] uppercase tracking-wide text-gray-500 mb-1">
        {label}
      </div>
      <ul className="space-y-1 list-disc ps-5 leading-relaxed">
        {items.map((item, i) => (
          <li key={i}>{parseSummaryText(item)}</li>
        ))}
      </ul>
    </div>
  );
}

function InaccurateButton({
  state,
  onClick,
  accent,
}: {
  state: SubmitState;
  onClick: () => void;
  accent: "indigo" | "emerald";
}) {
  if (state === "done") {
    return (
      <span
        className={`text-[11px] ${accent === "indigo" ? "text-indigo-600" : "text-emerald-700"}`}
        aria-live="polite"
      >
        תודה, נשפר
      </span>
    );
  }
  if (state === "error") {
    return (
      <span className="text-[11px] text-state-red" aria-live="polite">
        לא הצלחנו לשמור — נסי שוב
      </span>
    );
  }
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={state === "submitting"}
      aria-label="סמני את הסיכום כלא מדויק"
      className="flex items-center gap-1 text-[11px] text-gray-500 hover:text-gray-900 disabled:opacity-50"
    >
      <ThumbsDown size={14} aria-hidden />
      <span>לא מדויק</span>
    </button>
  );
}
