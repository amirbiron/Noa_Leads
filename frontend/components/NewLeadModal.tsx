"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ChevronDown, ChevronUp, X } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import {
  PREFERRED_CONTACT_LABELS,
  PRIORITY_LABELS,
  SERVICE_SUBTYPE_LABELS,
} from "@/lib/hebrew";
import { LEAD_MANUALLY_CREATED_EVENT } from "@/lib/leadEvents";
import { SUBTYPES_BY_CATEGORY } from "@/lib/serviceCategories";
import type {
  PreferredContact,
  PriorityLevel,
  ServiceCategory,
  SourceChannel,
} from "@/lib/types";
import { TermHint } from "./TermHint";
import { VoiceRecorderButton } from "./VoiceRecorderButton";

// טופס יצירת ליד. שדות חובה לפי §7.1 (שם, טלפון, מקור, תוכן הפנייה) +
// קטגוריה אופציונלית מוצגים תמיד. כפתור "הוסף פרטים נוספים" חושף את
// שדות §7.2 (subtype, מייל, ארגון, ערוץ מועדף, עדיפות, חדש/חוזר, הערה
// אישית) כך שאפשר למלא הכל בפתיחה במקום להיכנס לעריכה אחרי יצירה.
export function NewLeadModal({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const router = useRouter();
  // ===== שדות בסיס (תמיד גלויים) =====
  const [fullName, setFullName] = useState("");
  const [phone, setPhone] = useState("");
  // אופציונלי לפי Spec §7.1 — ברירת מחדל "ללא קטגוריה". נועה תסווג
  // אחר כך מהכרטיס. ראה F-04 ב-docs/spec-deviations.md.
  const [category, setCategory] = useState<ServiceCategory | "">("");
  const [source, setSource] = useState<SourceChannel>("manual");
  // תוכן הפנייה — חובה. בלי זה אין הקשר לליד. §7.1.
  const [leadMessage, setLeadMessage] = useState("");

  // ===== שדות expand (§7.2) =====
  const [expanded, setExpanded] = useState(false);
  const [email, setEmail] = useState("");
  const [organization, setOrganization] = useState("");
  const [subtype, setSubtype] = useState("");
  const [preferredContact, setPreferredContact] =
    useState<PreferredContact>("whatsapp");
  const [priority, setPriority] = useState<PriorityLevel>("normal");
  const [isReturning, setIsReturning] = useState(false);
  const [personalNote, setPersonalNote] = useState("");

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!open) return null;

  // שינוי קטגוריה מאפס subtype אם הוא לא תואם — חסכון מהמשתמש שגיאת
  // backend (subtype לא תואם לקטגוריה). אותה לוגיקה כמו EditLeadModal.
  function handleCategoryChange(c: ServiceCategory | "") {
    setCategory(c);
    if (c === "" || !SUBTYPES_BY_CATEGORY[c]?.includes(subtype)) {
      setSubtype("");
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      // כל שדות ה-expand נשלחים גם אם ה-section מקופל — ה-state נשמר
      // כשהמשתמש פותח/סוגר ושומר. ריקים → null (חוץ מ-boolean ו-enums
      // עם default).
      const lead = await api.createLead({
        full_name: fullName.trim(),
        phone: phone.trim() || null,
        email: email.trim() || null,
        organization_name: organization.trim() || null,
        service_category: category || null,
        service_subtype: subtype || null,
        source_channel: source,
        preferred_contact: preferredContact,
        priority_level: priority,
        is_returning_customer: isReturning,
        personal_note: personalNote.trim() || null,
        lead_message: leadMessage.trim(),
      });
      // event ל-useDashboardPoll: הליד הזה נוצר ידנית, לא להציג עליו
      // toast "ליד חדש" בpoll הבא. ה-hook מחזיק Set עם TTL של 5 דקות.
      window.dispatchEvent(
        new CustomEvent(LEAD_MANUALLY_CREATED_EVENT, {
          detail: { id: lead.id },
        }),
      );
      onClose();
      router.push(`/leads/${lead.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "שגיאה ביצירת הליד");
    } finally {
      setSubmitting(false);
    }
  }

  const subtypeOptions = category ? SUBTYPES_BY_CATEGORY[category] : [];

  return (
    // dvh + flex-col + sticky header/footer — מבטיח שהכותרת והכפתורים
    // נשארים גלויים גם בטופס ארוך וגם כשkeyboard נפתח במובייל.
    <div className="fixed inset-0 z-50 bg-black/40 flex items-end sm:items-center justify-center">
      <form
        onSubmit={handleSubmit}
        className="bg-white w-full sm:max-w-md sm:rounded-2xl rounded-t-2xl shadow-xl max-h-[95dvh] flex flex-col"
      >
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100 shrink-0">
          <h2 className="font-semibold flex items-center">
            ליד חדש
            <TermHint termKey="concept_lead" />
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600"
            aria-label="סגירה"
          >
            <X size={20} />
          </button>
        </div>

        <div className="overflow-y-auto p-4 space-y-4">
          <Field label="שם מלא">
            <input
              required
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-base focus:border-gray-900 focus:outline-none"
              placeholder="לדוגמה: שרה לוי"
              autoFocus
            />
          </Field>

          <Field label="טלפון">
            <input
              type="tel"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-base focus:border-gray-900 focus:outline-none"
              placeholder="050-1234567"
              dir="ltr"
            />
          </Field>

          <Field label="קטגוריה (אופציונלי)">
            <select
              value={category}
              onChange={(e) =>
                handleCategoryChange(e.target.value as ServiceCategory | "")
              }
              className="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-base focus:border-gray-900 focus:outline-none"
            >
              <option value="">— לבחור מאוחר יותר —</option>
              <option value="clinic">קליניקה</option>
              <option value="workshops">סדנאות והרצאות</option>
              <option value="production">ליווי והפקות</option>
              <option value="digital_course">קורס דיגיטלי</option>
            </select>
          </Field>

          <Field label="מקור הפנייה">
            <select
              value={source}
              onChange={(e) => setSource(e.target.value as SourceChannel)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-base focus:border-gray-900 focus:outline-none"
            >
              <option value="manual">הזנה ידנית</option>
              <option value="referral">המלצה</option>
              <option value="form">טופס באתר</option>
              <option value="whatsapp">וואטסאפ</option>
              <option value="email">מייל</option>
              <option value="facebook">פייסבוק</option>
              <option value="instagram">אינסטגרם</option>
              <option value="other">אחר</option>
            </select>
          </Field>

          <Field label="תוכן הפנייה">
            <textarea
              required
              value={leadMessage}
              onChange={(e) => setLeadMessage(e.target.value)}
              rows={4}
              className="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-base focus:border-gray-900 focus:outline-none"
              placeholder="הדבק כאן את ההודעה שהגיעה בוואטסאפ / תאר במילים שלך מה הלקוח רצה"
            />
            {/* הקלטה — נועה יכולה לדבר במקום להקליד. הקונטקסט שנשלח
                ל-OpenAI הוא מה שכבר הוקלד (שם/קטגוריה) כדי לשפר דיוק
                שמות. ראה VoiceRecorderButton mode="new". */}
            <div className="mt-2">
              <VoiceRecorderButton
                mode="new"
                context={{
                  leadName: fullName.trim() || null,
                  serviceCategory: category || null,
                  serviceSubtype: subtype || null,
                }}
                disabled={submitting}
                onTranscribed={(text) =>
                  setLeadMessage((prev) =>
                    prev.trim() ? `${prev.trimEnd()}\n${text}` : text,
                  )
                }
              />
            </div>
          </Field>

          {/* כפתור הרחבה — חושף את שדות §7.2 שאינם חובה ליצירה. */}
          <button
            type="button"
            onClick={() => setExpanded((e) => !e)}
            className="w-full flex items-center justify-center gap-1.5 text-sm text-gray-600 hover:text-gray-900 py-2 border-t border-gray-100"
            aria-expanded={expanded}
            aria-controls="new-lead-expand-section"
          >
            {expanded ? (
              <ChevronUp size={16} aria-hidden />
            ) : (
              <ChevronDown size={16} aria-hidden />
            )}
            <span>
              {expanded ? "הסתר פרטים נוספים" : "הוסף פרטים נוספים"}
            </span>
          </button>

          {expanded && (
            <div id="new-lead-expand-section" className="space-y-4">
              <Field label="מייל">
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-base focus:border-gray-900 focus:outline-none"
                  placeholder="name@example.com"
                  dir="ltr"
                />
              </Field>

              <Field label="ארגון (אם רלוונטי)">
                <input
                  value={organization}
                  onChange={(e) => setOrganization(e.target.value)}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-base focus:border-gray-900 focus:outline-none"
                  placeholder="לדוגמה: עיריית רעננה"
                />
              </Field>

              {/* sub-type מותנה ב-category — כמו ב-EditLeadModal. */}
              {category && subtypeOptions.length > 0 && (
                <Field label="סוג שירות">
                  <select
                    value={subtype}
                    onChange={(e) => setSubtype(e.target.value)}
                    className="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-base focus:border-gray-900 focus:outline-none bg-white"
                  >
                    <option value="">— ללא סוג —</option>
                    {subtypeOptions.map((s) => (
                      <option key={s} value={s}>
                        {SERVICE_SUBTYPE_LABELS[s] ?? s}
                      </option>
                    ))}
                  </select>
                </Field>
              )}

              <Field label="ערוץ תקשורת מועדף">
                <select
                  value={preferredContact}
                  onChange={(e) =>
                    setPreferredContact(e.target.value as PreferredContact)
                  }
                  className="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-base focus:border-gray-900 focus:outline-none bg-white"
                >
                  {(
                    Object.keys(PREFERRED_CONTACT_LABELS) as PreferredContact[]
                  ).map((c) => (
                    <option key={c} value={c}>
                      {PREFERRED_CONTACT_LABELS[c]}
                    </option>
                  ))}
                </select>
              </Field>

              <Field label="עדיפות">
                <select
                  value={priority}
                  onChange={(e) =>
                    setPriority(e.target.value as PriorityLevel)
                  }
                  className="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-base focus:border-gray-900 focus:outline-none bg-white"
                >
                  {(Object.keys(PRIORITY_LABELS) as PriorityLevel[]).map(
                    (p) => (
                      <option key={p} value={p}>
                        {PRIORITY_LABELS[p]}
                      </option>
                    ),
                  )}
                </select>
              </Field>

              {/* checkbox יחיד במקום radio של 2 אופציות — קומפקטי, default
                  unchecked = חדש (תואם default False ב-backend). */}
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={isReturning}
                  onChange={(e) => setIsReturning(e.target.checked)}
                  className="w-4 h-4 rounded border-gray-300 text-gray-900 focus:ring-gray-900"
                />
                <span className="text-sm text-gray-700">
                  לקוח חוזר (עבד עם נועה בעבר)
                </span>
              </label>

              <Field label="הערה אישית (לא נשלחת ללקוח)">
                <textarea
                  value={personalNote}
                  onChange={(e) => setPersonalNote(e.target.value)}
                  rows={3}
                  placeholder="פרט שכדאי לזכור — שם בן הזוג, העדפה, וכו'"
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-gray-900 focus:outline-none"
                />
                <div className="mt-2">
                  <VoiceRecorderButton
                    mode="new"
                    context={{
                      leadName: fullName.trim() || null,
                      serviceCategory: category || null,
                      serviceSubtype: subtype || null,
                    }}
                    disabled={submitting}
                    onTranscribed={(text) =>
                      setPersonalNote((prev) =>
                        prev.trim() ? `${prev.trimEnd()}\n${text}` : text,
                      )
                    }
                  />
                </div>
              </Field>
            </div>
          )}

          {error && (
            <div className="text-sm text-state-red bg-state-red/10 rounded-lg px-3 py-2">
              {error}
            </div>
          )}
        </div>

        <div className="border-t border-gray-100 p-3 flex gap-2 shrink-0">
          <button
            type="button"
            onClick={onClose}
            disabled={submitting}
            className="flex-1 rounded-lg bg-gray-100 text-gray-800 py-3 font-medium disabled:opacity-50"
          >
            ביטול
          </button>
          <button
            type="submit"
            disabled={submitting || !fullName.trim() || !leadMessage.trim()}
            className="flex-1 rounded-lg bg-gray-900 text-white py-3 font-medium disabled:opacity-50"
          >
            {submitting ? "יוצרת ליד…" : "צרי ליד"}
          </button>
        </div>
      </form>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <div className="text-sm font-medium text-gray-700 mb-1.5">{label}</div>
      {children}
    </label>
  );
}
