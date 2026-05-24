"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { X } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { ServiceCategory, SourceChannel } from "@/lib/types";

// טופס מהיר 3 שדות לפי האפיון: שם, טלפון, מקור.
// שאר הפרטים אפשר למלא אחר כך מכרטיס הליד.
export function NewLeadModal({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const router = useRouter();
  const [fullName, setFullName] = useState("");
  const [phone, setPhone] = useState("");
  // אופציונלי לפי Spec §7.1 — ברירת מחדל "ללא קטגוריה". נועה תסווג
  // אחר כך מהכרטיס. ראה F-04 ב-docs/spec-deviations.md.
  const [category, setCategory] = useState<ServiceCategory | "">("");
  const [source, setSource] = useState<SourceChannel>("manual");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!open) return null;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const lead = await api.createLead({
        full_name: fullName.trim(),
        phone: phone.trim() || null,
        service_category: category || null,
        source_channel: source,
      });
      onClose();
      router.push(`/leads/${lead.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "שגיאה ביצירת הליד");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 bg-black/40 flex items-end sm:items-center justify-center">
      <div className="bg-white w-full sm:max-w-md sm:rounded-2xl rounded-t-2xl shadow-xl">
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100">
          <h2 className="font-semibold">ליד חדש</h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600"
            aria-label="סגירה"
          >
            <X size={20} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-4 space-y-4">
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
                setCategory(e.target.value as ServiceCategory | "")
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

          {error && (
            <div className="text-sm text-state-red bg-state-red/10 rounded-lg px-3 py-2">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={submitting || !fullName.trim()}
            className="w-full rounded-lg bg-gray-900 text-white py-3 font-medium disabled:opacity-50"
          >
            {submitting ? "יוצרת ליד…" : "צרי ליד"}
          </button>
        </form>
      </div>
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
