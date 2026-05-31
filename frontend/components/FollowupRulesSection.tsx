"use client";

import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { FOLLOWUP_RULE_LABELS, FOLLOWUP_UNIT_LABELS } from "@/lib/hebrew";
import type {
  FollowupRule,
  FollowupRuleUpdate,
  FollowupTimeUnit,
} from "@/lib/types";

// סקציית "חוקי פולואף" בעמוד ההגדרות (§17.1).
//
// owner: עריכה מלאה — interval (value+unit) + repeat_count + repeat_interval.
//        save explicit פר כלל (לא debounced — נועה רוצה לדעת בוודאות
//        שהשמירה קרתה).
// assistant: readonly — תצוגת ערכים בלבד, ללא inputs.
//
// אין הוספה/מחיקה — 5 הכללים מוגדרים בקוד (TaskType) ו-seeded ב-migration
// 0029. רק עריכת ערכים.
export function FollowupRulesSection({ isOwner }: { isOwner: boolean }) {
  const [rules, setRules] = useState<FollowupRule[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .listFollowupRules()
      .then(setRules)
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : "שגיאה בטעינת כללים"),
      )
      .finally(() => setLoading(false));
  }, []);

  function handleRuleUpdated(updated: FollowupRule) {
    setRules((prev) =>
      prev.map((r) => (r.rule_key === updated.rule_key ? updated : r)),
    );
  }

  if (loading) {
    return (
      <div className="text-center text-gray-400 py-4 text-sm">טוען כללים…</div>
    );
  }
  if (error) {
    return (
      <div className="text-sm text-state-red bg-state-red/10 rounded-lg px-3 py-2">
        {error}
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {rules.map((rule) =>
        isOwner ? (
          <EditableRuleCard
            key={rule.rule_key}
            rule={rule}
            onSaved={handleRuleUpdated}
          />
        ) : (
          <ReadonlyRuleCard key={rule.rule_key} rule={rule} />
        ),
      )}
    </div>
  );
}

function ReadonlyRuleCard({ rule }: { rule: FollowupRule }) {
  const title = FOLLOWUP_RULE_LABELS[rule.rule_key] ?? rule.rule_key;
  const intervalText = `${rule.interval_value} ${FOLLOWUP_UNIT_LABELS[rule.interval_unit]}`;
  const repeatText =
    rule.repeat_count > 1
      ? ` · ${rule.repeat_count} תזכורות (כל ${rule.repeat_interval_value} ${FOLLOWUP_UNIT_LABELS[rule.repeat_interval_unit]})`
      : "";
  return (
    <div className="bg-white rounded-xl border border-gray-200 px-3.5 py-2.5 text-sm flex items-baseline justify-between gap-3">
      <span className="text-gray-700">{title}</span>
      <span className="text-gray-500 text-xs text-end">
        {intervalText}
        {repeatText}
      </span>
    </div>
  );
}

function EditableRuleCard({
  rule,
  onSaved,
}: {
  rule: FollowupRule;
  onSaved: (r: FollowupRule) => void;
}) {
  const title = FOLLOWUP_RULE_LABELS[rule.rule_key] ?? rule.rule_key;

  // local draft state — נטען מחדש בכל שינוי של ה-rule prop (אחרי save).
  const [intervalValue, setIntervalValue] = useState(String(rule.interval_value));
  const [intervalUnit, setIntervalUnit] = useState<FollowupTimeUnit>(
    rule.interval_unit,
  );
  const [repeatCount, setRepeatCount] = useState(String(rule.repeat_count));
  const [repeatIntervalValue, setRepeatIntervalValue] = useState(
    String(rule.repeat_interval_value),
  );
  const [repeatIntervalUnit, setRepeatIntervalUnit] = useState<FollowupTimeUnit>(
    rule.repeat_interval_unit,
  );

  const [saving, setSaving] = useState(false);
  const [feedback, setFeedback] = useState<"saved" | "error" | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // ולידציה בסיסית — המספרים חיוביים. backend אוכף ב-CHECK constraints
  // אבל נחסום מוקדם כדי לתת feedback מיידי.
  const parsedInterval = Number(intervalValue);
  const parsedRepeatCount = Number(repeatCount);
  const parsedRepeatInterval = Number(repeatIntervalValue);
  const isValid =
    Number.isInteger(parsedInterval) &&
    parsedInterval > 0 &&
    Number.isInteger(parsedRepeatCount) &&
    parsedRepeatCount >= 1 &&
    Number.isInteger(parsedRepeatInterval) &&
    parsedRepeatInterval > 0;

  const isDirty =
    parsedInterval !== rule.interval_value ||
    intervalUnit !== rule.interval_unit ||
    parsedRepeatCount !== rule.repeat_count ||
    parsedRepeatInterval !== rule.repeat_interval_value ||
    repeatIntervalUnit !== rule.repeat_interval_unit;

  const showRepeatRow = parsedRepeatCount > 1;

  async function handleSave() {
    if (!isValid || !isDirty) return;
    setSaving(true);
    setErrorMsg(null);
    setFeedback(null);
    const payload: FollowupRuleUpdate = {
      interval_value: parsedInterval,
      interval_unit: intervalUnit,
      repeat_count: parsedRepeatCount,
      repeat_interval_value: parsedRepeatInterval,
      repeat_interval_unit: repeatIntervalUnit,
    };
    try {
      const updated = await api.updateFollowupRule(rule.rule_key, payload);
      onSaved(updated);
      setFeedback("saved");
      // ה-feedback "נשמר" נעלם אחרי ~2 שניות.
      setTimeout(() => setFeedback(null), 2000);
    } catch (err) {
      setFeedback("error");
      setErrorMsg(
        err instanceof ApiError ? err.message : "שגיאה בשמירת הכלל",
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-3.5 space-y-2.5">
      <div className="flex items-center justify-between gap-2">
        <div className="text-sm font-medium text-gray-800">{title}</div>
        {feedback === "saved" && (
          <span className="text-xs text-state-green">נשמר</span>
        )}
      </div>

      {/* התראה אחרי */}
      <div className="flex items-center gap-2 text-sm">
        <span className="text-gray-600 text-xs w-24 shrink-0">התראה אחרי</span>
        <input
          type="number"
          min={1}
          value={intervalValue}
          onChange={(e) => setIntervalValue(e.target.value)}
          disabled={saving}
          className="w-20 rounded border border-gray-300 px-2 py-1 text-sm focus:border-gray-900 focus:outline-none"
        />
        <select
          value={intervalUnit}
          onChange={(e) => setIntervalUnit(e.target.value as FollowupTimeUnit)}
          disabled={saving}
          className="rounded border border-gray-300 px-2 py-1 text-sm bg-white focus:border-gray-900 focus:outline-none"
        >
          <option value="hours">{FOLLOWUP_UNIT_LABELS.hours}</option>
          <option value="days">{FOLLOWUP_UNIT_LABELS.days}</option>
        </select>
      </div>

      {/* תזכורות חוזרות */}
      <div className="flex items-center gap-2 text-sm">
        <span className="text-gray-600 text-xs w-24 shrink-0">תזכורות</span>
        <input
          type="number"
          min={1}
          value={repeatCount}
          onChange={(e) => setRepeatCount(e.target.value)}
          disabled={saving}
          className="w-20 rounded border border-gray-300 px-2 py-1 text-sm focus:border-gray-900 focus:outline-none"
        />
        <span className="text-xs text-gray-500">(כולל הראשונה)</span>
      </div>

      {/* מרווח בין חזרות — מוצג רק כשיש יותר מתזכורת אחת */}
      {showRepeatRow && (
        <div className="flex items-center gap-2 text-sm">
          <span className="text-gray-600 text-xs w-24 shrink-0">מרווח</span>
          <input
            type="number"
            min={1}
            value={repeatIntervalValue}
            onChange={(e) => setRepeatIntervalValue(e.target.value)}
            disabled={saving}
            className="w-20 rounded border border-gray-300 px-2 py-1 text-sm focus:border-gray-900 focus:outline-none"
          />
          <select
            value={repeatIntervalUnit}
            onChange={(e) =>
              setRepeatIntervalUnit(e.target.value as FollowupTimeUnit)
            }
            disabled={saving}
            className="rounded border border-gray-300 px-2 py-1 text-sm bg-white focus:border-gray-900 focus:outline-none"
          >
            <option value="hours">{FOLLOWUP_UNIT_LABELS.hours}</option>
            <option value="days">{FOLLOWUP_UNIT_LABELS.days}</option>
          </select>
        </div>
      )}

      {feedback === "error" && errorMsg && (
        <div className="text-xs text-state-red">{errorMsg}</div>
      )}

      {isDirty && (
        <div className="flex justify-end pt-1">
          <button
            type="button"
            onClick={handleSave}
            disabled={saving || !isValid}
            className="rounded-lg bg-gray-900 text-white text-sm px-4 py-1.5 disabled:opacity-50"
          >
            {saving ? "שומרת…" : "שמירה"}
          </button>
        </div>
      )}
    </div>
  );
}
