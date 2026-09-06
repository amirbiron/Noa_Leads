"""
תמלול קולי גנרי — לטופס יצירת ליד חדש (NewLeadModal).

POST `/transcribe-note` (בלי lead_id): נועה מקליטה הערה בזמן מילוי הטופס,
לפני שהליד נוצר. הקונטקסט (שם, קטגוריה, sub-type) נשלח כ-form fields ממה
שכבר הוקלד — משפר את דיוק התמלול בעברית (gpt-4o-transcribe מקבל prompt
שמרמז שמות ומונחים נפוצים). אם לא נשלח קונטקסט — התמלול עדיין עובד, רק
פחות מדויק.

נפרד מ-`/leads/{lead_id}/transcribe-note` (ב-routes/leads.py) כי הוא דורש
ליד קיים. אותה ולידציה (mime/size), אותה התנהגות שגיאות, אותה פרטיות.
"""

from fastapi import APIRouter, File, Form, UploadFile

from app.api.deps import CurrentUser, DbSession
from app.core.exceptions import (
    ExternalServiceError,
    ServiceUnavailableError,
    ValidationError,
)
from app.schemas.transcription import TranscriptionResponse
from app.services.transcription import (
    MAX_AUDIO_BYTES,
    LeadTranscriptionContext,
    TranscriptionError,
    TranscriptionUnavailable,
    transcribe_uploaded,
)

router = APIRouter(tags=["transcription"])


@router.post("/transcribe-note", response_model=TranscriptionResponse)
async def transcribe_note_for_new_lead(
    db: DbSession,
    user: CurrentUser,
    audio_file: UploadFile = File(...),
    lead_name: str | None = Form(default=None),
    service_category: str | None = Form(default=None),
    service_subtype: str | None = Form(default=None),
) -> TranscriptionResponse:
    """תמלול קולי בלי lead — לטופס יצירת ליד חדש (NewLeadModal).

    הקונטקסט הוא ה-form fields שכבר הוקלדו בטופס. אם הם ריקים, ה-prompt
    יישלח ריק ל-OpenAI (התמלול עדיין עובד, רק פחות מדויק על שמות).

    אבטחה: דורש auth כמו האנדפוינט ה-per-lead — תמלול עולה כסף, לא
    חושפים את ה-endpoint לציבור.

    Errors זהים לאנדפוינט ה-per-lead:
    - 422: mime לא נתמך / קובץ ריק / גדול מ-10MB.
    - 502: כשל ב-OpenAI / רשת.
    - 503: OPENAI_API_KEY לא מוגדר.
    """
    # streaming read עם size guard — זהה ל-route ה-per-lead.
    audio_bytes = await audio_file.read(MAX_AUDIO_BYTES + 1)
    if len(audio_bytes) > MAX_AUDIO_BYTES:
        raise ValidationError("הקובץ גדול מדי. הקלטה מקסימלית ~5 דקות.")

    # סגירת ה-DB session לפני קריאת OpenAI הארוכה (5-30 שניות) — מונע
    # מיצוי pool תחת העלאות מקבילות. אותו עיקרון כמו ב-route ה-per-lead.
    await db.close()

    # ctx בלי lead — id=None, השדות האחרים מהטופס (אם הוקלדו).
    # ה-empty-string טיפול: נועה שלחה form בלי הטקסט → מתפרש כ-None.
    ctx = LeadTranscriptionContext(
        id=None,
        full_name=(lead_name or None),
        service_category=(service_category or None),
        service_subtype=(service_subtype or None),
    )

    try:
        text = await transcribe_uploaded(
            audio_bytes, audio_file.content_type, ctx
        )
    except TranscriptionUnavailable as exc:
        raise ServiceUnavailableError(
            "שירות התמלול לא זמין כרגע."
        ) from exc
    except TranscriptionError as exc:
        raise ExternalServiceError(
            "התמלול נכשל. נסי שוב או הקלידי ידנית."
        ) from exc

    return TranscriptionResponse(text=text)
