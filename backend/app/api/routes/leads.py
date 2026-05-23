"""
Leads routes — CRUD, actions, close, reopen, timeline.
"""

from uuid import UUID

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession
from app.schemas.activity import ActionRequest, ActivityRead
from app.schemas.common import PaginatedResponse
from app.schemas.lead import (
    LeadCloseRequest,
    LeadCreate,
    LeadListItem,
    LeadRead,
    LeadUpdate,
)
from app.services import leads as leads_service
from app.services import lead_actions as actions_service

router = APIRouter(prefix="/leads", tags=["leads"])


@router.post("", response_model=LeadRead, status_code=201)
async def create_lead(
    payload: LeadCreate, db: DbSession, user: CurrentUser
) -> LeadRead:
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


@router.get("/{lead_id}/timeline", response_model=list[ActivityRead])
async def get_timeline(
    lead_id: UUID, db: DbSession, user: CurrentUser
) -> list[ActivityRead]:
    activities = await leads_service.get_timeline(db, lead_id)
    return [ActivityRead.model_validate(a) for a in activities]
