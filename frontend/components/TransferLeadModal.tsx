"use client";

import { useEffect, useState } from "react";
import { X } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { Lead, User } from "@/lib/types";

// העברת ליד לעוזרת / חזרה לנועה. מציג רק משתמשים שאינם הבעלים הנוכחי.
export function TransferLeadModal({
  lead,
  open,
  onClose,
  onTransferred,
}: {
  lead: Lead;
  open: boolean;
  onClose: () => void;
  onTransferred: () => void;
}) {
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    setSelectedId(null);
    setNote("");
    setError(null);
    api
      .listUsers()
      .then((all) => setUsers(all.filter((u) => u.id !== lead.owner_id)))
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : "שגיאה בטעינה"),
      )
      .finally(() => setLoading(false));
  }, [open, lead.owner_id]);

  async function submit() {
    if (!selectedId) return;
    setBusy(true);
    setError(null);
    try {
      await api.transferLead(lead.id, {
        target_user_id: selectedId,
        handoff_note: note.trim() || undefined,
      });
      onTransferred();
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "שגיאה בהעברה");
    } finally {
      setBusy(false);
    }
  }

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 bg-black/40 flex items-end sm:items-center justify-center">
      <div className="bg-white w-full sm:max-w-md sm:rounded-2xl rounded-t-2xl shadow-xl">
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100">
          <h2 className="font-semibold">העברת ליד</h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600"
            aria-label="סגירה"
          >
            <X size={20} />
          </button>
        </div>

        <div className="p-4 space-y-4">
          {loading && (
            <div className="text-sm text-gray-400 text-center py-4">טוען…</div>
          )}

          {!loading && users.length === 0 && (
            <div className="text-sm text-gray-500 text-center py-4">
              אין משתמש אחר במערכת. צרי משתמש דרך CLI.
            </div>
          )}

          {!loading && users.length > 0 && (
            <div className="space-y-2">
              {users.map((u) => (
                <button
                  key={u.id}
                  onClick={() => setSelectedId(u.id)}
                  className={`w-full text-start rounded-lg border px-3 py-2.5 ${
                    selectedId === u.id
                      ? "border-gray-900 bg-gray-50"
                      : "border-gray-200 bg-white"
                  }`}
                >
                  <div className="font-medium text-sm">{u.name}</div>
                  <div className="text-xs text-gray-500">
                    {u.role === "owner" ? "בעלים" : "עוזרת"}
                  </div>
                </button>
              ))}
            </div>
          )}

          {selectedId && (
            <label className="block">
              <div className="text-sm font-medium text-gray-700 mb-1.5">
                הערת מסירה (אופציונלי)
              </div>
              <textarea
                value={note}
                onChange={(e) => setNote(e.target.value)}
                rows={2}
                placeholder="לדוגמה: בקשי הצעת מחיר לסדנה"
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-gray-900 focus:outline-none"
              />
            </label>
          )}

          {error && (
            <div className="text-sm text-state-red bg-state-red/10 rounded-lg px-3 py-2">
              {error}
            </div>
          )}

          <button
            onClick={submit}
            disabled={busy || !selectedId}
            className="w-full rounded-lg bg-gray-900 text-white py-3 font-medium disabled:opacity-50"
          >
            {busy ? "מעבירה…" : "העברה"}
          </button>
        </div>
      </div>
    </div>
  );
}
