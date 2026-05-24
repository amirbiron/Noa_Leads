"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Calendar, AlertTriangle, Check } from "lucide-react";
import { api, ApiError } from "@/lib/api";

type Status = {
  connected: boolean;
  google_account_email?: string | null;
  auth_invalid: boolean;
};

// סקציה למסך /settings — מנהלת את החיבור ל-Google Calendar.
// 3 מצבים: לא מחובר / מחובר / חיבור פג תוקף.
export function GoogleCalendarSection() {
  const params = useSearchParams();
  const [status, setStatus] = useState<Status | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<"connect" | "disconnect" | null>(null);
  const [error, setError] = useState<string | null>(null);

  // קריאה מ-callback (?google=connected או ?google=error&reason=...)
  const callbackResult = params.get("google");
  const callbackReason = params.get("reason");

  async function load() {
    try {
      setStatus(await api.getGoogleStatus());
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
      const { auth_url } = await api.startGoogleAuth();
      // הפניה ל-Google — חזרה מה-callback של ה-backend תפנה ל-/settings
      window.location.href = auth_url;
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "שגיאה בהתחלת חיבור");
      setBusy(null);
    }
  }

  async function disconnect() {
    if (!confirm("לנתק את יומן Google? תורים חדשים לא יסונכרנו ליומן עד חיבור מחדש.")) {
      return;
    }
    setBusy("disconnect");
    setError(null);
    try {
      await api.disconnectGoogle();
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
        <Calendar size={20} className="text-gray-400 mt-0.5 shrink-0" aria-hidden />
        <div className="flex-1 min-w-0">
          <div className="font-medium">Google Calendar</div>

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
              {status.auth_invalid && (
                <div className="mt-2 flex items-start gap-2 bg-state-orange/10 border border-state-orange/30 rounded-lg px-3 py-2 text-sm">
                  <AlertTriangle
                    size={14}
                    className="text-state-orange mt-0.5 shrink-0"
                    aria-hidden
                  />
                  <span>
                    החיבור פג תוקף. יש להתחבר מחדש כדי שתורים יסונכרנו.
                  </span>
                </div>
              )}
            </>
          ) : (
            <div className="text-sm text-gray-500 mt-1">
              לא מחובר. חיבור מאפשר סנכרון אוטומטי של תורים לפגישה.
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
              : "התחברות ליומן Google"}
          </button>
        )}
      </div>
    </div>
  );
}
