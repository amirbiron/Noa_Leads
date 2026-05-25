"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import {
  ArrowRightLeft,
  CalendarPlus,
  FileText,
  Mail,
  MessageCircle,
  Phone,
  Plus,
  Send,
  XCircle,
} from "lucide-react";
import { AddProgramModal } from "@/components/AddProgramModal";
import { AppShell } from "@/components/AppShell";
import { CloseLeadModal } from "@/components/CloseLeadModal";
import { DynamicActionButton } from "@/components/DynamicActionButton";
import { PendingBookingCard } from "@/components/PendingBookingCard";
import { ProgramCard } from "@/components/ProgramCard";
import { QuickActions } from "@/components/QuickActions";
import { SectionHeader } from "@/components/SectionHeader";
import { StateBadge } from "@/components/StateBadge";
import { TemplatePickerSheet } from "@/components/TemplatePickerSheet";
import { Timeline } from "@/components/Timeline";
import { TransferLeadModal } from "@/components/TransferLeadModal";
import { api, ApiError } from "@/lib/api";
import { toWhatsAppDigits } from "@/lib/phone";
import {
  labelCategory,
  labelContact,
  labelPriority,
  labelStatus,
  labelSubtype,
  labelWaiting,
} from "@/lib/hebrew";
import type {
  Activity,
  BookingRead,
  Lead,
  Program,
  StateColor,
} from "@/lib/types";

function inferStateColor(lead: Lead): StateColor {
  if (["WON", "LOST", "ARCHIVED"].includes(lead.status)) return "gray";
  if (lead.needs_attention) return "red";
  if (lead.next_action_due_at) {
    const due = new Date(lead.next_action_due_at).getTime();
    const now = Date.now();
    if (due <= now) return "red";
    if (due <= now + 48 * 60 * 60 * 1000) return "orange";
  }
  return "green";
}

export default function LeadDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const [lead, setLead] = useState<Lead | null>(null);
  const [activities, setActivities] = useState<Activity[]>([]);
  const [programs, setPrograms] = useState<Program[]>([]);
  const [activeBooking, setActiveBooking] = useState<BookingRead | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [templateOpen, setTemplateOpen] = useState(false);
  const [closeOpen, setCloseOpen] = useState(false);
  const [transferOpen, setTransferOpen] = useState(false);
  const [programOpen, setProgramOpen] = useState(false);
  const [reopening, setReopening] = useState(false);

  async function load() {
    setError(null);
    try {
      const [l, t, p, b] = await Promise.all([
        api.getLead(id),
        api.getTimeline(id),
        api.listProgramsForLead(id),
        // active booking — מוצג בכרטיס אישור/דחייה כשהליד ב-BOOKING_PENDING.
        // נטען תמיד (גם כשהליד לא pending) כי זול ומאפשר תצוגה גם של booking
        // approved בעתיד (שלב 14+).
        api.getActiveBookingForLead(id),
      ]);
      setLead(l);
      setActivities(t);
      setPrograms(p);
      setActiveBooking(b);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "שגיאה בטעינה");
    } finally {
      setLoading(false);
    }
  }

  async function handleReopen() {
    setReopening(true);
    setError(null);
    try {
      await api.reopenLead(id);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "שגיאה בפתיחה מחדש");
    } finally {
      setReopening(false);
    }
  }

  useEffect(() => {
    if (!id) return;
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  return (
    <AppShell>
      {loading && (
        <div className="text-center text-gray-400 py-10 text-sm">טוען…</div>
      )}
      {error && (
        <div className="text-sm text-state-red bg-state-red/10 rounded-lg px-3 py-2">
          {error}
        </div>
      )}

      {lead && (
        <div className="space-y-4">
          {/* Header */}
          <div className="bg-white rounded-xl border border-gray-200 p-4">
            <div className="flex items-start justify-between gap-2">
              <div>
                <div className="text-lg font-semibold flex items-center gap-2">
                  <span>{lead.full_name}</span>
                  {lead.waiting_on === "CLIENT" && (
                    <span
                      className="text-base"
                      aria-label="מחכה ללקוח"
                      title="מחכה ללקוח"
                    >
                      ⏳
                    </span>
                  )}
                </div>
                {lead.organization_name && (
                  <div className="text-sm text-gray-500">
                    {lead.organization_name}
                  </div>
                )}
                <div className="text-sm text-gray-700 mt-1">
                  {labelCategory(lead.service_category)}
                  {lead.service_subtype &&
                    ` · ${labelSubtype(lead.service_subtype)}`}
                </div>
              </div>
              {/* תיוג "תקין" (ירוק) מיותר — מצב ירוק הוא ברירת המחדל ואין
                  צורך לסמן. רק red/orange/gray (אדום/בקרוב/סגור) ראויים badge. */}
              {inferStateColor(lead) !== "green" && (
                <StateBadge color={inferStateColor(lead)} />
              )}
            </div>

            <div className="grid grid-cols-2 gap-2 mt-3 text-xs">
              <Meta label="סטטוס" value={labelStatus(lead.status)} />
              <Meta label="ממתין" value={labelWaiting(lead.waiting_on)} />
              <Meta label="עדיפות" value={labelPriority(lead.priority_level)} />
              <Meta label="ערוץ" value={labelContact(lead.preferred_contact)} />
            </div>

            {/* פרטי קשר */}
            <div className="mt-3 flex flex-wrap gap-2">
              {lead.phone && (
                <a
                  href={`tel:${lead.phone}`}
                  className="inline-flex items-center gap-1.5 text-sm text-gray-700 bg-gray-100 px-2.5 py-1 rounded-full"
                >
                  <Phone size={14} aria-hidden />
                  <span dir="ltr">{lead.phone}</span>
                </a>
              )}
              {lead.phone && toWhatsAppDigits(lead.phone) && (
                <a
                  href={`https://wa.me/${toWhatsAppDigits(lead.phone)}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1.5 text-sm text-gray-700 bg-gray-100 px-2.5 py-1 rounded-full"
                >
                  <MessageCircle size={14} aria-hidden />
                  וואטסאפ
                </a>
              )}
              {lead.email && (
                <a
                  href={`mailto:${lead.email}`}
                  className="inline-flex items-center gap-1.5 text-sm text-gray-700 bg-gray-100 px-2.5 py-1 rounded-full"
                >
                  <Mail size={14} aria-hidden />
                  <span dir="ltr">{lead.email}</span>
                </a>
              )}
            </div>

            {lead.personal_note && (
              <div className="mt-3 bg-yellow-50 border border-yellow-200 rounded-lg px-3 py-2 text-sm text-yellow-900 flex items-start gap-2">
                <FileText size={14} className="mt-0.5 shrink-0" aria-hidden />
                <span>{lead.personal_note}</span>
              </div>
            )}
          </div>

          {/* בקשת תור ממתינה — בראש לפי החשיבות (קריאה לפעולה ראשונה
              שנועה צריכה) */}
          {activeBooking && activeBooking.status === "pending_approval" && (
            <PendingBookingCard booking={activeBooking} onChanged={load} />
          )}

          {/* כפתור "מה עכשיו?" — רק לליד פתוח */}
          {!["WON", "LOST", "ARCHIVED"].includes(lead.status) && (
            <DynamicActionButton
              lead={lead}
              activeBooking={activeBooking}
              onActionDone={load}
            />
          )}

          {/* כפתורי תבנית + העברה — רק לליד פתוח */}
          {!["WON", "LOST", "ARCHIVED"].includes(lead.status) && (
            <div className="grid grid-cols-2 gap-2">
              <button
                onClick={() => setTemplateOpen(true)}
                className="rounded-lg bg-white border border-gray-200 py-2.5 text-sm font-medium flex items-center justify-center gap-1.5"
              >
                {/* Send הוא מטוס נייר — "חץ שליחה" שצריך להישקף ב-RTL
                    לפי הסקיל (docs/Skills/hebrew-rtl-best-practices). */}
                <Send size={15} aria-hidden className="rtl:-scale-x-100" />
                בחירת תבנית
              </button>
              <button
                onClick={() => setTransferOpen(true)}
                className="rounded-lg bg-white border border-gray-200 py-2.5 text-sm font-medium flex items-center justify-center gap-1.5"
              >
                <ArrowRightLeft size={15} aria-hidden />
                העברה
              </button>
            </div>
          )}

          {/* קישור לדף קביעת תור — להעתקה ושיתוף עם הליד */}
          {!["WON", "LOST", "ARCHIVED"].includes(lead.status) && (
            <CopyBookingLinkButton token={lead.booking_token} />
          )}

          {/* תוכניות מתמשכות */}
          {(programs.length > 0 ||
            !["WON", "LOST", "ARCHIVED"].includes(lead.status)) && (
            <div>
              <div className="flex items-center justify-between mt-5 mb-2">
                <h2 className="text-sm font-semibold text-gray-700">
                  תוכניות
                  {programs.length > 0 && (
                    <span className="text-gray-400 font-normal me-1">
                      ({programs.length})
                    </span>
                  )}
                </h2>
                {!["WON", "LOST", "ARCHIVED"].includes(lead.status) && (
                  <button
                    onClick={() => setProgramOpen(true)}
                    className="inline-flex items-center gap-1 text-xs text-gray-600 hover:text-gray-900"
                  >
                    <Plus size={14} aria-hidden />
                    הוספה
                  </button>
                )}
              </div>
              {programs.length === 0 ? (
                <div className="bg-white rounded-xl border border-dashed border-gray-200 px-4 py-4 text-center text-xs text-gray-400">
                  אין תוכנית מתמשכת. אפשר להוסיף אם זה לקוח קבוע.
                </div>
              ) : (
                <ul className="space-y-2">
                  {programs.map((p) => (
                    <li key={p.id}>
                      <ProgramCard program={p} onChanged={load} />
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {/* צ'יפים לסיכום שיחה */}
          <div>
            <SectionHeader title="סיכומי שיחה" />
            <QuickActions lead={lead} onActionDone={load} />
          </div>

          {/* סגירה / פתיחה מחדש */}
          {!["WON", "LOST", "ARCHIVED"].includes(lead.status) ? (
            <button
              onClick={() => setCloseOpen(true)}
              className="w-full rounded-lg bg-white border border-state-red/40 text-state-red py-2.5 text-sm font-medium flex items-center justify-center gap-1.5"
            >
              <XCircle size={15} aria-hidden />
              סגירת ליד
            </button>
          ) : (
            <button
              onClick={handleReopen}
              disabled={reopening}
              className="w-full rounded-lg bg-white border border-gray-300 text-gray-700 py-2.5 text-sm font-medium disabled:opacity-50"
            >
              {reopening ? "פותחת…" : "פתיחה מחדש"}
            </button>
          )}

          {/* Timeline */}
          <div>
            <SectionHeader title="היסטוריה" count={activities.length} />
            <Timeline activities={activities} />
          </div>
        </div>
      )}

      {lead && (
        <>
          <TemplatePickerSheet
            lead={lead}
            open={templateOpen}
            onClose={() => setTemplateOpen(false)}
            onSent={load}
          />
          <CloseLeadModal
            lead={lead}
            open={closeOpen}
            onClose={() => setCloseOpen(false)}
            onClosed={load}
          />
          <TransferLeadModal
            lead={lead}
            open={transferOpen}
            onClose={() => setTransferOpen(false)}
            onTransferred={load}
          />
          <AddProgramModal
            leadId={lead.id}
            open={programOpen}
            onClose={() => setProgramOpen(false)}
            onCreated={load}
          />
        </>
      )}
    </AppShell>
  );
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-gray-50 rounded-lg px-2.5 py-1.5">
      <div className="text-[10px] uppercase tracking-wide text-gray-400">
        {label}
      </div>
      <div className="text-xs font-medium text-gray-800 mt-0.5">{value}</div>
    </div>
  );
}

function CopyBookingLinkButton({ token }: { token: string }) {
  const [copied, setCopied] = useState(false);
  // נבנה ידנית במקום process.env כדי לעבוד גם בdev עם host אחר.
  // encodeURIComponent הגנתי — UUID לא מכיל תווים מיוחדים, אבל אם הפורמט
  // ישתנה בעתיד הגנה זו תמנע URL שבור.
  const url =
    typeof window !== "undefined"
      ? `${window.location.origin}/book/${encodeURIComponent(token)}`
      : "";

  async function copy() {
    if (!url) return;
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      // fallback: בחלק מהדפדפנים clipboard API נחסם — נציג את הקישור
      // עצמו ל-copy ידני (כרגע פשוט נדפיס כשגיאה)
      window.prompt("העתיקי את הקישור:", url);
    }
  }

  return (
    <button
      onClick={copy}
      className="w-full rounded-lg bg-white border border-gray-200 py-2.5 text-sm font-medium flex items-center justify-center gap-1.5"
    >
      <CalendarPlus size={15} aria-hidden />
      {copied ? "הקישור הועתק ✓" : "העתקת קישור לקביעת תור"}
    </button>
  );
}
