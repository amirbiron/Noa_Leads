"""
Programs routes — תוכניות מתמשכות.
"""

from uuid import UUID

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.schemas.program import (
    ProgramCreate,
    ProgramRead,
    ProgramUpdate,
    ProgramWithLeadRead,
)
from app.services import programs as programs_service

router = APIRouter(prefix="/programs", tags=["programs"])


@router.get("/active", response_model=list[ProgramWithLeadRead])
async def list_active(
    db: DbSession, user: CurrentUser
) -> list[ProgramWithLeadRead]:
    """כל התוכניות הפעילות + פרטי הלקוח, ממוין לפי קרבת סיום."""
    items = await programs_service.list_active_programs(db)
    return [
        ProgramWithLeadRead(
            id=p.id,
            lead_id=p.lead_id,
            program_type=p.program_type,
            total_sessions=p.total_sessions,
            completed_sessions=p.completed_sessions,
            total_price=p.total_price,
            actual_hours=p.actual_hours,
            started_at=p.started_at,
            estimated_end_at=p.estimated_end_at,
            status=p.status,
            lead_name=lead.full_name,
            lead_organization=lead.organization_name,
        )
        for p, lead in items
    ]


@router.get("/lead/{lead_id}", response_model=list[ProgramRead])
async def list_for_lead(
    lead_id: UUID, db: DbSession, user: CurrentUser
) -> list[ProgramRead]:
    """תוכניות (פעילות + היסטוריות) של ליד ספציפי."""
    items = await programs_service.list_programs_for_lead(db, lead_id)
    return [ProgramRead.model_validate(p) for p in items]


@router.post("", response_model=ProgramRead, status_code=201)
async def create_program(
    payload: ProgramCreate, db: DbSession, user: CurrentUser
) -> ProgramRead:
    program = await programs_service.create_program(db, payload, user.id)
    return ProgramRead.model_validate(program)


@router.get("/{program_id}", response_model=ProgramRead)
async def get_program(
    program_id: UUID, db: DbSession, user: CurrentUser
) -> ProgramRead:
    program = await programs_service.get_program_or_404(db, program_id)
    return ProgramRead.model_validate(program)


@router.patch("/{program_id}", response_model=ProgramRead)
async def update_program(
    program_id: UUID,
    payload: ProgramUpdate,
    db: DbSession,
    user: CurrentUser,
) -> ProgramRead:
    program = await programs_service.update_program(
        db, program_id, payload, user.id
    )
    return ProgramRead.model_validate(program)


@router.post("/{program_id}/cancel", response_model=ProgramRead)
async def cancel_program(
    program_id: UUID, db: DbSession, user: CurrentUser
) -> ProgramRead:
    program = await programs_service.cancel_program(db, program_id, user.id)
    return ProgramRead.model_validate(program)
