"use client";

import { useEffect, useState } from "react";
import { Copy, Mail, MessageCircle, X } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { toWhatsAppDigits } from "@/lib/phone";
import type { Lead, Template, TemplateRenderResponse } from "@/lib/types";

type EffectiveChannel = "whatsapp" | "email";

// UUIDs קנוניים של תבניות הצעת מחיר (Spec §16.4 + seed 0009). מחובר
// ל-_CANONICAL_TEMPLATES ב-backend/app/services/templates.py — שינוי
// שם דורש עדכון בשני המקומות. מוגדר ב-frontend כדי שב-manual mode
// (כש-/templates/auto החזיר 404 ו-user בוחר חופשי) נדע אם הוא בחר
// תבנית הצעה אמיתית או רק תבנית פתיחה רגילה. השפעה: actionType.
const CANONICAL_PROPOSAL_TEMPLATE_IDS: ReadonlySet<string> = new Set([
  "00000000-0000-0009-0000-000000000008", // T8 "הצעת מחיר - סדנה" (org)
  "00000000-0000-0009-0000-000000000009", // T9 "הצעת תוכנית - שיקום" (private)
]);

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
  // נדלק כשנכשלה טעינת תבנית הקנונית (preset mode) — נופלים למסך
  // manual list עם רשימה מלאה. בלי זה ה-flow נחסם על error בלי דרך
  // המשתמש להמשיך פרט לסגירה (תיקון bugbot).
  const [presetFailed, setPresetFailed] = useState(false);

  // האם להציג את ה-manual list view (בחירה מרשימה).
  // - אם אין presetTemplateId → תמיד manual.
  // - אם יש presetTemplateId אבל ה-getTemplate/renderTemplate נכשלו → fallback ל-manual.
  const inManualMode = !presetTemplateId || presetFailed;

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    setSelected(null);
    setRendered(null);
    setError(null);
    setTemplates([]);
    setPresetFailed(false);

    // cancelled flag למקרה ש-useEffect שב לרוץ (פותחים/סוגרים מהר) או
    // ה-component unmounts במהלך fetch. בלי זה ה-setState יקרא אחרי
    // unmount — warning של React (לא קריסה, אבל מיותר).
    let cancelled = false;

    // תמיד טוענים את כל הרשימה הפעילה — בלי סינון channel/audience.
    // - manual mode (אין preset): מציג רשימה.
    // - preset mode: רשימה pre-loaded כדי שfallback (preset failure) יהיה
    //   instant, בלי refetch.
    // הרשימה ~10 שורות, זול.
    const loadList = async () => {
      try {
        const items = await api.listTemplates(true);
        if (!cancelled) setTemplates(items);
      } catch (err) {
        if (!cancelled) {
          // לא דורסים error קיים מ-preset שכבר נכשל.
          setError((prev) =>
            prev || (err instanceof ApiError ? err.message : "שגיאה בטעינה"),
          );
        }
      }
    };

    const loadPreset = async () => {
      if (!presetTemplateId) return;
      try {
        const tpl = await api.getTemplate(presetTemplateId);
        if (cancelled) return;
        // render inline (לא דרך pickTemplate) — pickTemplate לא יכול
        // לבדוק את ה-cancelled flag הזה (סקופ של useEffect), ובלי הבדיקה
        // renderTemplate איטי שמסתיים אחרי close/preset-change היה דורס
        // את ה-UI עם preview ישן (תיקון bugbot stale race).
        try {
          const r = await api.renderTemplate(tpl.id, lead.id);
          if (cancelled) return;
          setSelected(tpl);
          setRendered(r);
        } catch (err) {
          if (cancelled) return;
          setError(err instanceof ApiError ? err.message : "שגיאה ברנדור");
          // render נכשל אחרי ש-getTemplate הצליח — fallback ל-manual.
          // הרשימה כבר נטענת במקביל, אז המעבר instant.
          setPresetFailed(true);
        }
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof ApiError ? err.message : "שגיאה בטעינה");
        setPresetFailed(true);
      }
    };

    // הרצה מקבילית — שניהם רצים יחד; setLoading(false) רק אחרי שגם
    // הרשימה וגם ה-preset (כולל render) הסתיימו.
    void Promise.all([loadList(), loadPreset()]).finally(() => {
      if (!cancelled) setLoading(false);
    });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, presetTemplateId]);

  // נקראת רק מ-manual list click (לא מ-useEffect ה-preset path).
  // ה-preset path מבצע render inline עם cancellation. כאן user-initiated,
  // ה-race דומה אבל פחות שכיח (כל קליק מתחיל render חדש; אם user מקליק
  // מהר תבניות שונות ויש latency משתנה, ייתכן שתבנית ישנה תדרוס חדשה —
  // edge case לא מטופל עכשיו, לא הועלה ע"י bugbot).
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

  // ה-channel האפקטיבי:
  // 1. forceChannel (preferred_contact='email') — מנצח תמיד. אם המשתמשת
  //    קבעה במפורש email על הליד, נכבד את זה גם אם אין email בליד
  //    (CTA יחסם עם "אין מייל" — היא תעדכן את הליד).
  // 2. template.channel — ברירת מחדל לפי seed (T2/T8 = email, השאר = WA).
  // 3. **fallback אוטומטי** (תיקון bugbot): אם ה-template ביקש email אבל
  //    אין email ויש phone — נשלח ב-WA. רלוונטי לליד org בלי email pref
  //    (default WA) שהקנונית שלו T2/T8 (email) אבל יש לו רק phone. בלי
  //    הfallback הזה הכפתור הראשי היה חסום ("אין מייל") למרות שאפשר
  //    לשלוח. הfallback רץ רק כש-forceChannel לא נכפה — pref מפורש מנצח.
  const idealChannel: EffectiveChannel =
    forceChannel ?? (selected?.channel === "email" ? "email" : "whatsapp");
  const effectiveChannel: EffectiveChannel =
    !forceChannel && idealChannel === "email" && !lead.email && lead.phone
      ? "whatsapp"
      : idealChannel;

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

      // ה-action האפקטיבי: מבוסס על *התבנית הנבחרת*, לא רק על ה-role.
      // ב-preset mode הקנונית תואמת ל-role — actionType מתאים.
      // ב-manual mode (preset failed / secondary picker) המשתמשת בוחרת
      // חופשי:
      //   - אם בחרה תבנית הצעה קנונית (T8/T9) → mark_proposal_sent
      //     (מקדם ל-PROPOSAL_SENT, יוצר PROPOSAL_FOLLOWUP task).
      //   - אחרת → mark_template_sent (לא מקדם סטטוס מ-IN_PROGRESS,
      //     רק last_outbound + activity + auto-close tasks).
      // תיקון דו-כיווני של 2 ממצאי bugbot: לא לקדם בטעות ל-PROPOSAL_SENT
      // עם תבנית פתיחה, אבל גם לא לחסום קידום כשהמשתמשת באמת בוחרת תבנית
      // הצעה ידנית.
      const isProposalTemplate = CANONICAL_PROPOSAL_TEMPLATE_IDS.has(selected.id);
      const effectiveActionType: typeof actionType =
        inManualMode
          ? actionType === "mark_proposal_sent" && isProposalTemplate
            ? "mark_proposal_sent"
            : "mark_template_sent"
          : actionType;

      // רק אחרי שהפתיחה הצליחה (WA) / handoff בוצע (mailto) — סימון במערכת.
      // ה-action (mark_template_sent או mark_proposal_sent) מעדכן סטטוס +
      // activity + סוגר tasks (AUTO_CLOSE_TASK_TYPES). פירוט ב-state_machine.py.
      await api.performAction(lead.id, effectiveActionType, {
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

  // inManualMode = אין preset, או שה-preset נכשל ונפלנו ל-fallback.
  // משפיע על: כותרת ה-sheet, הצגת הרשימה, "בחירת תבנית אחרת".
  const sheetTitle = inManualMode ? "בחרי תבנית" : "שליחה";
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
      <div className="bg-white w-full sm:max-w-md sm:rounded-2xl rounded-t-2xl shadow-xl max-h-[90dvh] flex flex-col">
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

          {!loading && inManualMode && templates.length === 0 && (
            <div className="text-sm text-gray-500 text-center py-4">
              אין תבניות פעילות. צרי תבנית מ-/templates.
            </div>
          )}

          {!rendered &&
            inManualMode &&
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

              {/* "בחירת תבנית אחרת" רק במצב manual (כולל אחרי preset fallback) */}
              {inManualMode && (
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
