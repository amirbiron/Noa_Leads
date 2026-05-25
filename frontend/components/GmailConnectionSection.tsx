"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Mail, AlertTriangle, Check, Tag } from "lucide-react";
import { api, ApiError } from "@/lib/api";

type Status = {
  connected: boolean;
  google_account_email?: string | null;
  history_id?: string | null;
  watch_expiration?: string | null;
  filter_label_name?: string | null;
  auth_invalid: boolean;
};

// סקציה ל-/settings — Phase 3 Stage 17. מקבילה ל-GoogleCalendarSection.
// מציגה גם את שם תווית הסינון (Spec §20.11) כדי שנועה תדע מה ה-classifier
// יסמן ב-Gmail אחרי שיופעל בcommit 4/4.
export function GmailConnectionSection() {
  const params = useSearchParams();
  const [status, setStatus] = useState<Status | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<"connect" | "disconnect" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const callbackResult = params.get("gmail");
  const callbackReason = params.get("reason");

  async function load() {
    try {
      setStatus(await api.getGmailStatus());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "שגיאה בטעינה");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function connect() {
    setBusy("connect");
    setError(null);
    try {
      const { auth_url } = await api.startGmailAuth();
      window.location.href = auth_url;
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "שגיאה בהתחלת חיבור");
      setBusy(null);
    }
  }

  async function disconnect() {
    if (!confirm("לנתק את Gmail? מיילים חדשים לא יהפכו ללידים אוטומטית עד חיבור מחדש.")) {
      return;
    }
    setBusy("disconnect");
    setError(null);
    try {
      await api.disconnectGmail();
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "שגיאה בניתוק");
    } finally {
      setBusy(null);
    }
  }

  if (loading) {
    return (
      <div className="bg-white rounded-xl border border-gray-200 p-4 text-sm text-gray-400">
        טוען…
      </div>
    );
  }

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4 space-y-3">
      <div className="flex items-start gap-3">
        <Mail size={20} className="text-gray-400 mt-0.5 shrink-0" aria-hidden />
        <div className="flex-1 min-w-0">
          <div className="font-medium">Gmail</div>

          {/* הודעה מה-OAuth callback */}
          {callbackResult === "connected" && (
            <div className="text-xs text-state-green mt-1 flex items-center gap-1">
              <Check size={12} aria-hidden /> חובר בהצלחה
            </div>
          )}
          {callbackResult === "error" && (
            <div className="text-xs text-state-red mt-1">
              החיבור נכשל ({callbackReason || "שגיאה לא ידועה"})
            </div>
          )}

          {/* מצב חיבור */}
          {status?.connected ? (
            <>
              <div className="text-sm text-gray-600 mt-1">
                מחובר ל-<span dir="ltr">{status.google_account_email}</span>
              </div>
              {status.filter_label_name && (
                <div className="text-xs text-gray-500 mt-1 flex items-center gap-1">
                  <Tag size={12} aria-hidden />
                  <span>
                    תווית סינון: <strong>{status.filter_label_name}</strong>
                  </span>
                </div>
              )}
              {status.auth_invalid && (
                <div className="mt-2 flex items-start gap-2 bg-state-orange/10 border border-state-orange/30 rounded-lg px-3 py-2 text-sm">
                  <AlertTriangle
                    size={14}
                    className="text-state-orange mt-0.5 shrink-0"
                    aria-hidden
                  />
                  <span>
                    החיבור פג תוקף. יש להתחבר מחדש כדי שמיילים יסונכרנו.
                  </span>
                </div>
              )}
            </>
          ) : (
            <div className="text-sm text-gray-500 mt-1">
              לא מחובר. חיבור מאפשר ש-AI יקלוט אוטומטית פניות שמגיעות במייל.
            </div>
          )}
        </div>
      </div>

      {error && (
        <div className="text-sm text-state-red bg-state-red/10 rounded-lg px-3 py-2">
          {error}
        </div>
      )}

      <div className="flex gap-2">
        {status?.connected && !status.auth_invalid ? (
          <button
            onClick={disconnect}
            disabled={busy !== null}
            className="rounded-lg bg-white border border-gray-300 text-gray-700 py-2 px-3 text-sm disabled:opacity-50"
          >
            {busy === "disconnect" ? "מנתקת…" : "ניתוק"}
          </button>
        ) : (
          <button
            onClick={connect}
            disabled={busy !== null}
            className="rounded-lg bg-gray-900 text-white py-2 px-3 text-sm font-medium disabled:opacity-50"
          >
            {busy === "connect"
              ? "פותחת…"
              : status?.auth_invalid
              ? "התחברות מחדש"
              : "התחברות ל-Gmail"}
          </button>
        )}
      </div>
    </div>
  );
}
