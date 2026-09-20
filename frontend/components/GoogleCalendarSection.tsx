"use client";

import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Calendar, AlertTriangle, Check, Info } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type {
  GoogleCalendarListItem,
  GoogleCalendarStatus,
} from "@/lib/types";

// רק יומן שאפשר לכתוב אליו יכול לשמש כיומן היעד — אחרת יצירת הפגישה
// הייתה נכשלת רק ברגע האמת, מול הלקוח. אותה רשימה נאכפת גם בשרת
// (`_WRITABLE_ROLES` ב-app/services/google_calendar.py).
const WRITABLE_ROLES = new Set(["writer", "owner"]);

// סקציה למסך /settings — מנהלת את החיבור ל-Google Calendar ואת בחירת
// היומנים. 3 מצבי חיבור: לא מחובר / מחובר / חיבור פג תוקף.
export function GoogleCalendarSection() {
  const params = useSearchParams();
  const [status, setStatus] = useState<GoogleCalendarStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<
    "connect" | "disconnect" | "save" | null
  >(null);
  const [error, setError] = useState<string | null>(null);

  // רשימת היומנים של החשבון — נטענת רק כשמחוברים.
  const [calendars, setCalendars] = useState<GoogleCalendarListItem[] | null>(
    null,
  );
  const [calendarsError, setCalendarsError] = useState<string | null>(null);

  // הבחירה שנועה עורכת כרגע. state מקומי כי זה טופס (היא מסמנת כמה
  // תיבות ואז שומרת), אבל הוא **מסונכרן מחדש** מהשרת בכל שינוי של
  // ה-status — אחרת אחרי שמירה או רענון הוא היה נשאר תקוע על הערך
  // הישן וממשיך לשלוח אותו בשמירה הבאה.
  const [targetId, setTargetId] = useState<string>("");
  const [busyIds, setBusyIds] = useState<string[]>([]);

  // קריאה מ-callback (?google=connected או ?google=error&reason=...)
  const callbackResult = params.get("google");
  const callbackReason = params.get("reason");

  const load = useCallback(async () => {
    // מחזיר את ה-status כדי ש-`disconnect`/`save` יוכלו להמשיך ממנו
    // בלי להמתין ל-re-render.
    const next = await api.getGoogleStatus();
    setStatus(next);
    return next;
  }, []);

  useEffect(() => {
    // דגל ביטול: בלי זה, תגובה של בקשה ישנה שמגיעה אחרי unmount (או
    // אחרי בקשה חדשה יותר) הייתה דורסת את ה-state.
    let cancelled = false;
    (async () => {
      try {
        const next = await api.getGoogleStatus();
        if (cancelled) return;
        setStatus(next);
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof ApiError ? err.message : "שגיאה בטעינה");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // טעינת רשימת היומנים — רק כשיש חיבור תקין. auth שבור יחזיר 401
  // ואין טעם לנסות.
  const connectedOk = !!status?.connected && !status.auth_invalid;
  useEffect(() => {
    if (!connectedOk) {
      setCalendars(null);
      return;
    }
    let cancelled = false;
    (async () => {
      setCalendarsError(null);
      try {
        const { items } = await api.listGoogleCalendars();
        if (cancelled) return;
        setCalendars(items);
      } catch (err) {
        if (cancelled) return;
        setCalendarsError(
          err instanceof ApiError ? err.message : "שגיאה בטעינת היומנים",
        );
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [connectedOk]);

  // סנכרון הטופס מהשרת. ה-deps הם הערכים עצמם (לא אובייקט ה-status),
  // כדי שרענון שמחזיר אותם נתונים לא ידרוס עריכה שבאמצע.
  const serverTarget = status?.calendar_id ?? "";
  const serverBusyKey = (status?.busy_calendar_ids ?? []).join(",");
  useEffect(() => {
    setTargetId(serverTarget);
    setBusyIds(serverBusyKey ? serverBusyKey.split(",") : []);
  }, [serverTarget, serverBusyKey]);

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
    if (
      !confirm(
        "לנתק את יומן Google? פגישות חדשות לא יסונכרנו ליומן עד חיבור מחדש.",
      )
    ) {
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

  async function saveCalendars() {
    if (!targetId) return;
    setBusy("save");
    setError(null);
    try {
      // התשובה היא הסטטוס המעודכן — מציבים אותה ישירות, וה-useEffect
      // שלמעלה מסנכרן ממנה את הטופס.
      setStatus(
        await api.setGoogleCalendars({
          target_calendar_id: targetId,
          busy_calendar_ids: busyIds,
        }),
      );
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "שגיאה בשמירת היומנים");
    } finally {
      setBusy(null);
    }
  }

  function toggleBusy(id: string) {
    setBusyIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );
  }

  const dirty =
    targetId !== serverTarget ||
    [...busyIds].sort().join(",") !==
      [...(status?.busy_calendar_ids ?? [])].sort().join(",");

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
                    החיבור פג תוקף. יש להתחבר מחדש כדי שפגישות יסונכרנו.
                  </span>
                </div>
              )}
            </>
          ) : (
            <div className="text-sm text-gray-500 mt-1">
              לא מחובר. חיבור מאפשר סנכרון אוטומטי של פגישות ליומן.
            </div>
          )}
        </div>
      </div>

      {/* בורר היומנים — רק כשהחיבור תקין */}
      {connectedOk && (
        <div className="border-t border-gray-100 pt-3 space-y-3">
          <div className="flex items-start gap-2 text-xs text-gray-500">
            <Info size={13} className="mt-0.5 shrink-0" aria-hidden />
            <span>
              שעה שתפוסה באחד מהיומנים המסומנים לא תוצע ללקוחות. הפגישות
              עצמן ייקבעו ביומן אחד בלבד — זה שנבחר למטה.
            </span>
          </div>

          {calendarsError ? (
            <div className="text-sm text-state-red bg-state-red/10 rounded-lg px-3 py-2">
              {calendarsError}
            </div>
          ) : calendars === null ? (
            <div className="text-sm text-gray-400">טוענת יומנים…</div>
          ) : calendars.length === 0 ? (
            <div className="text-sm text-gray-500">
              לא נמצאו יומנים בחשבון המחובר.
            </div>
          ) : (
            <>
              <div>
                <div className="text-sm font-medium text-gray-700 mb-1.5">
                  יומנים שנחשבים תפוסים
                </div>
                <div className="space-y-1.5">
                  {calendars.map((cal) => {
                    const isTarget = cal.id === targetId;
                    return (
                      <label
                        key={cal.id}
                        className="flex items-center gap-2 text-sm text-gray-800"
                      >
                        <input
                          type="checkbox"
                          // יומן היעד תמיד נחשב תפוס — הפגישות שלנו
                          // נמצאות בו. מוצג מסומן ונעול כדי שלא ייראה
                          // כאילו אפשר לבטל אותו.
                          checked={isTarget || busyIds.includes(cal.id)}
                          disabled={isTarget}
                          onChange={() => toggleBusy(cal.id)}
                          className="rounded border-gray-300"
                        />
                        <span className="truncate">{cal.summary}</span>
                        {isTarget && (
                          <span className="text-xs text-gray-400 shrink-0">
                            (יומן הפגישות)
                          </span>
                        )}
                      </label>
                    );
                  })}
                </div>
              </div>

              <div>
                <label className="block">
                  <div className="text-sm font-medium text-gray-700 mb-1.5">
                    הפגישות ייקבעו ביומן
                  </div>
                  <select
                    value={targetId}
                    onChange={(e) => setTargetId(e.target.value)}
                    className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm bg-white"
                  >
                    {calendars
                      .filter((c) => WRITABLE_ROLES.has(c.access_role))
                      .map((cal) => (
                        <option key={cal.id} value={cal.id}>
                          {cal.summary}
                        </option>
                      ))}
                  </select>
                </label>
                {calendars.every((c) => !WRITABLE_ROLES.has(c.access_role)) && (
                  <div className="text-xs text-state-orange mt-1">
                    אין יומן עם הרשאת כתיבה בחשבון הזה.
                  </div>
                )}
              </div>

              {dirty && (
                <button
                  onClick={saveCalendars}
                  disabled={busy !== null || !targetId}
                  className="w-full rounded-lg bg-gray-900 text-white py-2 text-sm font-medium disabled:opacity-50"
                >
                  {busy === "save" ? "שומרת…" : "שמירת בחירת היומנים"}
                </button>
              )}
            </>
          )}
        </div>
      )}

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
