"""
Templates routes — CRUD + render לפי ליד.
"""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession
from app.schemas.template import (
    TemplateCreate,
    TemplateRead,
    TemplateRenderResponse,
    TemplateUpdate,
)
from app.services import templates as templates_service

router = APIRouter(prefix="/templates", tags=["templates"])


@router.get("", response_model=list[TemplateRead])
async def list_templates(
    db: DbSession,
    user: CurrentUser,
    active_only: bool = Query(default=False),
) -> list[TemplateRead]:
    items = await templates_service.list_templates(db, active_only=active_only)
    return [TemplateRead.model_validate(t) for t in items]


@router.post("", response_model=TemplateRead, status_code=201)
async def create_template(
    payload: TemplateCreate, db: DbSession, user: CurrentUser
) -> TemplateRead:
    template = await templates_service.create_template(db, payload, user.id)
    return TemplateRead.model_validate(template)


# חייב להירשם *לפני* GET /{template_id} — אחרת FastAPI יפרש "auto" כ-UUID
# ויחזיר 422 לפני שיגיע לפה.
@router.get("/auto", response_model=TemplateRead)
async def auto_select_template(
    db: DbSession,
    user: CurrentUser,
    lead_id: UUID = Query(...),
    role: Literal["opening", "proposal", "proposal_followup"] = Query(...),
) -> TemplateRead:
    """
    מחזיר את התבנית הקנונית לתפקיד (opening/proposal/proposal_followup)
    עבור הליד הזה. 404 = אין canonical → frontend פותח TemplatePickerSheet
    הרגיל (בחירה ידנית).
    """
    template = await templates_service.auto_select_template_for_lead(
        db, lead_id, role
    )
    return TemplateRead.model_validate(template)


@router.get("/{template_id}", response_model=TemplateRead)
async def get_template(
    template_id: UUID, db: DbSession, user: CurrentUser
) -> TemplateRead:
    template = await templates_service.get_template_or_404(db, template_id)
    return TemplateRead.model_validate(template)


@router.patch("/{template_id}", response_model=TemplateRead)
async def update_template(
    template_id: UUID,
    payload: TemplateUpdate,
    db: DbSession,
    user: CurrentUser,
) -> TemplateRead:
    template = await templates_service.update_template(db, template_id, payload)
    return TemplateRead.model_validate(template)


@router.delete("/{template_id}", status_code=204)
async def delete_template(
    template_id: UUID, db: DbSession, user: CurrentUser
) -> None:
    await templates_service.delete_template(db, template_id)


@router.post("/{template_id}/render", response_model=TemplateRenderResponse)
async def render_template(
    template_id: UUID,
    db: DbSession,
    user: CurrentUser,
    lead_id: UUID = Query(...),
) -> TemplateRenderResponse:
    return await templates_service.render_template_for_lead(
        db, template_id, lead_id
    )
