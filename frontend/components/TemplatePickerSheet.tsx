"use client";

import { useEffect, useState } from "react";
import { Copy, MessageCircle, X } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { Lead, Template, TemplateRenderResponse } from "@/lib/types";

interface Props {
  lead: Lead;
  open: boolean;
  onClose: () => void;
  onSent: () => void;
}

// בורר תבניות + רנדור + פתיחת וואטסאפ עם הטקסט המוכן.
// לפי האפיון: "X רק לוחצת שלח" — אנחנו פותחים את WA עם prefill,
// והליד מסומן template_sent מיד (אחרי הקליק).
export function TemplatePickerSheet({ lead, open, onClose, onSent }: Props) {
  const [templates, setTemplates] = useState<Template[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<Template | null>(null);
  const [rendered, setRendered] = useState<TemplateRenderResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    setSelected(null);
    setRendered(null);
    setError(null);
    api
      .listTemplates(true)
      .then((items) =>
        setTemplates(items.filter((t) => t.channel === "whatsapp")),
      )
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : "שגיאה בטעינה"),
      )
      .finally(() => setLoading(false));
  }, [open]);

  async function pickTemplate(t: Template) {
    setSelected(t);
    setError(null);
    try {
      const r = await api.renderTemplate(t.id, lead.id);
      setRendered(r);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "שגיאה ברנדור");
    }
  }

  function copyToClipboard() {
    if (!rendered) return;
    void navigator.clipboard.writeText(rendered.rendered_body);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  async function openWhatsAppAndMark() {
    if (!rendered || !lead.phone) return;
    setSending(true);
    setError(null);
    try {
      // פתיחת וואטסאפ עם הטקסט המוכן
      const digits = lead.phone.replace(/\D/g, "");
      const text = encodeURIComponent(rendered.rendered_body);
      window.open(`https://wa.me/${digits}?text=${text}`, "_blank");
      // סימון במערכת: התבנית נשלחה (סטטוס NEW → IN_PROGRESS אוטומטית)
      await api.performAction(lead.id, "mark_template_sent", {
        metadata: { template_id: selected?.id },
      });
      onSent();
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "שגיאה בסימון");
    } finally {
      setSending(false);
    }
  }

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 bg-black/40 flex items-end sm:items-center justify-center">
      <div className="bg-white w-full sm:max-w-md sm:rounded-2xl rounded-t-2xl shadow-xl max-h-[90vh] flex flex-col">
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100 shrink-0">
          <h2 className="font-semibold">בחרי תבנית</h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600"
            aria-label="סגירה"
          >
            <X size={20} />
          </button>
        </div>

        <div className="overflow-y-auto p-4 space-y-3">
          {loading && (
            <div className="text-sm text-gray-400 text-center py-4">טוען…</div>
          )}

          {!loading && templates.length === 0 && (
            <div className="text-sm text-gray-500 text-center py-4">
              אין תבניות פעילות. צרי תבנית מ-/templates.
            </div>
          )}

          {!rendered &&
            templates.map((t) => (
              <button
                key={t.id}
                onClick={() => pickTemplate(t)}
                className="w-full text-start bg-white border border-gray-200 rounded-lg px-3 py-2.5 active:bg-gray-50"
              >
                <div className="font-medium text-sm">{t.name}</div>
                <div className="text-xs text-gray-500 mt-0.5 line-clamp-2">
                  {t.body}
                </div>
              </button>
            ))}

          {rendered && (
            <div className="space-y-3">
              <div>
                <div className="text-xs text-gray-500 mb-1">
                  תצוגה מקדימה — {selected?.name}
                </div>
                <div className="bg-gray-50 rounded-lg px-3 py-2.5 text-sm whitespace-pre-line border border-gray-200">
                  {rendered.rendered_body}
                </div>
              </div>

              {rendered.missing_variables.length > 0 && (
                <div className="text-xs text-state-orange bg-state-orange/10 rounded-lg px-3 py-2">
                  שדות חסרים בליד:{" "}
                  <strong>{rendered.missing_variables.join(", ")}</strong>
                </div>
              )}

              <button
                onClick={() => {
                  setSelected(null);
                  setRendered(null);
                }}
                className="text-sm text-gray-500 underline"
              >
                בחירת תבנית אחרת
              </button>
            </div>
          )}

          {error && (
            <div className="text-sm text-state-red bg-state-red/10 rounded-lg px-3 py-2">
              {error}
            </div>
          )}
        </div>

        {rendered && (
          <div className="border-t border-gray-100 p-3 space-y-2 shrink-0">
            <button
              onClick={openWhatsAppAndMark}
              disabled={sending || !lead.phone}
              className="w-full rounded-lg bg-gray-900 text-white py-3 font-medium flex items-center justify-center gap-2 disabled:opacity-50"
            >
              <MessageCircle size={18} aria-hidden />
              {sending
                ? "פותחת…"
                : lead.phone
                ? "פתיחת וואטסאפ"
                : "אין טלפון לליד"}
            </button>
            <button
              onClick={copyToClipboard}
              className="w-full rounded-lg bg-gray-100 text-gray-800 py-2.5 text-sm flex items-center justify-center gap-2"
            >
              <Copy size={14} aria-hidden />
              {copied ? "הועתק ✓" : "העתקה ללוח"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
