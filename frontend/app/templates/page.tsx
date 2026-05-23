"use client";

import { useEffect, useState } from "react";
import { Edit3, Plus, Trash2 } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { EmptyState } from "@/components/EmptyState";
import { TemplateEditor } from "@/components/TemplateEditor";
import { api, ApiError } from "@/lib/api";
import type { Template } from "@/lib/types";

const CHANNEL_LABEL: Record<string, string> = {
  whatsapp: "וואטסאפ",
  email: "מייל",
};

const AUDIENCE_LABEL: Record<string, string> = {
  private: "ליד פרטי",
  organization: "ארגון",
  dormant: "ליד רדום",
};

export default function TemplatesPage() {
  const [templates, setTemplates] = useState<Template[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<Template | null>(null);
  const [editorOpen, setEditorOpen] = useState(false);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const items = await api.listTemplates(false);
      setTemplates(items);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "שגיאה בטעינה");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function handleDelete(id: string) {
    if (!confirm("להפוך תבנית זו ללא פעילה? היא תוסתר מהבורר.")) return;
    try {
      await api.deleteTemplate(id);
      void load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "שגיאה במחיקה");
    }
  }

  return (
    <AppShell title="תבניות">
      <div className="flex justify-end mb-3">
        <button
          onClick={() => {
            setEditing(null);
            setEditorOpen(true);
          }}
          className="inline-flex items-center gap-1.5 bg-gray-900 text-white text-sm px-3 py-2 rounded-lg"
        >
          <Plus size={16} aria-hidden />
          תבנית חדשה
        </button>
      </div>

      {loading && (
        <div className="text-center text-gray-400 py-10 text-sm">טוען…</div>
      )}
      {error && (
        <div className="text-sm text-state-red bg-state-red/10 rounded-lg px-3 py-2 mb-3">
          {error}
        </div>
      )}
      {!loading && !error && templates.length === 0 && (
        <EmptyState
          title="אין תבניות עדיין"
          hint="לחיצה על 'תבנית חדשה' כדי להתחיל."
        />
      )}

      <ul className="space-y-2">
        {templates.map((t) => (
          <li
            key={t.id}
            className={`bg-white rounded-xl border border-gray-200 px-3.5 py-3 ${
              t.is_active ? "" : "opacity-60"
            }`}
          >
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="font-medium">{t.name}</span>
                  {!t.is_active && (
                    <span className="text-[10px] uppercase text-gray-400 border border-gray-300 rounded px-1.5 py-0.5">
                      לא פעילה
                    </span>
                  )}
                </div>
                <div className="text-xs text-gray-500 mt-0.5">
                  {CHANNEL_LABEL[t.channel] ?? t.channel}
                  {t.target_audience &&
                    ` · ${AUDIENCE_LABEL[t.target_audience] ?? t.target_audience}`}
                </div>
                <div className="text-sm text-gray-700 mt-1.5 line-clamp-2 whitespace-pre-line">
                  {t.body}
                </div>
              </div>
              <div className="flex flex-col gap-1.5 shrink-0">
                <button
                  onClick={() => {
                    setEditing(t);
                    setEditorOpen(true);
                  }}
                  className="text-gray-400 hover:text-gray-700 p-1"
                  aria-label="עריכה"
                >
                  <Edit3 size={16} />
                </button>
                {t.is_active && (
                  <button
                    onClick={() => handleDelete(t.id)}
                    className="text-gray-400 hover:text-state-red p-1"
                    aria-label="מחיקה"
                  >
                    <Trash2 size={16} />
                  </button>
                )}
              </div>
            </div>
          </li>
        ))}
      </ul>

      <TemplateEditor
        template={editing}
        open={editorOpen}
        onClose={() => setEditorOpen(false)}
        onSaved={load}
      />
    </AppShell>
  );
}
