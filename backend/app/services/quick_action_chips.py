"""
שירות צ'יפים מהירים — CRUD עם validation של action_type מול state_machine.
"""

import logging
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.core.state_machine import ACTIONS
from app.models.quick_action_chip import QuickActionChip
from app.schemas.quick_action_chip import (
    QuickActionChipCreate,
    QuickActionChipUpdate,
)

logger = logging.getLogger(__name__)


def _validate_action_type(action_type: str) -> None:
    """
    ה-action_type חייב להתאים למפתח ב-state_machine.ACTIONS.

    שגיאה ידידותית בעברית למשתמש — בלי לחשוף את רשימת ה-action_types
    הפנימיים (כלל 3 ב-CLAUDE.md: אל תחשוף מידע פנימי ב-API responses).
    הפרטים נכנסים ל-log לדיבוג.
    """
    if action_type not in ACTIONS:
        logger.warning(
            "Rejected unknown action_type for chip: %r (valid: %s)",
            action_type,
            sorted(ACTIONS.keys()),
        )
        raise ValidationError("סוג פעולה לא תקף.")


async def list_chips(
    db: AsyncSession, *, active_only: bool = False
) -> list[QuickActionChip]:
    """
    כל הצ'יפים, ממוין לפי sort_order עולה.
    active_only=True — רק לתצוגה ב-QuickActions (לא בעמוד הגדרות).
    """
    stmt = select(QuickActionChip).order_by(
        QuickActionChip.sort_order.asc(), QuickActionChip.label.asc()
    )
    if active_only:
        stmt = stmt.where(QuickActionChip.is_active.is_(True))
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def create_chip(
    db: AsyncSession, payload: QuickActionChipCreate
) -> QuickActionChip:
    _validate_action_type(payload.action_type)
    chip = QuickActionChip(
        label=payload.label,
        action_type=payload.action_type,
        requires_content=payload.requires_content,
        sort_order=payload.sort_order,
        is_active=payload.is_active,
    )
    db.add(chip)
    await db.commit()
    await db.refresh(chip)
    return chip


async def update_chip(
    db: AsyncSession, chip_id: UUID, payload: QuickActionChipUpdate
) -> QuickActionChip:
    if payload.action_type is not None:
        _validate_action_type(payload.action_type)

    values = payload.model_dump(exclude_unset=True)
    if not values:
        return await _get_chip_or_404(db, chip_id)

    result = await db.execute(
        update(QuickActionChip)
        .where(QuickActionChip.id == chip_id)
        .values(**values)
        .returning(QuickActionChip.id)
    )
    if result.scalar_one_or_none() is None:
        raise NotFoundError("צ'יפ לא נמצא.")
    await db.commit()
    return await _get_chip_or_404(db, chip_id)


async def delete_chip(db: AsyncSession, chip_id: UUID) -> None:
    result = await db.execute(
        delete(QuickActionChip)
        .where(QuickActionChip.id == chip_id)
        .returning(QuickActionChip.id)
    )
    if result.scalar_one_or_none() is None:
        raise NotFoundError("צ'יפ לא נמצא.")
    await db.commit()


async def _get_chip_or_404(
    db: AsyncSession, chip_id: UUID
) -> QuickActionChip:
    result = await db.execute(
        select(QuickActionChip)
        .where(QuickActionChip.id == chip_id)
        .execution_options(populate_existing=True)
    )
    chip = result.scalar_one_or_none()
    if chip is None:
        raise NotFoundError("צ'יפ לא נמצא.")
    return chip
