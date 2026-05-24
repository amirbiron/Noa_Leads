"use client";

import { useEffect, useState } from "react";
import { Check, X } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { api, ApiError } from "@/lib/api";
import { labelCategory } from "@/lib/hebrew";
import type { ServiceRate } from "@/lib/types";

// עריכת תעריפי שירות — F-03 + F-12. owner-only ברמת ה-API.
// קבוצה לפי category, כל row עם כפתור "ערוך" שפותח inline editor.
//
// שלא כמו chips — אי אפשר להוסיף או למחוק תעריפים. הרשימה קבועה
// מהSpec §15.2, נועה רק עורכת ערכים (מחיר / מפגשים / הערות / פעיל).
export default function RatesSettingsPage() {
  const [rates, setRates] = useState<ServiceRate[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editSubtype, setEditSubtype] = useState<string | null>(null);

  async function load() {
    setError(null);
    try {
      setRates(await api.listServiceRates());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "שגיאה בטעינה");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  // קיבוץ לפי category, בסדר היציב של הspec.
  const grouped = rates.reduce<Record<string, ServiceRate[]>>((acc, r) => {
    (acc[r.service_category] ??= []).push(r);
    return acc;
  }, {});

  return (
    <AppShell title="תעריפי שירות">
      {loading && (
        <div className="text-center text-gray-400 py-10 text-sm">טוען…</div>
      )}
      {error && (
        <div className="text-sm text-state-red bg-state-red/10 rounded-lg px-3 py-2 mb-3">
          {error}
        </div>
      )}

      {!loading && (
        <>
          <p className="text-sm text-gray-600 mb-3">
            ערכי ברירת מחדל לכל שירות. בכל סגירת עסקה (WON) המערכת תציע
            את הערכים האלה כברירת מחדל, וניתן לעקוף בכרטיס הספציפי.
          </p>

          {Object.entries(grouped).map(([category, items]) => (
            <div key={category} className="mb-4">
              <h2 className="text-xs text-gray-500 mb-1.5 font-medium">
                {labelCategory(category)}
              </h2>
              <ul className="bg-white rounded-xl border border-gray-200 divide-y divide-gray-100">
                {items.map((rate) =>
                  editSubtype === rate.service_subtype ? (
                    <li key={rate.id} className="p-3">
                      <RateEditor
                        rate={rate}
                        onCancel={() => setEditSubtype(null)}
                        onSaved={async () => {
                          setEditSubtype(null);
                          await load();
                        }}
                        onError={setError}
                      />
                    </li>
                  ) : (
                    <li
                      key={rate.id}
                      className="flex items-baseline justify-between gap-3 px-3.5 py-2.5 text-sm"
                    >
                      <div className="min-w-0 flex-1">
                        <div className="text-gray-800 font-medium flex items-center gap-2">
                          {rate.label}
                          {!rate.is_active && (
                            <span className="text-[10px] bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded">
                              לא פעיל
                            </span>
                          )}
                        </div>
                        <div className="text-xs text-gray-400 mt-0.5">
                          {summary(rate)}
                        </div>
                      </div>
                      <button
                        onClick={() => setEditSubtype(rate.service_subtype)}
                        className="text-xs text-gray-700 px-2 py-1 rounded hover:bg-gray-100 shrink-0"
                      >
                        ערוך
                      </button>
                    </li>
                  ),
                )}
              </ul>
            </div>
          ))}
        </>
      )}
    </AppShell>
  );
}

function summary(r: ServiceRate): string {
  if (r.default_price === null) return "לבירור";
  const parts = [`${Number(r.default_price).toLocaleString("he-IL")} ₪`];
  if (r.default_sessions_count) {
    const unit = r.default_sessions_count === 1 ? "מפגש" : "מפגשים";
    parts.push(`${r.default_sessions_count} ${unit}`);
  }
  if (r.default_duration_minutes) {
    parts.push(`${r.default_duration_minutes} דק' כל אחד`);
  }
  if (r.hourly_rate) {
    parts.push(
      `${Math.round(Number(r.hourly_rate)).toLocaleString("he-IL")} ₪/שעה`,
    );
  }
  return parts.join(" · ");
}

function RateEditor({
  rate,
  onCancel,
  onSaved,
  onError,
}: {
  rate: ServiceRate;
  onCancel: () => void;
  onSaved: () => Promise<void>;
  onError: (msg: string) => void;
}) {
  // ערכי טופס כ-strings — מאפשר ריק = "לבירור".
  const [price, setPrice] = useState<string>(
    rate.default_price !== null ? String(rate.default_price) : "",
  );
  const [duration, setDuration] = useState<string>(
    rate.default_duration_minutes !== null
      ? String(rate.default_duration_minutes)
      : "",
  );
  const [sessions, setSessions] = useState<string>(
    rate.default_sessions_count !== null
      ? String(rate.default_sessions_count)
      : "",
  );
  const [notes, setNotes] = useState<string>(rate.notes ?? "");
  const [isActive, setIsActive] = useState<boolean>(rate.is_active);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  function parseOptionalInt(s: string): number | null | undefined {
    const trimmed = s.trim();
    if (trimmed === "") return null;
    const n = parseInt(trimmed, 10);
    return Number.isInteger(n) && n > 0 ? n : undefined;
  }

  function parseOptionalDecimal(s: string): number | null | undefined {
    const trimmed = s.trim();
    if (trimmed === "") return null;
    if (!/^\d+(\.\d{1,2})?$/.test(trimmed)) return undefined;
    return Number(trimmed);
  }

  async function handleSave() {
    setErr(null);
    const priceVal = parseOptionalDecimal(price);
    const durationVal = parseOptionalInt(duration);
    const sessionsVal = parseOptionalInt(sessions);
    if (
      priceVal === undefined ||
      durationVal === undefined ||
      sessionsVal === undefined
    ) {
      setErr(
        "ערכים לא תקפים. מחיר: מספר עם עד 2 ספרות אחרי הנקודה. דקות / מפגשים: מספר שלם חיובי.",
      );
      return;
    }
    setBusy(true);
    try {
      await api.updateServiceRate(rate.service_subtype, {
        default_price: priceVal,
        default_duration_minutes: durationVal,
        default_sessions_count: sessionsVal,
        notes: notes.trim() || null,
        is_active: isActive,
      });
      await onSaved();
    } catch (e) {
      onError(e instanceof ApiError ? e.message : "שגיאה בשמירה");
      setBusy(false);
    }
  }

  return (
    <div className="bg-white rounded-xl border border-gray-300 p-3 space-y-3">
      <div className="text-sm font-medium">{rate.label}</div>

      <div>
        <label className="text-xs text-gray-600 block mb-1">
          מחיר (₪) — ריק = לבירור
        </label>
        <input
          type="text"
          inputMode="decimal"
          value={price}
          onChange={(e) => setPrice(e.target.value)}
          placeholder="2400"
          className="w-full text-sm border border-gray-300 rounded-md px-2 py-1.5 focus:outline-none focus:border-gray-900"
        />
      </div>

      <div className="grid grid-cols-2 gap-2">
        <div>
          <label className="text-xs text-gray-600 block mb-1">
            דקות למפגש
          </label>
          <input
            type="number"
            min={1}
            max={1440}
            step={1}
            value={duration}
            onChange={(e) => setDuration(e.target.value)}
            placeholder="60"
            className="w-full text-sm border border-gray-300 rounded-md px-2 py-1.5 focus:outline-none focus:border-gray-900"
          />
        </div>
        <div>
          <label className="text-xs text-gray-600 block mb-1">
            מספר מפגשים
          </label>
          <input
            type="number"
            min={1}
            max={200}
            step={1}
            value={sessions}
            onChange={(e) => setSessions(e.target.value)}
            placeholder="8"
            className="w-full text-sm border border-gray-300 rounded-md px-2 py-1.5 focus:outline-none focus:border-gray-900"
          />
        </div>
      </div>

      <div>
        <label className="text-xs text-gray-600 block mb-1">הערות</label>
        <textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          rows={2}
          className="w-full text-sm border border-gray-300 rounded-md px-2 py-1.5 focus:outline-none focus:border-gray-900"
        />
      </div>

      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={isActive}
          onChange={(e) => setIsActive(e.target.checked)}
        />
        <span>תעריף פעיל (יוצע ב-CloseLeadModal)</span>
      </label>

      {err && (
        <div className="text-sm text-state-red bg-state-red/10 rounded-lg px-3 py-2">
          {err}
        </div>
      )}

      <div className="flex justify-end gap-2">
        <button
          onClick={onCancel}
          className="text-sm text-gray-600 px-3 py-1.5"
          disabled={busy}
        >
          <X size={14} className="inline" aria-hidden /> ביטול
        </button>
        <button
          onClick={handleSave}
          disabled={busy}
          className="text-sm bg-gray-900 text-white px-3 py-1.5 rounded-md disabled:opacity-50"
        >
          <Check size={14} className="inline" aria-hidden />{" "}
          {busy ? "שומר…" : "שמירה"}
        </button>
      </div>
    </div>
  );
}
