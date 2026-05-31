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
  // idempotent guard ל-handleStop — onstop callback של MediaRecorder לא
  // תמיד נורה (iOS Safari edge), אז stopRecording קוראת ל-handleStop
  // ידנית כ-fallback. ה-flag מבטיח ש-handleStop ירוץ בדיוק פעם אחת,
  // גם אם onstop כן רץ במקביל.
  uploadStarted: boolean;
  // abort signal לכל async ב-session — בעיקר ה-upload ל-/transcribe-note.
  // disposeSession() קורא abort() → ה-fetch ב-handleStop נעצר אם
  // ה-modal נסגר תוך כדי upload (אחרת ה-OpenAI call היה מתבצע לחינם).
  abortController: AbortController;
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
      uploadStarted: false,
      abortController: new AbortController(),
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
    // visual feedback מיידי — onstop async; בלי setState כאן הכפתור
    // היה נראה "recording" עוד שבריר שנייה אחרי שהמשתמש לחץ.
    setState("transcribing");

    const recorder = session.recorder;

    // Safari/iOS edge: recorder כבר inactive (timeout פנימי, mic
    // disconnect וכו') — onstop כבר לא יורה. נקרא ל-handleStop ידנית.
    // בלי זה הכפתור תקוע ב"מתמללת…" עם mic חי.
    if (recorder.state === "inactive") {
      void handleStop(session);
      return;
    }

    try {
      recorder.stop();
    } catch {
      // stop() נכשל (InvalidStateError וכו') → onstop בטח לא ירוץ.
      // נקרא ל-handleStop ידנית. ה-finally של handleStop משחרר tracks
      // ומציג feedback.
      void handleStop(session);
      return;
    }

    // Watchdog ל-iOS Safari: onstop לא תמיד נורה גם אחרי stop() מוצלח.
    // אם handleStop לא רץ תוך 2 שניות → נקרא ידני. ה-uploadStarted guard
    // מבטיח ש-handleStop ירוץ exactly once גם אם onstop כן ירוץ אחר כך.
    setTimeout(() => {
      if (
        sessionRef.current === session &&
        !session.cancelled &&
        !session.uploadStarted
      ) {
        void handleStop(session);
      }
    }, 2000);
  }

  // helper יחיד לסיום session — מאחד את ה-cleanup ומוודא שמסלולי
  // "המשתמש עוד שם" תמיד מציגים feedback (success דרך onTranscribed
  // לפני קריאה זו, או error דרך `errorMessage`). שקט מותר *רק* כאשר
  // cancelled/unmounted (isMountedRef.current === false).
  //
  // **לא setState("idle")** בלי מעבר דרך כאן — אחרת קל לשכוח feedback
  // ולקבל יציאה שקטה שנראית כמו no-op.
  function finishSession(
    session: RecordingSession,
    errorMessage: string | null,
  ) {
    if (sessionRef.current === session) sessionRef.current = null;
    if (!isMountedRef.current) return;
    if (errorMessage !== null) setError(errorMessage);
    setState("idle");
  }

  async function handleStop(session: RecordingSession) {
    // Bug 2/3 (מהסבב הקודם): session בוטל ב-unmount/onerror — disposeSession
    // כבר ניתק את ה-stream וקרא cleanup. יוצאים שקט בכוונה.
    if (session.cancelled) return;
    // Idempotent guard: stopRecording קוראת ל-handleStop כ-fallback אם
    // onstop לא יורה (iOS Safari). אם onstop כן יורה אחר כך — נכנס לכאן
    // וייצא מיד. ה-set לפני ה-await מבטיח race-safety.
    if (session.uploadStarted) return;
    session.uploadStarted = true;

    // משחררים את ה-stream מיד, עוד לפני העלאה. אם ה-upload נכשל,
    // ה-mic כבר חופשי.
    session.stream?.getTracks().forEach((t) => t.stop());
    session.stream = null;

    const blob = new Blob(session.chunks, { type: session.mimeType });
    session.chunks = [];

    if (blob.size === 0) {
      // Blob ריק = Safari החזיר chunks ריקים / עצירה מיידית / capture
      // נכשל. בלי הודעה נועה רואה את הכפתור חוזר ל"הקליטי הערה" וחושבת
      // שלא קרה כלום.
      finishSession(session, "ההקלטה היתה ריקה. נסי שוב.");
      return;
    }

    let text: string | null = null;
    try {
      const result = await api.transcribeNote(
        leadId,
        blob,
        session.mimeType,
        session.abortController.signal,
      );
      text = result.text;
    } catch (err) {
      // ה-modal נסגר תוך כדי upload — disposeSession קרא abort(), אז
      // ה-fetch הופסק ו-OpenAI לא קיבל את הקובץ. שקט בכוונה.
      if (session.cancelled || !isMountedRef.current) {
        finishSession(session, null);
        return;
      }
      finishSession(
        session,
        err instanceof ApiError ? err.message : "התמלול נכשל. נסי שוב.",
      );
      return;
    }

    if (session.cancelled || !isMountedRef.current) {
      finishSession(session, null);
      return;
    }

    const trimmed = text?.trim() ?? "";
    if (!trimmed) {
      // 200 OK עם טקסט ריק = OpenAI לא זיהה דיבור. בלי הודעה הכפתור
      // חוזר ל-idle והמשתמשת חושבת שמשהו נשבר בשקט.
      finishSession(session, "התמלול לא זיהה דיבור. נסי לדבר ברור יותר.");
      return;
    }

    onTranscribed(trimmed);
    finishSession(session, null);
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

  // ב-recording: הכפתור הוא "עצור" — לעולם לא חוסמים אותו, גם אם
  // הטופס busy (cursor finding). אחרת submit תוך כדי הקלטה היה משאיר
  // את ה-mic פתוח עד סיום השמירה / unmount, בלי דרך לעצור מה-UI.
  // ב-states אחרים (idle/starting/transcribing) — `disabled` החיצוני חל.
  const buttonDisabled = isRecording
    ? false
    : disabled || isStarting || isTranscribing;

  return (
    <div className="space-y-1.5">
      <button
        type="button"
        onClick={isRecording ? stopRecording : startRecording}
        disabled={buttonDisabled}
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
  // abort כל fetch תלוי-session (בעיקר ה-upload ל-/transcribe-note).
  // אם handleStop כבר ב-await transcribeNote — ה-fetch נעצר ו-OpenAI
  // לא מקבל את הקובץ. לפני התיקון: ה-upload המשיך עד סופו לחינם.
  try {
    session.abortController.abort();
  } catch {
    // ignore
  }
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
