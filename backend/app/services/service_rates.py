"""
שירות תעריפי שירות (service_rates) — Spec v2.1 §5.10 + F-03.

לפני המעבר, ה-defaults היו hardcoded ב-app/utils/service_rates.py. עכשיו
נטענים מ-DB דרך migration 0015. נועה יכולה לערוך דרך PATCH /settings/
service-rates/{subtype}.

total_hours ו-hourly_rate מחושבים ב-_to_read — לא נשמרים בטבלה.
"""

from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.service_rate import ServiceRate
from app.schemas.service_rate import ServiceRateRead, ServiceRateUpdate


def _compute_derived(
    price: Decimal | None,
    duration: int | None,
    sessions: int | None,
) -> tuple[Decimal | None, Decimal | None]:
    """
    מחשב (total_hours, hourly_rate) מהשדות הגולמיים.
    אם price או duration*sessions=0 → None — שירות "לבירור".
    """
    if duration is None or sessions is None or duration <= 0 or sessions <= 0:
        return (None, None)
    total_minutes = duration * sessions
    total_hours = (Decimal(total_minutes) / Decimal(60)).quantize(Decimal("0.01"))
    if price is None or total_hours <= 0:
        return (total_hours, None)
    hourly_rate = (Decimal(price) / total_hours).quantize(Decimal("0.01"))
    return (total_hours, hourly_rate)


def _to_read(row: ServiceRate) -> ServiceRateRead:
    total_hours, hourly_rate = _compute_derived(
        row.default_price,
        row.default_duration_minutes,
        row.default_sessions_count,
    )
    return ServiceRateRead(
        id=row.id,
        service_category=row.service_category,
        service_subtype=row.service_subtype,
        label=row.label,
        default_price=row.default_price,
        default_duration_minutes=row.default_duration_minutes,
        default_sessions_count=row.default_sessions_count,
        total_hours=total_hours,
        hourly_rate=hourly_rate,
        notes=row.notes,
        is_active=row.is_active,
    )


async def list_service_rates(db: AsyncSession) -> list[ServiceRateRead]:
    """כל התעריפים, ממוין לפי category ואז subtype."""
    result = await db.execute(
        select(ServiceRate).order_by(
            ServiceRate.service_category.asc(),
            ServiceRate.service_subtype.asc(),
        )
    )
    return [_to_read(row) for row in result.scalars().all()]


async def update_service_rate_by_subtype(
    db: AsyncSession,
    subtype: str,
    payload: ServiceRateUpdate,
) -> ServiceRateRead:
    """
    מעדכן תעריף לפי subtype (PATCH partial). מחזיר 404 אם לא קיים.
    אנחנו משתמשים ב-subtype כ-identifier ולא ב-UUID כי הוא ייחודי גלובלית
    (UNIQUE constraint על (category, subtype)) ויותר נוח ב-URLs.
    """
    values = payload.model_dump(exclude_unset=True)
    if not values:
        # אין מה לעדכן — מחזירים את הקיים.
        return await _get_or_404(db, subtype)

    result = await db.execute(
        update(ServiceRate)
        .where(ServiceRate.service_subtype == subtype)
        .values(**values)
        .returning(ServiceRate.id)
    )
    if result.scalar_one_or_none() is None:
        raise NotFoundError("תעריף לא נמצא.")
    await db.commit()
    return await _get_or_404(db, subtype)


async def _get_or_404(db: AsyncSession, subtype: str) -> ServiceRateRead:
    result = await db.execute(
        select(ServiceRate)
        .where(ServiceRate.service_subtype == subtype)
        .execution_options(populate_existing=True)
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise NotFoundError("תעריף לא נמצא.")
    return _to_read(row)
