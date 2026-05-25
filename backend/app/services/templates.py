"""
שירות templates — CRUD + render לפי ליד.
"""

from typing import Literal
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
    build_variable_context,
    extract_placeholders,
    render_template,
)


# ===== Canonical mapping של תפקיד+קהל → seed UUID =====
# מכווון לכפתורים הראשיים בכרטיס הליד (DynamicActionButton). הלוגיקה
# בקוד ולא בDB כי spec §9.5 מתיר לנועה למחוק/לערוך תבניות, אבל הזיהוי
# הקנוני של "תבנית פתיחה לארגון" צריך להישאר יציב. אם UUID זה לא קיים
# או שהתבנית בוטלה (is_active=False) — הroute מחזיר 404 וה-frontend
# פותח את TemplatePickerSheet הרגיל (בחירה ידנית).
#
# מקור: backend/alembic/versions/2026_05_24_0009-0009_seed_initial_templates.py
# Roles:
#   opening           — "פתיחה" (T1 פרטי / T2 ארגון)
#   proposal          — "הצעה" (T9 פרטי / T8 ארגון)
#   proposal_followup — "פולואף אחרי הצעה" (T4, audience-agnostic)
_CANONICAL_TEMPLATES: dict[tuple[str, str | None], UUID] = {
    ("opening", "organization"): UUID("00000000-0000-0009-0000-000000000002"),
    ("opening", "private"): UUID("00000000-0000-0009-0000-000000000001"),
    ("proposal", "organization"): UUID("00000000-0000-0009-0000-000000000008"),
    ("proposal", "private"): UUID("00000000-0000-0009-0000-000000000009"),
    ("proposal_followup", None): UUID("00000000-0000-0009-0000-000000000004"),
}

TemplateRole = Literal["opening", "proposal", "proposal_followup"]


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


# ===================== Auto-select =====================

async def auto_select_template_for_lead(
    db: AsyncSession, lead_id: UUID, role: TemplateRole
) -> Template:
    """
    מחזיר את התבנית הקנונית לפי תפקיד (opening/proposal/proposal_followup)
    + audience של הליד (organization אם יש organization_name, אחרת private).
    proposal_followup audience-agnostic.

    NotFoundError → 404 → frontend נופל ל-TemplatePickerSheet (בחירה ידנית).
    הסיגנל הזה (404, לא 200+null) מפשט את ה-branching ב-frontend.
    """
    lead = await get_lead_or_404(db, lead_id)
    audience = "organization" if lead.organization_name else "private"
    key: tuple[str, str | None] = (
        (role, None) if role == "proposal_followup" else (role, audience)
    )
    canonical_id = _CANONICAL_TEMPLATES.get(key)
    if canonical_id is None:
        # שילוב role+audience לא מוגדר. לא צפוי בקריאות מה-frontend (Literal),
        # אבל אם מישהו יקרא ל-API ישירות עם role לא חוקי — נטפל יפה.
        raise NotFoundError("אין מיפוי קנוני לתבנית.")

    result = await db.execute(
        select(Template).where(
            Template.id == canonical_id,
            Template.is_active.is_(True),
        )
    )
    template = result.scalar_one_or_none()
    if template is None:
        raise NotFoundError("התבנית הקנונית לא קיימת או לא פעילה.")
    return template


# ===================== Render =====================

async def render_template_for_lead(
    db: AsyncSession, template_id: UUID, lead_id: UUID
) -> TemplateRenderResponse:
    template = await get_template_or_404(db, template_id)
    lead = await get_lead_or_404(db, lead_id)

    context = build_variable_context(lead)
    rendered = render_template(template.body, context)

    # missing = כל placeholder ב-body שלא יתמלא כראוי בליד הזה:
    # - placeholder לא נתמך בכלל (טעות איות)
    # - placeholder נתמך אבל הליד חסר את הערך (למשל {organization} בלי ארגון)
    # שניהם פוגעים בטקסט הסופי ושווה להציג ל-UI לפני שליחה.
    found = set(extract_placeholders(template.body))
    missing = sorted(
        p for p in found
        if p not in context or not context[p]
    )

    return TemplateRenderResponse(
        template_id=template.id,
        lead_id=lead.id,
        rendered_body=rendered,
        channel=template.channel,
        missing_variables=missing,
    )
