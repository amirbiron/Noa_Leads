"""
שירות templates — CRUD + render לפי ליד.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.template import Template
from app.schemas.template import (
    TemplateCreate,
    TemplateRenderResponse,
    TemplateUpdate,
)
from app.services.leads import get_lead_or_404
from app.utils.template_render import (
    SUPPORTED_VARIABLES,
    build_variable_context,
    extract_placeholders,
    render_template,
)


# ===================== CRUD =====================

async def list_templates(
    db: AsyncSession, *, active_only: bool = False
) -> list[Template]:
    stmt = select(Template)
    if active_only:
        stmt = stmt.where(Template.is_active.is_(True))
    stmt = stmt.order_by(Template.name.asc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_template_or_404(db: AsyncSession, template_id: UUID) -> Template:
    result = await db.execute(select(Template).where(Template.id == template_id))
    template = result.scalar_one_or_none()
    if template is None:
        raise NotFoundError("תבנית לא נמצאה.")
    return template


async def create_template(
    db: AsyncSession, payload: TemplateCreate, created_by: UUID | None
) -> Template:
    template = Template(
        name=payload.name,
        channel=str(payload.channel),
        target_audience=(
            str(payload.target_audience) if payload.target_audience else None
        ),
        body=payload.body,
        variables=payload.variables,
        is_active=payload.is_active,
        created_by=created_by,
    )
    db.add(template)
    await db.commit()
    await db.refresh(template)
    return template


async def update_template(
    db: AsyncSession, template_id: UUID, payload: TemplateUpdate
) -> Template:
    template = await get_template_or_404(db, template_id)
    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        if hasattr(value, "value"):
            value = value.value
        setattr(template, key, value)
    await db.commit()
    await db.refresh(template)
    return template


async def delete_template(db: AsyncSession, template_id: UUID) -> None:
    """soft delete — מסמן is_active=False במקום למחוק. שומר על היסטוריה."""
    template = await get_template_or_404(db, template_id)
    template.is_active = False
    await db.commit()


# ===================== Render =====================

async def render_template_for_lead(
    db: AsyncSession, template_id: UUID, lead_id: UUID
) -> TemplateRenderResponse:
    template = await get_template_or_404(db, template_id)
    lead = await get_lead_or_404(db, lead_id)

    context = build_variable_context(lead)
    rendered = render_template(template.body, context)

    # זיהוי משתנים שהוזכרו ב-body אבל ה-context לא מספק להם ערך
    found = set(extract_placeholders(template.body))
    supported = set(SUPPORTED_VARIABLES.keys())
    # missing = placeholders שהיו אבל לא נתמכים בכלל
    missing = sorted(found - supported)

    return TemplateRenderResponse(
        template_id=template.id,
        lead_id=lead.id,
        rendered_body=rendered,
        channel=template.channel,
        missing_variables=missing,
    )
