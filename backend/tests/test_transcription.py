"""בדיקות יחידה ל-`services/transcription`.

- `build_transcription_prompt`: שם + קטגוריה + subtype מועברים נכון,
  edge cases (אין שם / placeholder / אין קטגוריה).
- `transcribe_audio`: fallback בכשל API (raise TranscriptionError ולא
  קריסה), success path עם strip של טקסט.

pure: אין DB, אין תלות במפתח OPENAI_API_KEY אמיתי (mock-ים את ה-client).
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.constants import LeadStatus, SourceChannel
from app.models.lead import Lead
from app.services import transcription


def _mk_lead(**kwargs) -> Lead:
    """Builder ל-Lead in-memory (לא DB). מספיק לבדיקות יחידה של helpers
    שלא נוגעים ב-DB."""
    defaults = dict(
        full_name="דנה לוי",
        source_channel=SourceChannel.MANUAL.value,
        status=LeadStatus.NEW.value,
        service_category="clinic",
        service_subtype="voice_rehab",
    )
    defaults.update(kwargs)
    return Lead(**defaults)


# ===== build_transcription_prompt — 4 תרחישים =====


def test_build_prompt_with_name_and_category_and_subtype():
    """המקרה השלם: כל השדות נכנסים ל-prompt בעברית."""
    prompt = transcription.build_transcription_prompt(_mk_lead())
    assert "דנה לוי" in prompt
    assert "קליניקה" in prompt  # SERVICE_CATEGORY_HE['clinic']
    assert "שיקום קול" in prompt  # SERVICE_SUBTYPE_HE['voice_rehab']


def test_build_prompt_without_name_only_category():
    """ליד ללא שם — רק קטגוריה ב-prompt."""
    prompt = transcription.build_transcription_prompt(
        _mk_lead(full_name="", service_subtype=None)
    )
    assert "קליניקה" in prompt
    assert "שם הליד" not in prompt


def test_build_prompt_without_category_only_name():
    """ליד ללא קטגוריה — רק שם ב-prompt."""
    prompt = transcription.build_transcription_prompt(
        _mk_lead(service_category=None, service_subtype=None)
    )
    assert "דנה לוי" in prompt
    assert "קטגוריה" not in prompt
    assert "סוג שירות" not in prompt


def test_build_prompt_placeholder_name_treated_as_missing():
    """שמות placeholder ('ללא שם', 'ללא') לא נכנסים ל-prompt — הם
    סמנטית 'אין שם'."""
    prompt_no_name = transcription.build_transcription_prompt(
        _mk_lead(full_name="ללא שם")
    )
    assert "ללא שם" not in prompt_no_name
    assert "שם הליד" not in prompt_no_name

    prompt_lela = transcription.build_transcription_prompt(
        _mk_lead(full_name="ללא")
    )
    assert "ללא" not in prompt_lela.split(" קטגוריה")[0]  # ב-prefix


def test_build_prompt_empty_when_nothing_known():
    """אין שום שדה משמעותי → מחרוזת ריקה (תישלח prompt=None ל-API)."""
    prompt = transcription.build_transcription_prompt(
        _mk_lead(
            full_name="",
            service_category=None,
            service_subtype=None,
        )
    )
    assert prompt == ""


# ===== transcribe_audio — fallback + success =====


async def test_transcribe_audio_raises_on_api_failure(tmp_path, monkeypatch):
    """כשל ב-OpenAI API → TranscriptionError. caller אחראי על UX
    גרציוזי ('נסי שוב או הקלידי'). השדה personal_note לא מושפע."""
    audio = tmp_path / "test.webm"
    audio.write_bytes(b"fake audio bytes")

    mock_client = MagicMock()
    mock_client.audio.transcriptions.create = AsyncMock(
        side_effect=RuntimeError("network failed")
    )
    monkeypatch.setattr(
        transcription, "_get_openai_client", lambda: mock_client
    )

    with pytest.raises(transcription.TranscriptionError, match="network"):
        await transcription.transcribe_audio(audio, _mk_lead())


async def test_transcribe_audio_returns_stripped_text_on_success(
    tmp_path, monkeypatch
):
    """success path: text של ה-response מוחזר אחרי strip של רווחים."""
    audio = tmp_path / "test.webm"
    audio.write_bytes(b"x" * 24_000)  # ~1 שנייה ב-opus voice (~24 kbps)

    mock_response = MagicMock()
    mock_response.text = "  שלום, זו הקלטה לבדיקה  "
    mock_client = MagicMock()
    mock_client.audio.transcriptions.create = AsyncMock(
        return_value=mock_response
    )
    monkeypatch.setattr(
        transcription, "_get_openai_client", lambda: mock_client
    )

    result = await transcription.transcribe_audio(audio, _mk_lead())
    assert result == "שלום, זו הקלטה לבדיקה"

    # מאמת שה-prompt הדינמי הועבר ל-API (שם + קטגוריה).
    call_kwargs = mock_client.audio.transcriptions.create.call_args.kwargs
    assert "דנה לוי" in call_kwargs["prompt"]
    assert "קליניקה" in call_kwargs["prompt"]
    assert call_kwargs["language"] == "he"
    assert call_kwargs["model"] == "gpt-4o-transcribe"
