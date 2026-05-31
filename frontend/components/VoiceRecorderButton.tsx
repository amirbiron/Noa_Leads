"use client";

import { useEffect, useRef, useState } from "react";
import { Loader2, Mic, Square } from "lucide-react";
import { api, ApiError } from "@/lib/api";

// תיעוד קולי (§13.3) — כפתור הקלטה שמתמלל לטקסט עברי.
//
// State machine:
//   idle → (click) → starting → recording → (click) → transcribing → idle
//                       ↓          ↓                       ↓
//                     error ←─────── ←─────────────────────
//
// "starting" = בזמן `await getUserMedia` (permission prompt). הכפתור
// disabled, מונע double-tap שייצור 2 streams במקביל.
//
// פרטיות: האודיו לא נשלח לשום מקום מעבר ל-endpoint /transcribe-note,
// וה-backend לא שומר אותו (NamedTemporaryFile עם delete=True).
//
// iOS: MediaRecorder תומך מ-Safari 14.5+. בדפדפנים ישנים יותר הכפתור
// מוסתר (lighter touch מאשר להציג כפתור שבור).
//
// Lifecycle (תיקון cursor 8 ממצאים): כל הקלטה היא session עם cancelled
// flag. כל async handler בודק `session.cancelled` ו-`isMountedRef.current`
// לפני side-effect, כך ש-unmount/error/double-tap לא גורמים ל-upload
// מיותר או setState על component unmounted.

interface Props {
  leadId: string;
  onTranscribed: (text: string) => void;
  disabled?: boolean;
}

type RecState = "idle" | "starting" | "recording" | "transcribing";

type RecordingSession = {
  cancelled: boolean;
  stream: MediaStream | null;
  recorder: MediaRecorder | null;
  mimeType: string;
  chunks: Blob[];
};

// MIME types שגם MediaRecorder תומך וגם OpenAI gpt-4o-transcribe מקבל,
// בסדר עדיפויות: webm/opus קטן ואיכותי, mp4 ל-iOS Safari, אחרים fallback.
const MIME_CANDIDATES = [
  "audio/webm;codecs=opus",
  "audio/webm",
  "audio/mp4",
  "audio/ogg",
  "audio/wav",
];

function isMediaRecorderSupported(): boolean {
  return typeof window !== "undefined" && "MediaRecorder" in window;
}

function pickMimeHint(): string {
  for (const m of MIME_CANDIDATES) {
    try {
      if (MediaRecorder.isTypeSupported(m)) return m;
    } catch {
      // בדפדפנים ישנים MediaRecorder.isTypeSupported עלול לזרוק.
    }
  }
  return ""; // ה-MediaRecorder יבחר default
}

export function VoiceRecorderButton({
  leadId,
  onTranscribed,
  disabled,
}: Props) {
  const [state, setState] = useState<RecState>("idle");
  const [error, setError] = useState<string | null>(null);
  const sessionRef = useRef<RecordingSession | null>(null);
  const isMountedRef = useRef(true);

  // cleanup ב-unmount — מסמן את ה-session הנוכחי כ-cancelled, ומשחרר
  // mic/recorder. async handlers שעוד "בטיסה" (onstop, אחרי await
  // transcribeNote) יראו cancelled=true ולא יבצעו side-effects.
  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
      disposeSession(sessionRef.current);
      sessionRef.current = null;
    };
  }, []);

  if (!isMediaRecorderSupported()) {
    // נכון: לא להציג כפתור שבור באייפון ישן. נועה תקליד ידנית.
    return null;
  }

  async function startRecording() {
    // double-tap guard #1: כבר יש session פעיל → מתעלמים.
    if (sessionRef.current && !sessionRef.current.cancelled) return;
    setError(null);
    setState("starting");

    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (err) {
      if (!isMountedRef.current) return;
      const name = (err as { name?: string })?.name;
      setError(
        name === "NotAllowedError" || name === "PermissionDeniedError"
          ? "אין הרשאה למיקרופון. אשרי בדפדפן ונסי שוב."
          : "לא ניתן לגשת למיקרופון.",
      );
      setState("idle");
      return;
    }

    // guard: ה-modal נסגר בזמן permission prompt — משחררים את ה-stream
    // מיד ויוצאים. בלי זה ה-mic נשאר תפוס לנצח (Bug 4).
    if (!isMountedRef.current) {
      stream.getTracks().forEach((t) => t.stop());
      return;
    }

    const mimeHint = pickMimeHint();
    let recorder: MediaRecorder;
    try {
      recorder = new MediaRecorder(
        stream,
        mimeHint ? { mimeType: mimeHint } : undefined,
      );
    } catch {
      stream.getTracks().forEach((t) => t.stop());
      setError("לא ניתן להתחיל הקלטה בדפדפן זה.");
      setState("idle");
      return;
    }

    // MIME אמיתי שה-browser בחר — לא הניחוש שלנו. ב-Safari כש-hint
    // ריק/לא נתמך, recorder.mimeType יחזיר את ה-default האמיתי
    // (לרוב audio/mp4), כך שה-Blob והבקשה מסומנים נכון (Bug 6).
    const session: RecordingSession = {
      cancelled: false,
      stream,
      recorder,
      mimeType: recorder.mimeType || mimeHint || "audio/webm",
      chunks: [],
    };
    sessionRef.current = session;

    recorder.ondataavailable = (e) => {
      if (e.data.size > 0) session.chunks.push(e.data);
    };
    recorder.onstop = () => {
      void handleStop(session);
    };
    recorder.onerror = () => {
      // disposeSession מנתק את onstop לפני stop, כך ש-handleStop לא
      // ירוץ אחרי error (Bug 3).
      disposeSession(session);
      if (sessionRef.current === session) sessionRef.current = null;
      if (isMountedRef.current) {
        setError("שגיאה בהקלטה.");
        setState("idle");
      }
    };

    try {
      recorder.start();
    } catch {
      // Bug 5: start() עלול לזרוק (InvalidStateError / NotSupportedError).
      // בלי disposeSession כאן, ה-stream נשאר פתוח.
      disposeSession(session);
      sessionRef.current = null;
      if (isMountedRef.current) {
        setError("שגיאה בהפעלת ההקלטה.");
        setState("idle");
      }
      return;
    }

    // edge: unmount קרה בדיוק לפני setState. ה-cleanup של ה-useEffect
    // קרא disposeSession על session ש-ref כבר הצביע אליו → cancelled=true.
    if (!isMountedRef.current) {
      disposeSession(session);
      sessionRef.current = null;
      return;
    }

    setState("recording");
  }

  function stopRecording() {
    const session = sessionRef.current;
    if (!session || session.cancelled || !session.recorder) return;
    if (session.recorder.state === "inactive") return;
    // visual feedback מיידי — onstop async; בלי setState כאן הכפתור
    // היה נראה "recording" עוד שבריר שנייה אחרי שהמשתמש לחץ.
    setState("transcribing");
    session.recorder.stop();
  }

  async function handleStop(session: RecordingSession) {
    // Bug 2/3: אם ה-session בוטל (unmount / error) — לא לבנות blob,
    // לא לעלות, לא לעדכן UI. disposeSession כבר ניתק onstop, אבל
    // double-check defensive במקרה ש-onstop רץ לפני שה-handlers נותקו.
    if (session.cancelled) return;

    // משחררים את ה-stream מיד, עוד לפני העלאה. אם ה-upload נכשל,
    // ה-mic כבר חופשי.
    session.stream?.getTracks().forEach((t) => t.stop());
    session.stream = null;

    const blob = new Blob(session.chunks, { type: session.mimeType });
    session.chunks = [];

    if (blob.size === 0) {
      // recording של 0 שניות / חתך — לא נקרא ל-API.
      if (sessionRef.current === session) sessionRef.current = null;
      if (isMountedRef.current) setState("idle");
      return;
    }

    let text: string | null = null;
    try {
      const result = await api.transcribeNote(leadId, blob, session.mimeType);
      text = result.text;
    } catch (err) {
      // ה-modal נסגר תוך כדי upload או error — לא מציגים שגיאה ולא
      // מעדכנים state (Bug 2).
      if (session.cancelled || !isMountedRef.current) {
        if (sessionRef.current === session) sessionRef.current = null;
        return;
      }
      setError(
        err instanceof ApiError ? err.message : "התמלול נכשל. נסי שוב.",
      );
      setState("idle");
      if (sessionRef.current === session) sessionRef.current = null;
      return;
    }

    if (session.cancelled || !isMountedRef.current) {
      if (sessionRef.current === session) sessionRef.current = null;
      return;
    }

    if (text && text.trim()) onTranscribed(text.trim());
    setState("idle");
    if (sessionRef.current === session) sessionRef.current = null;
  }

  const isRecording = state === "recording";
  const isStarting = state === "starting";
  const isTranscribing = state === "transcribing";

  const buttonLabel = isStarting
    ? "מבקשת הרשאה…"
    : isRecording
      ? "עצור הקלטה"
      : isTranscribing
        ? "מתמללת…"
        : "הקליטי הערה";
  const Icon =
    isRecording ? Square : isStarting || isTranscribing ? Loader2 : Mic;

  return (
    <div className="space-y-1.5">
      <button
        type="button"
        onClick={isRecording ? stopRecording : startRecording}
        disabled={disabled || isStarting || isTranscribing}
        className={`inline-flex items-center gap-2 rounded-lg border px-3 py-1.5 text-sm font-medium transition-colors disabled:opacity-50 ${
          isRecording
            ? "border-state-red/40 bg-state-red/10 text-state-red"
            : "border-gray-300 bg-white text-gray-700 hover:bg-gray-50"
        }`}
        aria-label={buttonLabel}
      >
        <Icon
          size={16}
          className={isStarting || isTranscribing ? "animate-spin" : ""}
          aria-hidden
        />
        {buttonLabel}
      </button>
      {error && (
        <div className="text-xs text-state-red" role="alert">
          {error}
        </div>
      )}
    </div>
  );
}

// dispose יחיד — נקרא מ-unmount, onerror, start() failure. שני שלבים:
// (1) ניתוק handlers — מונע trigger של handleStop כשנקרא stop בעקבות
//     הניקוי הזה (אחרת ה-API call של handleStop היה רץ למרות שאנחנו
//     בעיצומה של יציאה).
// (2) cancelled=true + stop + release tracks.
//
// פונקציה module-level (לא בתוך הקומפוננטה) — אין בה state/props,
// וכל הquit handlers (unmount cleanup, onerror, start catch) קוראים לה.
function disposeSession(session: RecordingSession | null) {
  if (!session) return;
  session.cancelled = true;
  const recorder = session.recorder;
  if (recorder) {
    recorder.onstop = null;
    recorder.ondataavailable = null;
    recorder.onerror = null;
    try {
      if (recorder.state !== "inactive") recorder.stop();
    } catch {
      // ignore — recorder כבר במצב לא תקין
    }
  }
  session.stream?.getTracks().forEach((t) => t.stop());
  session.stream = null;
  session.recorder = null;
  session.chunks = [];
}
