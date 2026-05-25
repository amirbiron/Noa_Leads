"use client";

import { useEffect, useState } from "react";
import { Copy, Mail, MessageCircle, X } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { toWhatsAppDigits } from "@/lib/phone";
import type { Lead, Template, TemplateRenderResponse } from "@/lib/types";

type EffectiveChannel = "whatsapp" | "email";

interface Props {
  lead: Lead;
  open: boolean;
  onClose: () => void;
  onSent: () => void;
  // הרחבות לכפתורים הראשיים של DynamicActionButton (Spec §9.3/§12.2):
  // - presetTemplateId: דילוג על list view ישר ל-preview של תבנית קנונית.
  // - forceChannel: override של template.channel (preferred_contact מנצח).
  //   ה-channel ב-DB נשמר לתצוגה ולסיווג, אבל מי שמחליט אם פותחים WA או
  //   mailto הוא ה-preferred_contact של הליד.
  // - actionType: ברירת מחדל mark_template_sent. הצעות יקראו ל-
  //   mark_proposal_sent (אותו פורמט payload, ה-state machine מטפל
  //   בטרנזישן השונה).
  presetTemplateId?: string;
  forceChannel?: EffectiveChannel;
  actionType?: "mark_template_sent" | "mark_proposal_sent";
}

export function TemplatePickerSheet({
  lead,
  open,
  onClose,
  onSent,
  presetTemplateId,
  forceChannel,
  actionType = "mark_template_sent",
}: Props) {
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
    setTemplates([]);

    // preset mode — מדלגים על רשימה, טוענים את הקנונית ומקדמים ישר ל-preview.
    if (presetTemplateId) {
      api
        .getTemplate(presetTemplateId)
        .then((t) => pickTemplate(t))
        .catch((err) =>
          setError(err instanceof ApiError ? err.message : "שגיאה בטעינה"),
        )
        .finally(() => setLoading(false));
      return;
    }

    // manual picker — מסונן לפי forceChannel. כשfallback מ-DynamicActionButton
    // מגיע עם forceChannel='email' (preferred_contact='email' + 404 על
    // הקנונית), הרשימה צריכה להציג תבניות email — אחרת נועה רואה רק
    // תבניות WA וה-flow נחסם. ברירת מחדל 'whatsapp' שומרת על ההתנהגות של
    // הכפתור המשני "בחירת תבנית" (תיקון bugbot).
    const listChannel: EffectiveChannel = forceChannel ?? "whatsapp";
    api
      .listTemplates(true)
      .then((items) =>
        setTemplates(items.filter((t) => t.channel === listChannel)),
      )
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : "שגיאה בטעינה"),
      )
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, presetTemplateId, forceChannel]);

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

  // ה-channel האפקטיבי: preferred_contact של הליד (דרך forceChannel) מנצח
  // את template.channel. אם לא הועבר forceChannel — נופלים ל-template.channel
  // (התנהגות ה-manual picker הקיימת, שמראש מסונן ל-WA).
  const effectiveChannel: EffectiveChannel =
    forceChannel ?? (selected?.channel === "email" ? "email" : "whatsapp");

  const hasContact =
    effectiveChannel === "whatsapp" ? Boolean(lead.phone) : Boolean(lead.email);

  async function openLinkAndMark() {
    if (!rendered || !selected) return;
    setSending(true);
    setError(null);
    try {
      if (effectiveChannel === "email") {
        if (!lead.email) {
          setError("אין מייל לליד.");
          return;
        }
        // subject = שם התבנית (למשל "פתיחה - ארגון"). פשטות > עמודה חדשה
        // ב-DB. נועה תוכל לערוך לפני שליחה בלקוח המייל.
        const subject = encodeURIComponent(selected.name);
        const body = encodeURIComponent(rendered.rendered_body);
        const href = `mailto:${lead.email}?subject=${subject}&body=${body}`;

        // mailto לא פותח חלון של דפדפן — הוא הופנה ל-mail client של המערכת.
        // window.open(mailto:, "_blank") מחזיר null בהרבה דפדפנים (Chrome
        // במיוחד) — זה לא popup blocker אלא תוצר טבעי של handoff ל-system
        // protocol. תיקון bugbot: anchor.click() אמין לכל הדפדפנים, לא
        // false-positive של popup guard. אין דרך לאמת שה-mail client אכן
        // נפתח (limit של mailto:); סומכים על handoff וקוראים ל-mark מיד.
        const anchor = document.createElement("a");
        anchor.href = href;
        anchor.rel = "noopener noreferrer";
        anchor.click();
      } else {
        if (!lead.phone) {
          setError("אין טלפון לליד.");
          return;
        }
        const digits = toWhatsAppDigits(lead.phone);
        if (!digits) {
          setError("מספר הטלפון לא מתאים לחיוג בוואטסאפ.");
          return;
        }
        const text = encodeURIComponent(rendered.rendered_body);
        const href = `https://wa.me/${digits}?text=${text}`;
        // WA web פותח באמת tab חדש — popup guard רלוונטי כאן. אם null
        // → blocker חסם → אסור לסמן כנשלח (הלקוחה לא ראתה כלום).
        const win = window.open(href, "_blank");
        if (!win) {
          setError('פתיחת וואטסאפ נחסמה ע"י הדפדפן. אפשרי חוסם פופ-אפים?');
          return;
        }
      }

      // רק אחרי שהפתיחה הצליחה (WA) / handoff בוצע (mailto) — סימון במערכת.
      // ה-action (mark_template_sent או mark_proposal_sent) מעדכן סטטוס +
      // activity + סוגר tasks (AUTO_CLOSE_TASK_TYPES). פירוט ב-state_machine.py.
      await api.performAction(lead.id, actionType, {
        metadata: { template_id: selected.id },
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

  const sheetTitle = presetTemplateId ? "שליחה" : "בחרי תבנית";
  const ctaIcon =
    effectiveChannel === "email" ? <Mail size={18} aria-hidden /> : <MessageCircle size={18} aria-hidden />;
  const ctaLabel = (() => {
    if (sending) return "פותחת…";
    if (!hasContact) {
      return effectiveChannel === "email" ? "אין מייל לליד" : "אין טלפון לליד";
    }
    return effectiveChannel === "email" ? "פתיחת מייל" : "פתיחת וואטסאפ";
  })();

  return (
    <div className="fixed inset-0 z-50 bg-black/40 flex items-end sm:items-center justify-center">
      <div className="bg-white w-full sm:max-w-md sm:rounded-2xl rounded-t-2xl shadow-xl max-h-[90vh] flex flex-col">
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100 shrink-0">
          <h2 className="font-semibold">{sheetTitle}</h2>
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

          {!loading && !presetTemplateId && templates.length === 0 && (
            <div className="text-sm text-gray-500 text-center py-4">
              אין תבניות פעילות. צרי תבנית מ-/templates.
            </div>
          )}

          {!rendered &&
            !presetTemplateId &&
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

              {/* "בחירת תבנית אחרת" מוסתר במצב preset — אין list לחזור אליה */}
              {!presetTemplateId && (
                <button
                  onClick={() => {
                    setSelected(null);
                    setRendered(null);
                  }}
                  className="text-sm text-gray-500 underline"
                >
                  בחירת תבנית אחרת
                </button>
              )}
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
              onClick={openLinkAndMark}
              disabled={sending || !hasContact}
              className="w-full rounded-lg bg-gray-900 text-white py-3 font-medium flex items-center justify-center gap-2 disabled:opacity-50"
            >
              {ctaIcon}
              {ctaLabel}
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
