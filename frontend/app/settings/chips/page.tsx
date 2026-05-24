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
import { SectionHeader } from "@/components/SectionHeader";
import { api, ApiError } from "@/lib/api";
import type { QuickActionChip } from "@/lib/types";

// רשימת ה-action_types הניתנים לבחירה. סנכרון ידני מול
// backend/app/core/state_machine.py — actions שלא ב-state_machine
// יידחו בvalidation. כללנו רק actions ידידותיים לשימוש בצ'יפ
// (לא request_meeting/approve_meeting שיש להם UI ייעודי).
const ACTION_OPTIONS: { value: string; label: string }[] = [
  { value: "mark_template_sent", label: "שליחת תבנית" },
  { value: "log_call_completed", label: "תיעוד שיחה" },
  { value: "log_call_no_answer", label: "אין מענה" },
  { value: "mark_proposal_sent", label: "שליחת הצעה" },
  { value: "add_internal_note", label: "הוספת הערה (דורש טקסט)" },
  { value: "log_inbound_message", label: "הודעה נכנסת" },
  { value: "log_outbound_message", label: "הודעה יוצאת" },
];

function labelForActionType(action_type: string): string {
  return ACTION_OPTIONS.find((a) => a.value === action_type)?.label ?? action_type;
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
            צ'יפים שמופיעים בכרטיס ליד לסיכום שיחה מהיר. אפשר לערוך, להוסיף, או להסיר.
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
                      {chip.requires_content && (
                        <span className="text-[10px] bg-blue-50 text-blue-600 px-1.5 py-0.5 rounded">
                          דורש טקסט
                        </span>
                      )}
                    </div>
                    <div className="text-xs text-gray-500">
                      {labelForActionType(chip.action_type)}
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
              הוספת צ'יפ חדש
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
    action_type: string;
    requires_content: boolean;
    sort_order?: number;
    is_active?: boolean;
  }) => Promise<void>;
}) {
  const [label, setLabel] = useState(initial?.label ?? "");
  const [actionType, setActionType] = useState(
    initial?.action_type ?? ACTION_OPTIONS[0].value,
  );
  const [requiresContent, setRequiresContent] = useState(
    initial?.requires_content ?? false,
  );
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function handleSave() {
    if (!label.trim()) {
      setErr("חובה להזין שם");
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      await onSave({
        label: label.trim(),
        action_type: actionType,
        requires_content: requiresContent,
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
        <label className="text-xs text-gray-600 block mb-1">שם הצ'יפ</label>
        <input
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          placeholder="למשל: שלחתי הצעה"
          className="w-full text-sm border border-gray-300 rounded-md px-2 py-1.5 focus:outline-none focus:border-gray-900"
          maxLength={100}
        />
      </div>
      <div>
        <label className="text-xs text-gray-600 block mb-1">פעולה</label>
        <select
          value={actionType}
          onChange={(e) => setActionType(e.target.value)}
          className="w-full text-sm border border-gray-300 rounded-md px-2 py-1.5 focus:outline-none focus:border-gray-900 bg-white"
        >
          {ACTION_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={requiresContent}
          onChange={(e) => setRequiresContent(e.target.checked)}
        />
        <span>דורש טקסט חופשי (כמו הערה פנימית)</span>
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
