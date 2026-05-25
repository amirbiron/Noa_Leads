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
import type {
  Lead,
  PreferredContact,
  PriorityLevel,
  ServiceCategory,
} from "@/lib/types";

// עריכת שדות אופציונליים של ליד אחרי יצירה. הטופס המהיר ב-NewLeadModal
// קולט רק 3 שדות חובה (שם, טלפון, מקור) + קטגוריה אופציונלית; עורך כל
// שאר ה-fields כאן, חוץ ממה שמנוהל ע"י flows ייעודיים:
// - source_channel: נקבע ב-intake, לא משתנה אחרי.
// - waiting_on: מנוהל ע"י chips / actions / transfer.
// - owner_id: transfer flow ייעודי.
// - utm_*: intake metadata, לא לעריכה ידנית.

// subtypes לכל קטגוריה — מקביל ל-SERVICE_CATEGORIES ב-backend/app/constants.py.
// שינוי שם של subtype או הוספה דורש עדכון בשני המקומות.
const SUBTYPES_BY_CATEGORY: Record<ServiceCategory, string[]> = {
  clinic: ["voice_development", "public_speaking", "voice_rehab"],
  workshops: [
    "workshop_speaking",
    "stage_arts",
    "lecture_organization",
    "lecture_academic",
  ],
  production: ["production_guidance", "production_directing"],
  digital_course: ["digital_course"],
};

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
    <div className="fixed inset-0 z-50 bg-black/40 flex items-end sm:items-center justify-center">
      <div className="bg-white w-full sm:max-w-md sm:rounded-2xl rounded-t-2xl shadow-xl max-h-[95vh] flex flex-col">
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100 shrink-0">
          <h2 className="font-semibold">עריכת ליד</h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600"
            aria-label="סגירה"
          >
            <X size={20} />
          </button>
        </div>

        <form
          onSubmit={handleSubmit}
          className="overflow-y-auto p-4 space-y-4"
        >
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
          </Field>

          {error && (
            <div className="text-sm text-state-red bg-state-red/10 rounded-lg px-3 py-2">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={busy || !fullName.trim()}
            className="w-full rounded-lg bg-gray-900 text-white py-3 font-medium disabled:opacity-50"
          >
            {busy ? "שומרת…" : "שמירה"}
          </button>
        </form>
      </div>
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
