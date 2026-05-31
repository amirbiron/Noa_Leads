"""
Leads routes — CRUD, actions, close, reopen, timeline.
"""

from uuid import UUID

from fastapi import APIRouter, File, Query, UploadFile

from app.api.deps import CurrentUser, DbSession
from app.core.exceptions import (
    ExternalServiceError,
    ServiceUnavailableError,
    ValidationError,
)
from app.schemas.activity import ActionRequest, ActivityRead
from app.schemas.common import PaginatedResponse
from app.schemas.email_message import EmailMessageRead
from app.schemas.lead import (
    DormantSuggestionRead,
    LeadCloseRequest,
    LeadCreateManual,
    LeadListItem,
    LeadRead,
    LeadTransferRequest,
    LeadUpdate,
)
from app.schemas.transcription import TranscriptionResponse
from app.services import leads as leads_service
from app.services import lead_actions as actions_service
from app.services import quick_action_chips as chips_service
from app.services.transcription import (
    MAX_AUDIO_BYTES,
    LeadTranscriptionContext,
    TranscriptionError,
    TranscriptionUnavailable,
    transcribe_uploaded,
)

router = APIRouter(prefix="/leads", tags=["leads"])


@router.post("", response_model=LeadRead, status_code=201)
async def create_lead(
    payload: LeadCreateManual, db: DbSession, user: CurrentUser
) -> LeadRead:
    # LeadCreateManual — lead_message חובה בטופס הידני (§7.1). הוא subclass
    # של LeadCreate, אז create_lead מקבל אותו ללא שינוי.
    lead = await leads_service.create_lead(db, payload, user.id)
    return LeadRead.model_validate(lead)


@router.get("", response_model=PaginatedResponse[LeadListItem])
async def list_leads(
    db: DbSession,
    user: CurrentUser,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    status: str | None = Query(default=None),
    waiting_on: str | None = Query(default=None),
    owner_id: UUID | None = Query(default=None),
    source_channel: str | None = Query(default=None),
    needs_attention: bool | None = Query(default=None),
    search: str | None = Query(default=None, max_length=200),
    closed: bool | None = Query(default=None),
) -> PaginatedResponse[LeadListItem]:
    items, total = await leads_service.list_leads(
        db,
        page=page,
        page_size=page_size,
        status=status,
        waiting_on=waiting_on,
        owner_id=owner_id,
        source_channel=source_channel,
        needs_attention=needs_attention,
        search=search,
        closed=closed,
    )
    return PaginatedResponse[LeadListItem](
        items=[LeadListItem.model_validate(x) for x in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{lead_id}", response_model=LeadRead)
async def get_lead(lead_id: UUID, db: DbSession, user: CurrentUser) -> LeadRead:
    lead = await leads_service.get_lead_or_404(db, lead_id)
    return LeadRead.model_validate(lead)


@router.patch("/{lead_id}", response_model=LeadRead)
async def patch_lead(
    lead_id: UUID, payload: LeadUpdate, db: DbSession, user: CurrentUser
) -> LeadRead:
    lead = await leads_service.update_lead(db, lead_id, payload, user.id)
    return LeadRead.model_validate(lead)


@router.post("/{lead_id}/actions/{action_type}", response_model=LeadRead)
async def perform_action(
    lead_id: UUID,
    action_type: str,
    payload: ActionRequest,
    db: DbSession,
    user: CurrentUser,
) -> LeadRead:
    lead = await actions_service.perform_action(
        db,
        lead_id,
        action_type,
        current_user_id=user.id,
        content=payload.content,
        metadata=payload.metadata,
    )
    return LeadRead.model_validate(lead)


@router.post("/{lead_id}/transfer", response_model=LeadRead)
async def transfer_lead(
    lead_id: UUID,
    payload: LeadTransferRequest,
    db: DbSession,
    user: CurrentUser,
) -> LeadRead:
    lead = await leads_service.transfer_lead(db, lead_id, payload, user.id)
    return LeadRead.model_validate(lead)


@router.post("/{lead_id}/close", response_model=LeadRead)
async def close_lead(
    lead_id: UUID,
    payload: LeadCloseRequest,
    db: DbSession,
    user: CurrentUser,
) -> LeadRead:
    lead = await leads_service.close_lead(db, lead_id, payload, user.id)
    return LeadRead.model_validate(lead)


@router.post("/{lead_id}/reopen", response_model=LeadRead)
async def reopen_lead(
    lead_id: UUID, db: DbSession, user: CurrentUser
) -> LeadRead:
    lead = await leads_service.reopen_lead(db, lead_id, user.id)
    return LeadRead.model_validate(lead)


@router.post("/{lead_id}/apply-chip/{chip_id}", response_model=LeadRead)
async def apply_chip(
    lead_id: UUID,
    chip_id: UUID,
    db: DbSession,
    user: CurrentUser,
) -> LeadRead:
    """
    מפעיל צ'יפ מהיר על ליד — Spec v2.1 §16.4.

    מבצע אטומית: ליד.status=target_status, ליד.waiting_on=waiting_on,
    יוצר task חדש מסוג followup_task_type עם due_at=now+auto_followup_days,
    ורושם activity. שגיאות: 404 (ליד/צ'יפ), 400 (ליד סגור / צ'יפ לא מאוכלס).
    """
    lead = await chips_service.apply_chip(
        db, lead_id=lead_id, chip_id=chip_id, performed_by=user.id
    )
    return LeadRead.model_validate(lead)


@router.get("/{lead_id}/timeline", response_model=list[ActivityRead])
async def get_timeline(
    lead_id: UUID, db: DbSession, user: CurrentUser
) -> list[ActivityRead]:
    activities = await leads_service.get_timeline(db, lead_id)
    return [ActivityRead.model_validate(a) for a in activities]


@router.get("/{lead_id}/emails", response_model=list[EmailMessageRead])
async def get_lead_emails(
    lead_id: UUID, db: DbSession, user: CurrentUser
) -> list[EmailMessageRead]:
    """מיילים נכנסים שקושרו לליד (Spec §20.10). מהחדש לישן."""
    emails = await leads_service.get_lead_emails(db, lead_id)
    return [EmailMessageRead.model_validate(e) for e in emails]


@router.get(
    "/{lead_id}/dormant-suggestion", response_model=DormantSuggestionRead | None
)
async def read_dormant_suggestion(
    lead_id: UUID, db: DbSession, user: CurrentUser
) -> DormantSuggestionRead | None:
    """המלצת פעולה AI לליד רדום (§19 D.1), או null אם אין המלצה פתוחה."""
    task = await leads_service.get_dormant_suggestion(db, lead_id)
    if task is None or not task.task_metadata:
        return None
    meta = task.task_metadata
    return DormantSuggestionRead(
        action=meta.get("ai_action", "no_action"),
        reasoning=meta.get("ai_reasoning", ""),
        generated_at=meta.get("ai_generated_at"),
        model_used=meta.get("model_used"),
    )


@router.post(
    "/{lead_id}/transcribe-note", response_model=TranscriptionResponse
)
async def transcribe_note(
    lead_id: UUID,
    db: DbSession,
    user: CurrentUser,
    audio_file: UploadFile = File(...),
) -> TranscriptionResponse:
    """תיעוד קולי (§13.3) — תמלול אודיו לטקסט עברי בהקשר של הליד.

    **לא נוגע ב-DB:** מחזיר רק את הטקסט. ה-UI מציג אותו ל-נועה ב-textarea,
    היא יכולה לערוך ולשמור דרך PATCH /leads/{id} הרגיל. בכוונה — תמלול
    עברי לא מושלם, מצריך בדיקה לפני התחייבות.

    **פרטיות:** קובץ האודיו לא נשמר ב-DB ולא ב-FS קבוע — temp file
    נמחק מיד אחרי קריאה ל-OpenAI.

    Errors:
    - 422: mime לא נתמך / קובץ ריק / גדול מ-10MB.
    - 502: כשל ב-OpenAI / רשת.
    - 503: OPENAI_API_KEY לא מוגדר ב-server.
    """
    # ולידציית קיום ליד לפני קריאת bytes — נכשל מהר אם 404.
    lead = await leads_service.get_lead_or_404(db, lead_id)
    ctx = LeadTranscriptionContext.from_lead(lead)

    # streaming read עם size guard. UploadFile.read() מעמיס לזיכרון —
    # 10MB סביר לאיפון אבל לא רוצים לקרוא יותר אם משהו תקול.
    audio_bytes = await audio_file.read(MAX_AUDIO_BYTES + 1)
    if len(audio_bytes) > MAX_AUDIO_BYTES:
        raise ValidationError("הקובץ גדול מדי. הקלטה מקסימלית ~5 דקות.")

    # סגירת ה-DB session **לפני** קריאת OpenAI הארוכה (5-30 שניות).
    # pool_size=5, max_overflow=10 → 15 חיבורים בלבד. בלי סגירה, 15
    # voice uploads מקבילים שולחים את ה-pool למיצוי וחוסמים את שאר
    # ה-API. ה-`ctx` snapshot כבר מכיל את כל מה שצריך להלן.
    # FastAPI יקרא ל-close שוב בסוף ה-handler — no-op.
    await db.close()

    try:
        text = await transcribe_uploaded(
            audio_bytes, audio_file.content_type, ctx
        )
    except TranscriptionUnavailable as exc:
        # 503 — OPENAI_API_KEY חסר. ה-UI יכול להציג "תיעוד קולי לא זמין".
        raise ServiceUnavailableError(
            "שירות התמלול לא זמין כרגע."
        ) from exc
    except TranscriptionError as exc:
        # 502 — נכשל ב-API / רשת. ה-UI יציע ניסיון חוזר / הקלדה ידנית.
        raise ExternalServiceError(
            "התמלול נכשל. נסי שוב או הקלידי ידנית."
        ) from exc

    return TranscriptionResponse(text=text)
