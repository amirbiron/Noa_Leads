"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { AUTH_CHANGED_EVENT, isLoggedIn } from "@/lib/auth";
import {
  CREATION_PENDING_DEFER_MS,
  CREATION_PENDING_MAX_MS,
  LEAD_CREATION_CANCELED_EVENT,
  LEAD_CREATION_PENDING_EVENT,
  LEAD_MANUALLY_CREATED_EVENT,
  MANUALLY_CREATED_TTL_MS,
  type LeadManuallyCreatedDetail,
} from "@/lib/leadEvents";
import type { DashboardPollResponse, LeadCard } from "@/lib/types";

// 60 שניות. לפי spec של אדיר: עד 15 דק' latency מקובל; 60s נותן UX
// כמעט-realtime עם עומס זניח (1440 requests/יום למשתמש פעיל).
const POLL_INTERVAL_MS = 60_000;

// 4.5s עקבי עם ה-toast של QuickActions.tsx — לא להפריע לקריאה.
const TOAST_AUTO_DISMISS_MS = 4_500;

interface PollState {
  // עולה ב-1 בכל poll עם delta non-empty. עמודים משתמשים בו כdep
  // ב-useEffect כדי לטרגר refetch.
  pollVersion: number;
  // ה-IDs של לידים שהיו ב-delta האחרון. דף ליד פרטני בודק את
  // ה-id שלו ב-Set הזה כדי להחליט אם לרענן (אחרת מטריד גלילה).
  recentlyUpdatedLeadIds: Set<string>;
  // last-wins: poll חדש דורס toast קודם. אין צבירה.
  toastMessage: string | null;
}

interface PollControl {
  dismissToast: () => void;
}

export function useDashboardPoll(): PollState & PollControl {
  const [state, setState] = useState<PollState>({
    pollVersion: 0,
    recentlyUpdatedLeadIds: new Set(),
    toastMessage: null,
  });

  // reactive loggedIn — Provider עולה ב-layout root, *לפני* login,
  // ב-/login `loggedIn=false`. אחרי setTokens, event "noa:auth-changed"
  // יורה והhook יעדכן → useEffect הפולינג ירוץ שוב ויפעיל interval.
  // בלי זה, ה-polling לא היה מתחיל אחרי login עד לreload מלא
  // (תיקון bugbot).
  const [loggedIn, setLoggedIn] = useState<boolean>(() =>
    typeof window !== "undefined" ? isLoggedIn() : false,
  );
  useEffect(() => {
    function recheck() {
      setLoggedIn(isLoggedIn());
    }
    window.addEventListener(AUTH_CHANGED_EVENT, recheck);
    // storage event — sync בין tabs (logout בtab אחר → polling
    // יעצור גם בtab הזה).
    window.addEventListener("storage", recheck);
    return () => {
      window.removeEventListener(AUTH_CHANGED_EVENT, recheck);
      window.removeEventListener("storage", recheck);
    };
  }, []);

  // ref ולא state — שינוי לא דורש re-render, רק קריאה ב-poll הבא.
  // התחלה: ה-now של ה-mount. ה-poll הראשון יחזיר 0 שינויים כי
  // הליד הטרי ביותר נוצר לפני mount.
  const sinceRef = useRef<string>(new Date().toISOString());
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // לידים שנועה יצרה ידנית באמצעות NewLeadModal — מסוננים מ-toast/
  // recentlyUpdatedLeadIds (אין טעם להתריע לה על מה שהיא עצמה יצרה
  // רגע קודם). Map id → expiresAt (ms epoch). cleanup ב-doPoll
  // לפני סינון, כדי שלא ידלוף לזמן בלתי-מוגבל.
  const manuallyCreatedRef = useRef<Map<string, number>>(new Map());

  // "creation in flight" — דלוק בין `lead-creation-pending` ל-
  // `lead-manually-created`/`lead-creation-canceled`. מטפל ב-race:
  // poll שהיה in-flight כש-נועה לחצה submit יכול לחזור עם הליד החדש
  // *לפני* שה-POST resolve והID נכנס ל-Map. בזמן הזה, doPoll דוחה
  // את ה-toast ב-CREATION_PENDING_DEFER_MS — מספיק זמן ל-POST להחזיר
  // ול-event לרוץ → ה-defer בודק שוב את ה-Map שכבר עודכן.
  const creationPendingRef = useRef(false);
  // safety timeout — אם events לא נורים (browser closed mid-POST, JS
  // error), ה-flag לא תקוע לנצח ומעצור toasts אמיתיים.
  const creationPendingTimeoutRef = useRef<
    ReturnType<typeof setTimeout> | null
  >(null);

  useEffect(() => {
    function clearPendingTimeout() {
      if (creationPendingTimeoutRef.current) {
        clearTimeout(creationPendingTimeoutRef.current);
        creationPendingTimeoutRef.current = null;
      }
    }
    function settlePending() {
      creationPendingRef.current = false;
      clearPendingTimeout();
    }
    function onPending() {
      creationPendingRef.current = true;
      clearPendingTimeout();
      creationPendingTimeoutRef.current = setTimeout(
        settlePending,
        CREATION_PENDING_MAX_MS,
      );
    }
    function onManuallyCreated(e: Event) {
      const detail = (e as CustomEvent<LeadManuallyCreatedDetail>).detail;
      if (detail?.id) {
        manuallyCreatedRef.current.set(
          detail.id,
          Date.now() + MANUALLY_CREATED_TTL_MS,
        );
      }
      // ID נכנס ל-Map → ה-pending mode לא נחוץ יותר. ה-Map עצמו ימשיך
      // לסנן את ה-ID הזה ב-poll-ים הבאים.
      settlePending();
    }
    window.addEventListener(LEAD_CREATION_PENDING_EVENT, onPending);
    window.addEventListener(LEAD_CREATION_CANCELED_EVENT, settlePending);
    window.addEventListener(LEAD_MANUALLY_CREATED_EVENT, onManuallyCreated);
    return () => {
      window.removeEventListener(LEAD_CREATION_PENDING_EVENT, onPending);
      window.removeEventListener(LEAD_CREATION_CANCELED_EVENT, settlePending);
      window.removeEventListener(
        LEAD_MANUALLY_CREATED_EVENT,
        onManuallyCreated,
      );
      clearPendingTimeout();
    };
  }, []);

  const doPoll = useCallback(async () => {
    if (!isLoggedIn()) return;
    if (typeof document !== "undefined" && document.hidden) return;
    try {
      const resp: DashboardPollResponse = await api.pollDashboard(
        sinceRef.current,
      );
      // server_time = anchor ל-poll הבא (מבדיל clock skew של ה-client).
      sinceRef.current = resp.server_time;

      // cleanup של IDs פגי-תוקף לפני סינון — מונע דליפת זיכרון לאורך
      // sessions ארוכים. ה-TTL (5 דק') מספיק לפסות poll שהיה in-flight
      // בזמן ה-create.
      const now = Date.now();
      for (const [id, expiresAt] of manuallyCreatedRef.current) {
        if (expiresAt <= now) manuallyCreatedRef.current.delete(id);
      }

      // publish — מפריד בין שני signals:
      //   * `pollVersion` bump = "רשימות, רעננו": תקף גם ללידים שנועה
      //     יצרה ידנית (היא בדף הליד שלהם, אבל /today /leads /pending
      //     לא מודעים — מציגים רשימה stale עד poll חיצוני).
      //   * `toastMessage` + `recentlyUpdatedLeadIds` = "מה להציג":
      //     מסונן (אין טעם להראות "ליד חדש: X" על מה שנועה הקלידה,
      //     ואין טעם לבקש מדף הליד שלה לעשות load מחדש — הוא fresh).
      //
      // ה-defer (creation-pending) רק קובע מתי publish רץ; הסמנטיקה
      // של "filtered מול raw" שווה בשני המסלולים.
      const publish = () => {
        // raw delta — לבדיקה האם בכלל קרה משהו ב-server.
        const rawDelta =
          resp.new_leads.length + resp.leads_with_inbound_replies.length;
        if (rawDelta === 0) return; // poll ריק לחלוטין — אין מה לעשות.

        // filtered — לידים שנועה לא יצרה. רק אלה מצדיקים toast ו-
        // refetch בדף ליד פתוח.
        const finalNewLeads = resp.new_leads.filter(
          (l) => !manuallyCreatedRef.current.has(l.id),
        );
        const filteredDelta =
          finalNewLeads.length + resp.leads_with_inbound_replies.length;

        const ids = new Set<string>([
          ...finalNewLeads.map((l: LeadCard) => l.id),
          ...resp.leads_with_inbound_replies.map((l: LeadCard) => l.id),
        ]);

        // toast רק אם יש משהו ש*נראה* למשתמש. אם הכל לידים ידניים →
        // null = אין toast חדש. שומרים על prev.toastMessage כדי לא
        // לבטל toast קיים שעוד בתוקף (auto-dismiss timer ינקה אותו).
        const message =
          filteredDelta > 0
            ? buildToast({ ...resp, new_leads: finalNewLeads })
            : null;

        setState((prev) => ({
          // bump תמיד כש-rawDelta > 0 — רשימות צריכות לדעת על השינוי.
          pollVersion: prev.pollVersion + 1,
          recentlyUpdatedLeadIds: ids,
          toastMessage: message ?? prev.toastMessage,
        }));
      };

      if (creationPendingRef.current) {
        // יצירת ליד ידנית in-flight: ה-POST של createLead עדיין לא
        // החזיר → ה-ID של הליד החדש עוד לא ב-Map. דוחים את הtoast
        // ב-~2s כדי לתת לאירוע ה-`lead-manually-created` להגיע ולהוסיף
        // את ה-ID. אחרי ה-defer `publish` מסנן שוב את ה-Map העדכני.
        // בלי זה: poll שחזר ראשון היה מציג "ליד חדש: X" על הליד שנועה
        // עצמה יצרה רגע קודם.
        setTimeout(publish, CREATION_PENDING_DEFER_MS);
        return;
      }
      publish();
    } catch (err) {
      // 401 → fetcher כבר ניווט ל-/login. שאר שגיאות (network, 500) —
      // לא קריטי, ה-poll הבא ינסה שוב. log רק ל-dev visibility.
      if (!(err instanceof ApiError && err.status === 401)) {
        // eslint-disable-next-line no-console
        console.warn("Dashboard poll failed:", err);
      }
    }
  }, []);

  useEffect(() => {
    if (!loggedIn) return;

    // login רענן — reset ה-since ל-now כדי לא למשוך היסטוריה שקדמה
    // ל-login (היה גורם ל-toast/refresh על לידים ישנים מהשעה האחרונה).
    sinceRef.current = new Date().toISOString();

    // poll מיידי ב-mount/לאחר login — לא לחכות 60s לסיבוב ראשון.
    void doPoll();

    function startInterval() {
      if (intervalRef.current) return;
      intervalRef.current = setInterval(() => void doPoll(), POLL_INTERVAL_MS);
    }
    function stopInterval() {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    }

    startInterval();

    function onVisibility() {
      if (document.hidden) {
        // tab hidden — לעצור פעולת רקע. interval/timer ב-Chrome יחנק
        // ל-1 דקה ממילא, אבל ביטול מפורש = ברור יותר ו-mobile friendly.
        stopInterval();
      } else {
        // tab visible — poll מיידי + restart interval. נועה רוצה
        // עדכון מהיר כשהיא חוזרת לטאב.
        void doPoll();
        startInterval();
      }
    }
    document.addEventListener("visibilitychange", onVisibility);

    return () => {
      stopInterval();
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [doPoll, loggedIn]);

  // auto-dismiss toast אחרי N שניות.
  useEffect(() => {
    if (!state.toastMessage) return;
    const t = setTimeout(
      () => setState((s) => ({ ...s, toastMessage: null })),
      TOAST_AUTO_DISMISS_MS,
    );
    return () => clearTimeout(t);
  }, [state.toastMessage]);

  const dismissToast = useCallback(
    () => setState((s) => ({ ...s, toastMessage: null })),
    [],
  );

  return { ...state, dismissToast };
}

function buildToast(resp: DashboardPollResponse): string {
  const n = resp.new_leads.length;
  const r = resp.leads_with_inbound_replies.length;
  // מיקוד על האירוע הבולט. ליד חדש יחיד = השם (יותר אישי).
  // כמה לידים = ספירה. אם רק תגובות — שם או ספירה.
  if (n === 1) return `ליד חדש: ${resp.new_leads[0].full_name}`;
  if (n > 1) return `${n} לידים חדשים`;
  if (r === 1) {
    return `תגובה חדשה מ-${resp.leads_with_inbound_replies[0].full_name}`;
  }
  return `${r} תגובות חדשות`;
}
