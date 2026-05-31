"""תיעוד קולי (§13.3) — תמלול הערות קוליות לכרטיס ליד דרך
OpenAI gpt-4o-transcribe. **ספק AI שני** (Anthropic לכל השאר).

עיקרון פרטיות: קובץ האודיו נמחק מיד אחרי תמלול (לא נשמר ב-DB/R2/FS
קבוע). caller אחראי על temp file lifecycle (NamedTemporaryFile עם
delete=True ב-endpoint).

עיקרון cost: לוג per-call עם משך אודיו + עלות מחושבת, **נפרד ממעקב
ה-Anthropic** ב-`services/ai.py`. כך אפשר לסכם חודשית בנפרד כמה התמלול
עולה (grep "transcription usage:").

מודול נפרד מ-`ai.py` בכוונה: ספק שונה, API שונה (audio, לא chat),
יחידת חיוב שונה (per-minute audio, לא tokens).
"""

import logging
import os
import tempfile
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID

from app.config import get_settings
from app.core.exceptions import ValidationError
from app.utils.labels import SERVICE_CATEGORY_HE, SERVICE_SUBTYPE_HE

if TYPE_CHECKING:
    from openai import AsyncOpenAI

    from app.models.lead import Lead

logger = logging.getLogger("services.transcription")

# gpt-4o-transcribe pricing per OpenAI docs (verify לפני deploy):
# $0.006 per minute = $0.0001 per second. אם המחיר משתנה — לעדכן כאן.
_USD_PER_SECOND = 0.0001

# placeholders של שם שאינם שמות אמיתיים — לא נכניס ל-prompt context.
_NAME_PLACEHOLDERS = {"ללא שם", "ללא"}

# Content-Type allowed list (base; codec params מותרים — אנו מתעלמים
# מהם בהשוואה). מבוסס על MediaRecorder יעדים נפוצים:
# - audio/webm — Chrome/Firefox (opus).
# - audio/mp4 — iOS Safari (critical, נועה באייפון).
# - audio/mpeg — mp3 (פחות נפוץ אבל gpt-4o-transcribe תומך).
# - audio/wav — fallback אוניברסלי.
# - audio/ogg — Firefox לעתים.
ALLOWED_AUDIO_MIME = frozenset(
    {"audio/webm", "audio/mp4", "audio/mpeg", "audio/wav", "audio/ogg"}
)

# 10MB ~= 5 דקות אודיו ב-webm/opus voice. מקסימום הקלטה סבירה לתמלול
# הערה אישית; מעל זה — סביר שמשהו תקול ב-recording (loop).
MAX_AUDIO_BYTES = 10 * 1024 * 1024


class TranscriptionError(Exception):
    """כשל בתמלול. caller יחזיר 502 ויודיע למשתמש 'נסי שוב או הקלידי'."""


class TranscriptionUnavailable(TranscriptionError):
    """OPENAI_API_KEY לא מוגדר. caller יחזיר 503 (פיצ'ר לא זמין)."""


@dataclass(frozen=True)
class LeadTranscriptionContext:
    """Snapshot של שדות Lead שנחוצים לתמלול. נקרא פעם אחת ב-endpoint
    מ-`from_lead()`, מאפשר ל-endpoint לסגור את ה-DB session לפני
    הקריאה הארוכה ל-OpenAI (5-30 שניות) — אחרת ה-connection מ-pool
    נשאר תפוס בלי צורך, ותחת העלאות במקביל ה-pool הקטן (pool_size=5)
    מתיש את עצמו.

    סיבה משנית: detached ORM access אחרי close הוא fragile (DetachedInstance);
    snapshot עוקף את הסיכון. שדות frozen — שלא נטעה ונכתוב חזרה.
    """

    id: UUID
    full_name: str | None
    service_category: str | None
    service_subtype: str | None

    @classmethod
    def from_lead(cls, lead: "Lead") -> "LeadTranscriptionContext":
        return cls(
            id=lead.id,
            full_name=lead.full_name,
            service_category=lead.service_category,
            service_subtype=lead.service_subtype,
        )


@lru_cache(maxsize=1)
def _get_openai_client() -> "AsyncOpenAI":
    """singleton client. lazy import כדי שאם openai לא מותקן/לא מוגדר
    מפתח, יתר ה-app יעבוד נקי."""
    from openai import AsyncOpenAI

    settings = get_settings()
    if not settings.openai_api_key:
        raise TranscriptionUnavailable(
            "OPENAI_API_KEY לא מוגדר — תמלול קולי לא זמין."
        )
    return AsyncOpenAI(api_key=settings.openai_api_key)


def build_transcription_prompt(ctx: LeadTranscriptionContext) -> str:
    """בונה prompt-context ל-gpt-4o-transcribe מנתוני הליד.

    המנוע מקבל שדה `prompt` ייעודי שמסייע לזהות שמות וביטויים שאחרת
    היה מנחש ("דנה" → "דינה", "שיקום קול" כמילים נפרדות). שולחים:
    - שם הליד (אם קיים ולא placeholder)
    - קטגוריה בעברית (label מ-SERVICE_CATEGORY_HE)
    - sub-type בעברית (אם קיים)

    אם כלום לא קיים → מחרוזת ריקה (יישלח prompt=None ל-API).

    **אפס תלות ב-DB session** — `ctx` הוא snapshot של ערכים פרימיטיביים,
    ניתן להעביר אחרי סגירת ה-session.
    """
    parts: list[str] = []
    name = (ctx.full_name or "").strip()
    if name and name not in _NAME_PLACEHOLDERS:
        parts.append(f"שם הליד: {name}")
    category_he = SERVICE_CATEGORY_HE.get(ctx.service_category or "")
    if category_he:
        parts.append(f"קטגוריה: {category_he}")
    subtype_he = SERVICE_SUBTYPE_HE.get(ctx.service_subtype or "")
    if subtype_he:
        parts.append(f"סוג שירות: {subtype_he}")
    return ". ".join(parts)


def _audio_duration_seconds(path: Path) -> float:
    """משך אודיו בשניות, אומדן מגודל-קובץ ו-bitrate ידוע של opus
    voice (~24 kbps). לא מדויק אבל מספיק ל-cost log אינדיקטיבי שאפשר
    לסכם חודשית.

    אלטרנטיבה: הוספת mutagen/ffprobe ל-dependencies לקריאת metadata
    אמיתית. דחוי — ה-cost נמוך מאוד (~$0.002/תמלול) ואומדן מספיק
    להחלטה אופרטיבית.
    """
    size_bytes = path.stat().st_size
    bits = size_bytes * 8
    bits_per_second = 24_000  # opus voice ~24 kbps
    return bits / bits_per_second


async def transcribe_audio(
    audio_path: Path, ctx: LeadTranscriptionContext
) -> str:
    """מתמלל קובץ אודיו של נועה לטקסט עברי, בהקשר של הליד.

    Args:
        audio_path: קובץ זמני שה-caller יצר. אנו לא מוחקים כאן —
            caller responsibility (ב-`transcribe_uploaded`).
        ctx: snapshot של ערכי הליד הנדרשים לבניית prompt. ה-endpoint
            יוצר אותו לפני סגירת ה-DB session, כך שהקריאה הזו לא דורשת
            connection פתוח.

    Returns:
        הטקסט המתומלל (str, trimmed).

    Raises:
        TranscriptionUnavailable: OPENAI_API_KEY לא מוגדר.
        TranscriptionError: כשל ב-API / רשת / response invalid.

    Side effects:
        Cost log per-call ב-INFO level עם duration + cost + model.
        נפרד ממעקב Anthropic (services/ai.py) — grep "transcription usage:"
        מבודד.
    """
    client = _get_openai_client()
    prompt = build_transcription_prompt(ctx)

    try:
        with audio_path.open("rb") as audio_file:
            response = await client.audio.transcriptions.create(
                model="gpt-4o-transcribe",
                file=audio_file,
                language="he",
                prompt=prompt or None,
                response_format="json",
            )
    except Exception as exc:  # OpenAI errors + network + parsing
        logger.warning("transcription failed: %s", exc)
        raise TranscriptionError(str(exc)) from exc

    text = (response.text or "").strip()

    # Cost log — דורש משך. ה-API לא מחזיר duration; אומדים מגודל-קובץ.
    # אם stat נכשל (race delete) — לוג בלי duration אבל בלי קריסה.
    try:
        duration_sec = _audio_duration_seconds(audio_path)
    except Exception:
        duration_sec = None
    cost_usd = duration_sec * _USD_PER_SECOND if duration_sec else None
    logger.info(
        "transcription usage: model=gpt-4o-transcribe lead_id=%s "
        "duration_sec=%.2f cost_usd=%.5f chars=%d",
        ctx.id,
        duration_sec if duration_sec is not None else -1,
        cost_usd if cost_usd is not None else 0,
        len(text),
    )

    return text


def _normalize_mime(content_type: str | None) -> str:
    """Content-Type עשוי לבוא עם codec params — `audio/webm;codecs=opus`.
    חותך את ה-params ומחזיר את ה-base type ב-lowercase."""
    if not content_type:
        return ""
    return content_type.lower().split(";")[0].strip()


async def transcribe_uploaded(
    audio_bytes: bytes,
    content_type: str | None,
    ctx: LeadTranscriptionContext,
) -> str:
    """Validation + temp file + transcribe_audio. הופרד מ-endpoint כדי
    שניתן יהיה לבדוק את הזרימה (validation + error mapping) בלי FastAPI
    TestClient.

    Args:
        audio_bytes: raw bytes של הקובץ. ה-endpoint כבר קרא אותם מ-
            UploadFile (streaming עד גבול MAX_AUDIO_BYTES).
        content_type: ה-MIME מה-request. עשוי להיות None אם הדפדפן
            לא שלח — נחסם כ-422.
        ctx: snapshot של נתוני הליד (אחרי סגירת DB session ב-endpoint).

    Returns:
        טקסט מתומלל (אותו ערך כמו `transcribe_audio`).

    Raises:
        ValidationError: mime לא נתמך / קובץ ריק / גדול מ-MAX_AUDIO_BYTES.
        TranscriptionUnavailable: OPENAI_API_KEY לא מוגדר (propagated).
        TranscriptionError: כשל OpenAI / רשת (propagated).
    """
    mime = _normalize_mime(content_type)
    if mime not in ALLOWED_AUDIO_MIME:
        # לא חושפים את ה-mime המקורי ב-response כדי לא להחזיר input
        # שעלול להיות מתקפה (כלל 3) — רק רשימת מותרים בכלליות.
        raise ValidationError(
            "סוג קובץ אודיו לא נתמך. השתמשי בהקלטה מהדפדפן."
        )
    if not audio_bytes:
        raise ValidationError("הקובץ ריק — לא הוקלט שום דבר.")
    if len(audio_bytes) > MAX_AUDIO_BYTES:
        raise ValidationError("הקובץ גדול מדי. הקלטה מקסימלית ~5 דקות.")

    # suffix תקין לכל types המותרים — חשוב ל-OpenAI שמזהה codec מה-extension.
    suffix = "." + mime.split("/")[-1]
    # Windows compat: `delete=True` ב-NamedTemporaryFile משאיר את ה-handle
    # פתוח, ו-transcribe_audio שפותח את אותו path שוב נכשל ב-Windows
    # (share mode). פתרון נייטרלי: delete=False + סגירת handle + cleanup
    # ב-finally. עובד זהה ב-Linux/Mac/Windows.
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    tmp_path = tmp.name
    try:
        tmp.write(audio_bytes)
        tmp.flush()
        tmp.close()  # release the handle לפני transcribe_audio.open
        return await transcribe_audio(Path(tmp_path), ctx)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass  # missing_ok / race
