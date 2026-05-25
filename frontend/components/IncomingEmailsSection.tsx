"use client";

import { useState } from "react";
import { ChevronDown, ChevronUp, Mail } from "lucide-react";
import { formatDateTimeHebrew, formatRelativeHebrew } from "@/lib/hebrew";
import type { EmailMessage } from "@/lib/types";

// סקציה בכרטיס ליד שמציגה מיילים נכנסים שקושרו לליד (Spec §20.10).
// כל מייל = card עם subject + from + relative time + preview ~120 תווים;
// קליק על chevron מרחיב inline להציג cleaned_text מלא.
//
// נטען מ-parent (lead page) דרך Promise.all, לא מתחזק state משלו.
// המקובץ מציג cleaned_text בלבד (טקסט בטוח, לא HTML). raw_html לא נחשף
// מה-backend כי אין sanitizer מותקן — ראה Future ב-plan.
//
// אם אין מיילים — לא רנדור (לא רעש לליד שנכנס מטופס).

const PREVIEW_LEN = 120;

function buildPreview(cleaned: string | null): string {
  if (!cleaned) return "";
  // ניקוי whitespace ל-preview שטוח. cleaned_text כבר עבר ניקוי HTML
  // וקיצור, אבל יכול לכלול שורות ריקות שמכוערות ב-preview.
  const normalized = cleaned.replace(/\s+/g, " ").trim();
  return normalized.length > PREVIEW_LEN
    ? normalized.slice(0, PREVIEW_LEN) + "…"
    : normalized;
}

export function IncomingEmailsSection({ emails }: { emails: EmailMessage[] }) {
  const [expandedId, setExpandedId] = useState<string | null>(null);

  if (emails.length === 0) return null;

  return (
    <ol className="space-y-2">
      {emails.map((email) => {
        const isExpanded = expandedId === email.id;
        const preview = buildPreview(email.cleaned_text);
        const timeStamp = email.received_at ?? email.created_at;

        return (
          <li
            key={email.id}
            className="bg-white rounded-lg border border-gray-200"
          >
            <button
              type="button"
              onClick={() => setExpandedId(isExpanded ? null : email.id)}
              className="w-full text-start px-3 py-2.5 active:bg-gray-50"
              aria-expanded={isExpanded}
            >
              <div className="flex items-baseline justify-between gap-2">
                <div className="flex items-center gap-2 min-w-0">
                  <Mail
                    size={14}
                    className="text-gray-400 shrink-0"
                    aria-hidden
                  />
                  <span className="text-sm font-medium truncate">
                    {email.subject || "ללא נושא"}
                  </span>
                </div>
                <div className="flex items-center gap-1 shrink-0">
                  <span
                    className="text-xs text-gray-400"
                    title={formatDateTimeHebrew(timeStamp)}
                  >
                    {formatRelativeHebrew(timeStamp)}
                  </span>
                  {isExpanded ? (
                    <ChevronUp size={14} className="text-gray-400" aria-hidden />
                  ) : (
                    <ChevronDown
                      size={14}
                      className="text-gray-400"
                      aria-hidden
                    />
                  )}
                </div>
              </div>
              {email.from_address && (
                <div
                  className="mt-1 text-xs text-gray-500 truncate"
                  dir="ltr"
                  style={{ textAlign: "start" }}
                >
                  {email.from_address}
                </div>
              )}
              {!isExpanded && preview && (
                <div className="mt-1 text-sm text-gray-600 line-clamp-2">
                  {preview}
                </div>
              )}
            </button>

            {isExpanded && (
              <div className="border-t border-gray-100 px-3 py-2.5">
                {email.cleaned_text ? (
                  <pre className="text-sm text-gray-700 whitespace-pre-wrap font-sans">
                    {email.cleaned_text}
                  </pre>
                ) : (
                  <div className="text-sm text-gray-400 italic">
                    אין תוכן זמין למייל זה.
                  </div>
                )}
              </div>
            )}
          </li>
        );
      })}
    </ol>
  );
}
