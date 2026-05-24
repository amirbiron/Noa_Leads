"""
Routes לצ'יפים מהירים: list (כל המשתמשים) + CRUD (Owner בלבד).
"""

from uuid import UUID

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession, OwnerOnly
from app.schemas.quick_action_chip import (
    QuickActionChipCreate,
    QuickActionChipRead,
    QuickActionChipUpdate,
)
from app.services import quick_action_chips as chips_service

router = APIRouter(prefix="/chips", tags=["chips"])


@router.get("", response_model=list[QuickActionChipRead])
async def list_chips(
    db: DbSession,
    _user: CurrentUser,
    active_only: bool = Query(
        default=False,
        description="True ל-QuickActions ב-UI (רק פעילים), False לעמוד הגדרות",
    ),
) -> list[QuickActionChipRead]:
    chips = await chips_service.list_chips(db, active_only=active_only)
    return [QuickActionChipRead.model_validate(c) for c in chips]


@router.post("", response_model=QuickActionChipRead, status_code=201)
async def create_chip(
    payload: QuickActionChipCreate, db: DbSession, _owner: OwnerOnly
) -> QuickActionChipRead:
    chip = await chips_service.create_chip(db, payload)
    return QuickActionChipRead.model_validate(chip)


@router.patch("/{chip_id}", response_model=QuickActionChipRead)
async def update_chip(
    chip_id: UUID,
    payload: QuickActionChipUpdate,
    db: DbSession,
    _owner: OwnerOnly,
) -> QuickActionChipRead:
    chip = await chips_service.update_chip(db, chip_id, payload)
    return QuickActionChipRead.model_validate(chip)


@router.delete("/{chip_id}", status_code=204)
async def delete_chip(
    chip_id: UUID, db: DbSession, _owner: OwnerOnly
) -> None:
    await chips_service.delete_chip(db, chip_id)
