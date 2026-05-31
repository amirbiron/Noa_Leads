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
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

from app.config import get_settings
from app.models.lead import Lead
from app.utils.labels import SERVICE_CATEGORY_HE, SERVICE_SUBTYPE_HE

if TYPE_CHECKING:
    from openai import AsyncOpenAI

logger = logging.getLogger("services.transcription")

# gpt-4o-transcribe pricing per OpenAI docs (verify לפני deploy):
# $0.006 per minute = $0.0001 per second. אם המחיר משתנה — לעדכן כאן.
_USD_PER_SECOND = 0.0001

# placeholders של שם שאינם שמות אמיתיים — לא נכניס ל-prompt context.
_NAME_PLACEHOLDERS = {"ללא שם", "ללא"}


class TranscriptionError(Exception):
    """כשל בתמלול. caller יחזיר 502 ויודיע למשתמש 'נסי שוב או הקלידי'."""


class TranscriptionUnavailable(TranscriptionError):
    """OPENAI_API_KEY לא מוגדר. caller יחזיר 503 (פיצ'ר לא זמין)."""


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


def build_transcription_prompt(lead: Lead) -> str:
    """בונה prompt-context ל-gpt-4o-transcribe מנתוני הליד.

    המנוע מקבל שדה `prompt` ייעודי שמסייע לזהות שמות וביטויים שאחרת
    היה מנחש ("דנה" → "דינה", "שיקום קול" כמילים נפרדות). שולחים:
    - שם הליד (אם קיים ולא placeholder)
    - קטגוריה בעברית (label מ-SERVICE_CATEGORY_HE)
    - sub-type בעברית (אם קיים)

    אם כלום לא קיים → מחרוזת ריקה (יישלח prompt=None ל-API).

    **אפס קריאות DB נוספות** — מקבלים את ה-Lead כפי שכבר נטען בכרטיס.
    """
    parts: list[str] = []
    name = (lead.full_name or "").strip()
    if name and name not in _NAME_PLACEHOLDERS:
        parts.append(f"שם הליד: {name}")
    category_he = SERVICE_CATEGORY_HE.get(lead.service_category or "")
    if category_he:
        parts.append(f"קטגוריה: {category_he}")
    subtype_he = SERVICE_SUBTYPE_HE.get(lead.service_subtype or "")
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


async def transcribe_audio(audio_path: Path, lead: Lead) -> str:
    """מתמלל קובץ אודיו של נועה לטקסט עברי, בהקשר של הליד.

    Args:
        audio_path: קובץ זמני שה-caller יצר ויחזיק delete-on-exit.
            אנו לא מוחקים כאן — caller responsibility (NamedTemporaryFile
            ב-endpoint).
        lead: ה-Lead כפי שנטען בכרטיס. משמש לבניית prompt בלבד,
            אפס קריאות DB מצידנו.

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
    prompt = build_transcription_prompt(lead)

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
        lead.id,
        duration_sec if duration_sec is not None else -1,
        cost_usd if cost_usd is not None else 0,
        len(text),
    )

    return text
