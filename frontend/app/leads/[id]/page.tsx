"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import {
  ArrowRightLeft,
  FileText,
  Mail,
  MessageCircle,
  Phone,
  Send,
  XCircle,
} from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { CloseLeadModal } from "@/components/CloseLeadModal";
import { DynamicActionButton } from "@/components/DynamicActionButton";
import { QuickActions } from "@/components/QuickActions";
import { SectionHeader } from "@/components/SectionHeader";
import { StateBadge } from "@/components/StateBadge";
import { TemplatePickerSheet } from "@/components/TemplatePickerSheet";
import { Timeline } from "@/components/Timeline";
import { TransferLeadModal } from "@/components/TransferLeadModal";
import { api, ApiError } from "@/lib/api";
import {
  labelCategory,
  labelContact,
  labelPriority,
  labelStatus,
  labelSubtype,
  labelWaiting,
} from "@/lib/hebrew";
import type { Activity, Lead, StateColor } from "@/lib/types";

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
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [templateOpen, setTemplateOpen] = useState(false);
  const [closeOpen, setCloseOpen] = useState(false);
  const [transferOpen, setTransferOpen] = useState(false);
  const [reopening, setReopening] = useState(false);

  async function load() {
    setError(null);
    try {
      const [l, t] = await Promise.all([api.getLead(id), api.getTimeline(id)]);
      setLead(l);
      setActivities(t);
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
                <div className="text-lg font-semibold">{lead.full_name}</div>
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
              <StateBadge color={inferStateColor(lead)} />
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
              {lead.phone && (
                <a
                  href={`https://wa.me/${lead.phone.replace(/\D/g, "")}`}
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

          {/* כפתור "מה עכשיו?" — רק לליד פתוח */}
          {!["WON", "LOST", "ARCHIVED"].includes(lead.status) && (
            <DynamicActionButton lead={lead} onActionDone={load} />
          )}

          {/* כפתורי תבנית + העברה — רק לליד פתוח */}
          {!["WON", "LOST", "ARCHIVED"].includes(lead.status) && (
            <div className="grid grid-cols-2 gap-2">
              <button
                onClick={() => setTemplateOpen(true)}
                className="rounded-lg bg-white border border-gray-200 py-2.5 text-sm font-medium flex items-center justify-center gap-1.5"
              >
                <Send size={15} aria-hidden />
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

          {/* צ'יפים לסיכום שיחה */}
          <div>
            <SectionHeader title="פעולות מהירות" />
            <QuickActions leadId={lead.id} onActionDone={load} />
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
            leadId={lead.id}
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
