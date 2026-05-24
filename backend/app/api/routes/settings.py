"""
Settings routes — תעריפי שירות (F-03).

GET קורא מה-DB (טבלת service_rates שנוצרה ב-migration 0015).
PATCH מאפשר לנועה (Owner) לערוך מחיר / מפגשים / הערות.
"""

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession, OwnerOnly
from app.schemas.service_rate import ServiceRateRead, ServiceRateUpdate
from app.services import service_rates as service_rates_service

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/service-rates", response_model=list[ServiceRateRead])
async def list_service_rates(
    db: DbSession, _user: CurrentUser
) -> list[ServiceRateRead]:
    """תעריפי ברירת מחדל לכל שירות + total_hours + hourly_rate מחושבים."""
    return await service_rates_service.list_service_rates(db)


@router.patch(
    "/service-rates/{subtype}", response_model=ServiceRateRead
)
async def update_service_rate(
    subtype: str,
    payload: ServiceRateUpdate,
    db: DbSession,
    _owner: OwnerOnly,
) -> ServiceRateRead:
    """עריכת תעריף — owner-only. PATCH partial על price/duration/sessions/notes/is_active."""
    return await service_rates_service.update_service_rate_by_subtype(
        db, subtype, payload
    )
