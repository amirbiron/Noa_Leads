"use client";

import { useEffect, useState } from "react";
import { X } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import {
  PREFERRED_CONTACT_LABELS,
  PRIORITY_LABELS,
  SERVICE_CATEGORY_LABELS,
  SERVICE_SUBTYPE_LABELS,
} from "@/lib/hebrew";
import { SUBTYPES_BY_CATEGORY } from "@/lib/serviceCategories";
import type {
  Lead,
  PreferredContact,
  PriorityLevel,
  ServiceCategory,
} from "@/lib/types";
import { VoiceRecorderButton } from "./VoiceRecorderButton";

// עריכת שדות אופציונליים של ליד אחרי יצירה. ה-NewLeadModal המורחב כבר
// תומך באותם שדות בעת יצירה (כפתור "הוסף פרטים נוספים"); כאן עורכים
// אחרי יצירה, חוץ ממה שמנוהל ע"י flows ייעודיים:
// - source_channel: נקבע ב-intake, לא משתנה אחרי.
// - waiting_on: מנוהל ע"י chips / actions / transfer.
// - owner_id: transfer flow ייעודי.
// - utm_*: intake metadata, לא לעריכה ידנית.
// - is_returning_customer: בעת היצירה בלבד דרך NewLeadModal (LeadUpdate
//   לא תומך כרגע; אם בעתיד נרצה לערוך — להוסיף ל-LeadUpdate schema).

interface Props {
  lead: Lead;
  open: boolean;
  onClose: () => void;
  onSaved: () => void;
}

export function EditLeadModal({ lead, open, onClose, onSaved }: Props) {
  const [fullName, setFullName] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [organization, setOrganization] = useState("");
  const [category, setCategory] = useState<ServiceCategory | "">("");
  const [subtype, setSubtype] = useState<string>("");
  const [preferredContact, setPreferredContact] =
    useState<PreferredContact>("whatsapp");
  const [priority, setPriority] = useState<PriorityLevel>("normal");
  const [personalNote, setPersonalNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // איפוס לערכי הליד הנוכחיים רק כשהמודאל נפתח או כשמדובר בליד אחר
  // (lead.id משתנה). ה-deps *לא* כוללים את `lead` כאובייקט — load()
  // של ה-parent (במיוחד window-focus refetch) יוצר אובייקט חדש בכל
  // קריאה, ואם useEffect היה רץ אז — קלט שנועה כתבה היה נמחק באמצע.
  // אם נועה מעוניינת לראות שינויים שקרו ב-DB בינתיים, היא תסגור ותפתח.
  useEffect(() => {
    if (!open) return;
    setFullName(lead.full_name);
    setPhone(lead.phone ?? "");
    setEmail(lead.email ?? "");
    setOrganization(lead.organization_name ?? "");
    setCategory((lead.service_category ?? "") as ServiceCategory | "");
    setSubtype(lead.service_subtype ?? "");
    setPreferredContact(
      (lead.preferred_contact ?? "whatsapp") as PreferredContact,
    );
    setPriority((lead.priority_level ?? "normal") as PriorityLevel);
    setPersonalNote(lead.personal_note ?? "");
    setBusy(false);
    setError(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, lead.id]);

  // שינוי קטגוריה מאפס subtype אם הוא לא תואם — חסכון מהמשתמש שגיאת
  // backend (subtype לא תואם לקטגוריה).
  function handleCategoryChange(c: ServiceCategory | "") {
    setCategory(c);
    if (c === "" || !SUBTYPES_BY_CATEGORY[c]?.includes(subtype)) {
      setSubtype("");
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!fullName.trim()) {
      setError("שם הוא שדה חובה");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      // PATCH — null מפורש מאפס שדה ב-DB (תואם reject_explicit_null
      // ב-LeadUpdate: full_name/waiting_on/priority/preferred_contact הם
      // NOT NULL ולא נשלח אותם כ-null; שאר השדות nullable).
      await api.updateLead(lead.id, {
        full_name: fullName.trim(),
        phone: phone.trim() || null,
        email: email.trim() || null,
        organization_name: organization.trim() || null,
        service_category: (category || null) as ServiceCategory | null,
        service_subtype: subtype || null,
        preferred_contact: preferredContact,
        priority_level: priority,
        personal_note: personalNote.trim() || null,
      });
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "שגיאה בעדכון הליד");
    } finally {
      setBusy(false);
    }
  }

  if (!open) return null;

  const subtypeOptions = category ? SUBTYPES_BY_CATEGORY[category] : [];

  return (
    // dvh ולא vh כדי שמקסימום הגובה יתחשב בקיווה הכתובת/keyboard של מובייל
    // (iOS Safari דחף תוכן מעל המסך עם vh). flex-col + shrink-0 על header
    // ו-footer + overflow-y-auto על body מבטיח שהכותרת + הכפתורים תמיד
    // נשארים גלויים גם בטופס ארוך. ה-form עוטף את כל המבנה כדי שכפתור
    // submit בfooter יעבוד.
    <div className="fixed inset-0 z-50 bg-black/40 flex items-end sm:items-center justify-center">
      <form
        onSubmit={handleSubmit}
        className="bg-white w-full sm:max-w-md sm:rounded-2xl rounded-t-2xl shadow-xl max-h-[95dvh] flex flex-col"
      >
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100 shrink-0">
          <h2 className="font-semibold">עריכת ליד</h2>
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
          <Field label="שם מלא *">
            <input
              required
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-base focus:border-gray-900 focus:outline-none"
            />
          </Field>

          <Field label="טלפון">
            <input
              type="tel"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-base focus:border-gray-900 focus:outline-none"
              dir="ltr"
            />
          </Field>

          <Field label="מייל">
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-base focus:border-gray-900 focus:outline-none"
              dir="ltr"
            />
          </Field>

          <Field label="ארגון (אם רלוונטי)">
            <input
              value={organization}
              onChange={(e) => setOrganization(e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-base focus:border-gray-900 focus:outline-none"
            />
          </Field>

          <Field label="קטגוריה">
            <select
              value={category}
              onChange={(e) =>
                handleCategoryChange(e.target.value as ServiceCategory | "")
              }
              className="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-base focus:border-gray-900 focus:outline-none bg-white"
            >
              <option value="">— ללא קטגוריה —</option>
              {(Object.keys(SERVICE_CATEGORY_LABELS) as ServiceCategory[]).map(
                (c) => (
                  <option key={c} value={c}>
                    {SERVICE_CATEGORY_LABELS[c]}
                  </option>
                ),
              )}
            </select>
          </Field>

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
              onChange={(e) => setPriority(e.target.value as PriorityLevel)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-base focus:border-gray-900 focus:outline-none bg-white"
            >
              {(Object.keys(PRIORITY_LABELS) as PriorityLevel[]).map((p) => (
                <option key={p} value={p}>
                  {PRIORITY_LABELS[p]}
                </option>
              ))}
            </select>
          </Field>

          <Field label="הערה אישית (לא נשלחת ללקוח)">
            <textarea
              value={personalNote}
              onChange={(e) => setPersonalNote(e.target.value)}
              rows={3}
              placeholder="פרט שכדאי לזכור — שם בן הזוג, העדפה, וכו'"
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-gray-900 focus:outline-none"
            />
            {/* תיעוד קולי (§13.3) — appen, לא דורס. נועה רואה את הטקסט
                ב-textarea ויכולה לערוך לפני שמירה. אם MediaRecorder לא
                נתמך (iOS Safari < 14.5), הכפתור מסתיר את עצמו. */}
            <div className="mt-2">
              <VoiceRecorderButton
                leadId={lead.id}
                disabled={busy}
                onTranscribed={(text) =>
                  setPersonalNote((prev) =>
                    prev.trim() ? `${prev.trimEnd()}\n${text}` : text,
                  )
                }
              />
            </div>
          </Field>

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
            disabled={busy}
            className="flex-1 rounded-lg bg-gray-100 text-gray-800 py-3 font-medium disabled:opacity-50"
          >
            ביטול
          </button>
          <button
            type="submit"
            disabled={busy || !fullName.trim()}
            className="flex-1 rounded-lg bg-gray-900 text-white py-3 font-medium disabled:opacity-50"
          >
            {busy ? "שומרת…" : "שמירה"}
          </button>
        </div>
      </form>
    </div>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <div className="text-sm font-medium text-gray-700 mb-1.5">{label}</div>
      {children}
    </label>
  );
}
