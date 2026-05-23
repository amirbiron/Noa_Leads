"use client";

import { useEffect, useState } from "react";
import { X } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { Template, TemplateCreate } from "@/lib/types";

// משתנים נתמכים — מסונכרן עם backend/app/utils/template_render.py.
// הצגה ל-Noa כדי שתדע מה היא יכולה לשבץ.
const SUPPORTED_VARS = [
  { key: "customer_name", label: "שם הלקוח/ה" },
  { key: "service_category", label: "קטגוריית השירות" },
  { key: "service_subtype", label: "סוג השירות הספציפי" },
  { key: "organization", label: "ארגון" },
  { key: "phone", label: "טלפון" },
  { key: "email", label: "מייל" },
];

interface Props {
  template: Template | null; // null = יצירה חדשה
  open: boolean;
  onClose: () => void;
  onSaved: () => void;
}

export function TemplateEditor({ template, open, onClose, onSaved }: Props) {
  const [name, setName] = useState("");
  const [channel, setChannel] = useState<"whatsapp" | "email">("whatsapp");
  const [audience, setAudience] = useState<
    "private" | "organization" | "dormant" | ""
  >("");
  const [body, setBody] = useState("");
  const [isActive, setIsActive] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    if (template) {
      setName(template.name);
      setChannel(template.channel as "whatsapp" | "email");
      setAudience(
        (template.target_audience as "" | "private" | "organization" | "dormant") ??
          "",
      );
      setBody(template.body);
      setIsActive(template.is_active);
    } else {
      setName("");
      setChannel("whatsapp");
      setAudience("");
      setBody("");
      setIsActive(true);
    }
    setError(null);
  }, [template, open]);

  function insertVar(key: string) {
    setBody((prev) => `${prev}{${key}}`);
  }

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const payload: TemplateCreate = {
        name: name.trim(),
        channel,
        target_audience: audience || null,
        body,
        is_active: isActive,
        // variables נשלף אוטומטית ע"י backend מתוך body — לא חובה כאן
      };
      if (template) {
        await api.updateTemplate(template.id, payload);
      } else {
        await api.createTemplate(payload);
      }
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "שגיאה בשמירה");
    } finally {
      setBusy(false);
    }
  }

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 bg-black/40 flex items-end sm:items-center justify-center">
      <div className="bg-white w-full sm:max-w-lg sm:rounded-2xl rounded-t-2xl shadow-xl max-h-[95vh] flex flex-col">
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100 shrink-0">
          <h2 className="font-semibold">
            {template ? "עריכת תבנית" : "תבנית חדשה"}
          </h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600"
            aria-label="סגירה"
          >
            <X size={20} />
          </button>
        </div>

        <div className="overflow-y-auto p-4 space-y-4">
          <label className="block">
            <div className="text-sm font-medium text-gray-700 mb-1.5">שם</div>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-base focus:border-gray-900 focus:outline-none"
              placeholder="לדוגמה: פתיחה לליד פרטי"
            />
          </label>

          <div className="grid grid-cols-2 gap-3">
            <label className="block">
              <div className="text-sm font-medium text-gray-700 mb-1.5">
                ערוץ
              </div>
              <select
                value={channel}
                onChange={(e) =>
                  setChannel(e.target.value as "whatsapp" | "email")
                }
                className="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-base focus:border-gray-900 focus:outline-none"
              >
                <option value="whatsapp">וואטסאפ</option>
                <option value="email">מייל</option>
              </select>
            </label>

            <label className="block">
              <div className="text-sm font-medium text-gray-700 mb-1.5">
                קהל יעד
              </div>
              <select
                value={audience}
                onChange={(e) =>
                  setAudience(
                    e.target.value as "" | "private" | "organization" | "dormant",
                  )
                }
                className="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-base focus:border-gray-900 focus:outline-none"
              >
                <option value="">כל אחד</option>
                <option value="private">ליד פרטי</option>
                <option value="organization">ארגון</option>
                <option value="dormant">ליד רדום</option>
              </select>
            </label>
          </div>

          <div>
            <div className="text-sm font-medium text-gray-700 mb-1.5">
              גוף התבנית
            </div>
            <textarea
              value={body}
              onChange={(e) => setBody(e.target.value)}
              rows={7}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-base focus:border-gray-900 focus:outline-none"
              placeholder="היי {customer_name}, ראיתי שאת מעוניינת ב-{service_subtype}…"
            />
            <div className="mt-2 flex flex-wrap gap-1.5">
              {SUPPORTED_VARS.map((v) => (
                <button
                  key={v.key}
                  type="button"
                  onClick={() => insertVar(v.key)}
                  className="text-xs px-2 py-1 rounded-full border border-gray-300 bg-white text-gray-700 hover:bg-gray-50"
                  title={v.label}
                >
                  {`{${v.key}}`}
                </button>
              ))}
            </div>
          </div>

          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={isActive}
              onChange={(e) => setIsActive(e.target.checked)}
              className="w-4 h-4"
            />
            <span className="text-sm text-gray-700">פעילה (מופיעה בבורר)</span>
          </label>

          {error && (
            <div className="text-sm text-state-red bg-state-red/10 rounded-lg px-3 py-2">
              {error}
            </div>
          )}
        </div>

        <div className="border-t border-gray-100 p-3 shrink-0">
          <button
            onClick={submit}
            disabled={busy || !name.trim() || !body.trim()}
            className="w-full rounded-lg bg-gray-900 text-white py-3 font-medium disabled:opacity-50"
          >
            {busy ? "שומרת…" : template ? "עדכון" : "יצירה"}
          </button>
        </div>
      </div>
    </div>
  );
}
