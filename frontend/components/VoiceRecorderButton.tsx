"use client";

import { useEffect, useRef, useState } from "react";
import { Loader2, Mic, Square } from "lucide-react";
import { api, ApiError } from "@/lib/api";

// תיעוד קולי (§13.3) — כפתור הקלטה שמתמלל לטקסט עברי.
//
// State machine:
//   idle → (click) → recording → (click) → transcribing → idle (text)
//                                       ↓
//                                    error → idle
//
// אין caller-side state — הקומפוננטה אוטרכית. callback `onTranscribed`
// מקבל את הטקסט המתומלל; ה-parent אחראי לצרף ל-textarea / state אחר.
//
// פרטיות: האודיו לא נשלח לשום מקום מעבר ל-endpoint /transcribe-note,
// וה-backend לא שומר אותו (NamedTemporaryFile עם delete=True).
//
// iOS: MediaRecorder תומך מ-Safari 14.5+. בדפדפנים ישנים יותר הכפתור
// מוסתר (lighter touch מאשר להציג כפתור שבור).

interface Props {
  leadId: string;
  onTranscribed: (text: string) => void;
  disabled?: boolean;
}

type RecState = "idle" | "recording" | "transcribing";

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

function pickMimeType(): string {
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
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const mimeRef = useRef<string>("");

  // cleanup ב-unmount — אם המשתמש סגר את המודאל באמצע הקלטה, המיקרופון
  // חייב להשתחרר (אחרת הdot הירוק נשאר ובדפדפן ה-state עלום).
  useEffect(() => {
    return () => {
      if (recorderRef.current && recorderRef.current.state !== "inactive") {
        try {
          recorderRef.current.stop();
        } catch {
          // ignore
        }
      }
      streamRef.current?.getTracks().forEach((t) => t.stop());
    };
  }, []);

  if (!isMediaRecorderSupported()) {
    // נכון: לא להציג כפתור שבור באייפון ישן. נועה תקליד ידנית.
    return null;
  }

  async function startRecording() {
    setError(null);
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (err) {
      const name = (err as { name?: string })?.name;
      setError(
        name === "NotAllowedError" || name === "PermissionDeniedError"
          ? "אין הרשאה למיקרופון. אשרי בדפדפן ונסי שוב."
          : "לא ניתן לגשת למיקרופון.",
      );
      return;
    }
    streamRef.current = stream;
    const mime = pickMimeType();
    mimeRef.current = mime;
    let recorder: MediaRecorder;
    try {
      recorder = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
    } catch {
      stream.getTracks().forEach((t) => t.stop());
      setError("לא ניתן להתחיל הקלטה בדפדפן זה.");
      return;
    }
    chunksRef.current = [];
    recorder.ondataavailable = (e) => {
      if (e.data.size > 0) chunksRef.current.push(e.data);
    };
    recorder.onstop = handleStop;
    recorder.onerror = () => {
      setError("שגיאה בהקלטה.");
      cleanupStream();
      setState("idle");
    };
    recorderRef.current = recorder;
    recorder.start();
    setState("recording");
  }

  function stopRecording() {
    const recorder = recorderRef.current;
    if (!recorder || recorder.state === "inactive") return;
    // visual feedback מיידי — onstop async; בלי setState כאן הכפתור
    // היה נראה "recording" עוד שבריר שנייה אחרי שהמשתמש לחץ.
    setState("transcribing");
    recorder.stop();
  }

  function cleanupStream() {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    recorderRef.current = null;
  }

  async function handleStop() {
    const blob = new Blob(chunksRef.current, {
      type: mimeRef.current || "audio/webm",
    });
    cleanupStream();
    chunksRef.current = [];

    if (blob.size === 0) {
      // recording של 0 שניות / חתך — לא נקרא ל-API.
      setState("idle");
      return;
    }

    try {
      const { text } = await api.transcribeNote(
        leadId,
        blob,
        mimeRef.current || "audio/webm",
      );
      if (text.trim()) onTranscribed(text.trim());
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "התמלול נכשל. נסי שוב.",
      );
    } finally {
      setState("idle");
    }
  }

  const isRecording = state === "recording";
  const isTranscribing = state === "transcribing";

  const buttonLabel = isRecording
    ? "עצור הקלטה"
    : isTranscribing
      ? "מתמללת…"
      : "הקליטי הערה";
  const Icon = isRecording ? Square : isTranscribing ? Loader2 : Mic;

  return (
    <div className="space-y-1.5">
      <button
        type="button"
        onClick={isRecording ? stopRecording : startRecording}
        disabled={disabled || isTranscribing}
        className={`inline-flex items-center gap-2 rounded-lg border px-3 py-1.5 text-sm font-medium transition-colors disabled:opacity-50 ${
          isRecording
            ? "border-state-red/40 bg-state-red/10 text-state-red"
            : "border-gray-300 bg-white text-gray-700 hover:bg-gray-50"
        }`}
        aria-label={buttonLabel}
      >
        <Icon
          size={16}
          className={isTranscribing ? "animate-spin" : ""}
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
