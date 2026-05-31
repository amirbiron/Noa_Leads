"""בדיקות ל-`services.transcription.transcribe_uploaded` — שכבת
ה-validation + error propagation שמשמשת את ה-endpoint
`POST /leads/{id}/transcribe-note`.

לא משתמש ב-FastAPI TestClient — בקוד הקיים אין dependency-override
infrastructure. ה-endpoint עצמו הוא wrapper דק (קריאת bytes + שליפת
ליד + try/except על errors); הלוגיקה הקריטית (mime/size validation +
error propagation מ-`transcribe_audio`) נמצאת ב-`transcribe_uploaded`,
ועליה אנחנו בודקים פה.

pure: אין DB אמיתי (Lead in-memory), אין OpenAI אמיתי (mock של
`transcribe_audio`).
"""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.exceptions import ValidationError
from app.services import transcription
from app.services.transcription import (
    MAX_AUDIO_BYTES,
    LeadTranscriptionContext,
    TranscriptionError,
    TranscriptionUnavailable,
    transcribe_uploaded,
)


def _mk_ctx(**kwargs) -> LeadTranscriptionContext:
    defaults = dict(
        id=uuid4(),
        full_name="דנה לוי",
        service_category="clinic",
        service_subtype="voice_rehab",
    )
    defaults.update(kwargs)
    return LeadTranscriptionContext(**defaults)


async def test_transcribe_uploaded_returns_text_on_success(monkeypatch):
    """success path — mime תקין + bytes לא ריקים → מחזיר את הטקסט מ-
    `transcribe_audio`."""
    monkeypatch.setattr(
        transcription,
        "transcribe_audio",
        AsyncMock(return_value="שלום, זו הקלטה לבדיקה"),
    )
    text = await transcribe_uploaded(
        b"fake audio bytes", "audio/webm", _mk_ctx()
    )
    assert text == "שלום, זו הקלטה לבדיקה"


async def test_transcribe_uploaded_strips_codec_from_mime(monkeypatch):
    """iOS שולח `audio/mp4;codecs=mp4a.40.2` — צריך להתקבל. החיתוך של
    ה-codec params חיוני, אחרת iOS תמיד יקבל 422."""
    monkeypatch.setattr(
        transcription, "transcribe_audio", AsyncMock(return_value="ok")
    )
    text = await transcribe_uploaded(
        b"bytes", "audio/mp4;codecs=mp4a.40.2", _mk_ctx()
    )
    assert text == "ok"


async def test_transcribe_uploaded_rejects_invalid_mime():
    """mime לא ברשימה (e.g., text/plain) → ValidationError (422 ב-HTTP)."""
    with pytest.raises(ValidationError, match="סוג קובץ אודיו"):
        await transcribe_uploaded(b"bytes", "text/plain", _mk_ctx())


async def test_transcribe_uploaded_rejects_missing_mime():
    """content_type=None (דפדפן לא שלח) → ValidationError."""
    with pytest.raises(ValidationError, match="סוג קובץ אודיו"):
        await transcribe_uploaded(b"bytes", None, _mk_ctx())


async def test_transcribe_uploaded_rejects_empty_bytes():
    """0 bytes (recording של 0 שניות / רשת חתכה) → ValidationError, לא
    קריאת חינם ל-OpenAI."""
    with pytest.raises(ValidationError, match="ריק"):
        await transcribe_uploaded(b"", "audio/webm", _mk_ctx())


async def test_transcribe_uploaded_rejects_oversized_bytes():
    """מעל MAX_AUDIO_BYTES → ValidationError. ה-endpoint עצמו חוסם
    קודם (קריאה עם limit), אבל ה-service מגן defensive."""
    big = b"x" * (MAX_AUDIO_BYTES + 1)
    with pytest.raises(ValidationError, match="גדול"):
        await transcribe_uploaded(big, "audio/webm", _mk_ctx())


async def test_transcribe_uploaded_propagates_unavailable(monkeypatch):
    """OPENAI_API_KEY חסר → TranscriptionUnavailable מ-`transcribe_audio`
    עובר הלאה. ה-endpoint עוטף ל-ServiceUnavailableError (503)."""
    monkeypatch.setattr(
        transcription,
        "transcribe_audio",
        AsyncMock(side_effect=TranscriptionUnavailable("no key")),
    )
    with pytest.raises(TranscriptionUnavailable):
        await transcribe_uploaded(b"bytes", "audio/webm", _mk_ctx())


async def test_transcribe_uploaded_propagates_transcription_error(monkeypatch):
    """כשל OpenAI / רשת → TranscriptionError עובר הלאה. ה-endpoint עוטף
    ל-ExternalServiceError (502)."""
    monkeypatch.setattr(
        transcription,
        "transcribe_audio",
        AsyncMock(side_effect=TranscriptionError("network down")),
    )
    with pytest.raises(TranscriptionError):
        await transcribe_uploaded(b"bytes", "audio/webm", _mk_ctx())
