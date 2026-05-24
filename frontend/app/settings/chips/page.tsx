"use client";

import { useEffect, useState } from "react";
import {
  Check,
  ChevronDown,
  ChevronUp,
  Plus,
  Trash2,
  X,
} from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { api, ApiError } from "@/lib/api";
import {
  STATUS_LABELS,
  TASK_TYPE_LABELS,
  WAITING_ON_LABELS,
  labelStatus,
  labelTaskType,
  labelWaiting,
} from "@/lib/hebrew";
import type {
  LeadStatus,
  QuickActionChip,
  WaitingOn,
} from "@/lib/types";

// אופציות לעריכה: לפי enums ב-Spec v2.1 §5.11.
// IN_PROGRESS הוא ה-typical לפי §16.4 אבל נועה יכולה לבחור אחר.
const STATUS_OPTIONS: LeadStatus[] = [
  "NEW",
  "IN_PROGRESS",
  "PROPOSAL_SENT",
  "BOOKING_PENDING",
  "BOOKED",
];
// סגורים (WON / LOST / ARCHIVED) לא רלוונטיים — chip לא יוצרים על
// ליד סגור (F-23).

// SYSTEM ו-NONE לא רלוונטיים לchip — נועה לא בוחרת אותם ידנית.
const WAITING_ON_OPTIONS: WaitingOn[] = [
  "NOAH",
  "CLIENT",
  "ASSISTANT",
  "ASSISTANT_PENDING_NOAH",
];

// TaskType — לפי Spec §17.1 + §16.4. הצ'יפים השכיחים יוצרים את 4 האלה.
const TASK_TYPE_OPTIONS = [
  "retry_call",
  "followup",
  "send_proposal",
  "dormant_check",
  "warm_followup",
  "lecture_inquiry",
];

function chipSummary(c: QuickActionChip): string {
  if (
    !c.target_status ||
    !c.waiting_on ||
    !c.followup_task_type ||
    c.auto_followup_days === null
  ) {
    return "לא מאוכלס — לחצי 'ערוך' כדי להשלים";
  }
  return `→ ${labelStatus(c.target_status)} · ${labelWaiting(c.waiting_on)} · ${labelTaskType(c.followup_task_type)} בעוד ${c.auto_followup_days} ימים`;
}

export default function ChipsSettingsPage() {
  const [chips, setChips] = useState<QuickActionChip[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editId, setEditId] = useState<string | null>(null);
  const [addOpen, setAddOpen] = useState(false);

  async function load() {
    setError(null);
    try {
      const data = await api.listChips(false);
      setChips(data);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "שגיאה בטעינה");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function toggleActive(chip: QuickActionChip) {
    try {
      await api.updateChip(chip.id, { is_active: !chip.is_active });
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "שגיאה");
    }
  }

  async function move(chip: QuickActionChip, delta: -1 | 1) {
    try {
      await api.updateChip(chip.id, { sort_order: chip.sort_order + delta });
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "שגיאה");
    }
  }

  async function remove(chip: QuickActionChip) {
    if (!confirm(`למחוק את הצ'יפ "${chip.label}"?`)) return;
    try {
      await api.deleteChip(chip.id);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "שגיאה");
    }
  }

  return (
    <AppShell title="צ'יפים מהירים">
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
            {"צ'יפים שמופיעים בכרטיס ליד לסיכום שיחה מהיר. אפשר לערוך, להוסיף, או להסיר."}
          </p>

          <ul className="space-y-2">
            {chips.map((chip) =>
              editId === chip.id ? (
                <li key={chip.id}>
                  <ChipEditor
                    initial={chip}
                    onCancel={() => setEditId(null)}
                    onSave={async (payload) => {
                      try {
                        await api.updateChip(chip.id, payload);
                        setEditId(null);
                        await load();
                      } catch (err) {
                        setError(
                          err instanceof ApiError ? err.message : "שגיאה",
                        );
                      }
                    }}
                  />
                </li>
              ) : (
                <li
                  key={chip.id}
                  className="bg-white rounded-xl border border-gray-200 px-3 py-2.5 flex items-center gap-2"
                >
                  <div className="flex flex-col gap-0.5">
                    <button
                      onClick={() => move(chip, -1)}
                      className="text-gray-400 hover:text-gray-700"
                      aria-label="העלה"
                    >
                      <ChevronUp size={14} />
                    </button>
                    <button
                      onClick={() => move(chip, 1)}
                      className="text-gray-400 hover:text-gray-700"
                      aria-label="הורד"
                    >
                      <ChevronDown size={14} />
                    </button>
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="font-medium truncate flex items-center gap-2">
                      <span>{chip.label}</span>
                      {!chip.is_active && (
                        <span className="text-[10px] bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded">
                          לא פעיל
                        </span>
                      )}
                    </div>
                    <div className="text-xs text-gray-500 truncate">
                      {chipSummary(chip)}
                    </div>
                  </div>
                  <button
                    onClick={() => toggleActive(chip)}
                    className="text-xs text-gray-600 px-2 py-1 rounded hover:bg-gray-100"
                  >
                    {chip.is_active ? "כבה" : "הפעל"}
                  </button>
                  <button
                    onClick={() => setEditId(chip.id)}
                    className="text-xs text-gray-700 px-2 py-1 rounded hover:bg-gray-100"
                  >
                    ערוך
                  </button>
                  <button
                    onClick={() => remove(chip)}
                    className="text-state-red hover:bg-state-red/10 p-1.5 rounded"
                    aria-label="מחק"
                  >
                    <Trash2 size={14} />
                  </button>
                </li>
              ),
            )}
          </ul>

          {addOpen ? (
            <div className="mt-3">
              <ChipEditor
                initial={null}
                onCancel={() => setAddOpen(false)}
                onSave={async (payload) => {
                  try {
                    await api.createChip(payload);
                    setAddOpen(false);
                    await load();
                  } catch (err) {
                    setError(err instanceof ApiError ? err.message : "שגיאה");
                  }
                }}
              />
            </div>
          ) : (
            <button
              onClick={() => setAddOpen(true)}
              className="mt-3 w-full bg-gray-900 text-white rounded-xl py-3 text-sm font-medium flex items-center justify-center gap-2"
            >
              <Plus size={16} aria-hidden />
              {"הוספת צ'יפ חדש"}
            </button>
          )}
        </>
      )}
    </AppShell>
  );
}

function ChipEditor({
  initial,
  onCancel,
  onSave,
}: {
  initial: QuickActionChip | null;
  onCancel: () => void;
  onSave: (payload: {
    label: string;
    target_status: LeadStatus;
    waiting_on: WaitingOn;
    followup_task_type: string;
    auto_followup_days: number;
    sort_order?: number;
    is_active?: boolean;
  }) => Promise<void>;
}) {
  const [label, setLabel] = useState(initial?.label ?? "");
  const [targetStatus, setTargetStatus] = useState<LeadStatus>(
    (initial?.target_status as LeadStatus | null) ?? "IN_PROGRESS",
  );
  const [waitingOn, setWaitingOn] = useState<WaitingOn>(
    (initial?.waiting_on as WaitingOn | null) ?? "NOAH",
  );
  const [taskType, setTaskType] = useState<string>(
    initial?.followup_task_type ?? "followup",
  );
  const [days, setDays] = useState<number>(initial?.auto_followup_days ?? 1);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function handleSave() {
    if (!label.trim()) {
      setErr("חובה להזין שם");
      return;
    }
    if (!Number.isFinite(days) || days < 1 || days > 365) {
      setErr("מספר ימים חייב להיות בין 1 ל-365");
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      await onSave({
        label: label.trim(),
        target_status: targetStatus,
        waiting_on: waitingOn,
        followup_task_type: taskType,
        auto_followup_days: days,
      });
    } catch (e) {
      setErr(e instanceof Error ? e.message : "שגיאה");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="bg-white rounded-xl border border-gray-300 p-3 space-y-3">
      <div>
        <label className="text-xs text-gray-600 block mb-1">
          {"שם הצ'יפ"}
        </label>
        <input
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          placeholder="למשל: רוצה הצעה"
          className="w-full text-sm border border-gray-300 rounded-md px-2 py-1.5 focus:outline-none focus:border-gray-900"
          maxLength={100}
        />
      </div>

      <div>
        <label className="text-xs text-gray-600 block mb-1">סטטוס יעד</label>
        <select
          value={targetStatus}
          onChange={(e) => setTargetStatus(e.target.value as LeadStatus)}
          className="w-full text-sm border border-gray-300 rounded-md px-2 py-1.5 focus:outline-none focus:border-gray-900 bg-white"
        >
          {STATUS_OPTIONS.map((s) => (
            <option key={s} value={s}>
              {STATUS_LABELS[s] ?? s}
            </option>
          ))}
        </select>
      </div>

      <div>
        <label className="text-xs text-gray-600 block mb-1">
          {"מי 'מחזיק' בליד אחרי הלחיצה"}
        </label>
        <select
          value={waitingOn}
          onChange={(e) => setWaitingOn(e.target.value as WaitingOn)}
          className="w-full text-sm border border-gray-300 rounded-md px-2 py-1.5 focus:outline-none focus:border-gray-900 bg-white"
        >
          {WAITING_ON_OPTIONS.map((w) => (
            <option key={w} value={w}>
              {WAITING_ON_LABELS[w] ?? w}
            </option>
          ))}
        </select>
      </div>

      <div>
        <label className="text-xs text-gray-600 block mb-1">סוג פולואפ</label>
        <select
          value={taskType}
          onChange={(e) => setTaskType(e.target.value)}
          className="w-full text-sm border border-gray-300 rounded-md px-2 py-1.5 focus:outline-none focus:border-gray-900 bg-white"
        >
          {TASK_TYPE_OPTIONS.map((t) => (
            <option key={t} value={t}>
              {TASK_TYPE_LABELS[t] ?? t}
            </option>
          ))}
        </select>
      </div>

      <div>
        <label className="text-xs text-gray-600 block mb-1">
          {"פולואפ בעוד כמה ימים"}
        </label>
        <input
          type="number"
          min={1}
          max={365}
          value={days}
          onChange={(e) => setDays(Number(e.target.value))}
          className="w-full text-sm border border-gray-300 rounded-md px-2 py-1.5 focus:outline-none focus:border-gray-900"
        />
      </div>

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
          disabled={busy || !label.trim()}
          className="text-sm bg-gray-900 text-white px-3 py-1.5 rounded-md disabled:opacity-50"
        >
          <Check size={14} className="inline" aria-hidden />{" "}
          {busy ? "שומר…" : "שמירה"}
        </button>
      </div>
    </div>
  );
}
