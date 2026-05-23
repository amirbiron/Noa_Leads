"""
Settings routes — נכון לעכשיו read-only.

בעתיד יתווסף PATCH לחישוב חוקים מותאמים אישית (chips, followup, וכו').
"""

from decimal import Decimal

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.deps import CurrentUser
from app.utils.service_rates import SERVICE_RATES

router = APIRouter(prefix="/settings", tags=["settings"])


class ServiceRateRead(BaseModel):
    subtype: str
    label: str
    category: str
    default_price: Decimal | None
    default_hours: Decimal | None
    hourly_rate: Decimal | None  # מחושב — לתצוגה ב-UI


@router.get("/service-rates", response_model=list[ServiceRateRead])
async def list_service_rates(user: CurrentUser) -> list[ServiceRateRead]:
    """תעריפי ברירת מחדל לכל שירות + תעריף שעתי מחושב."""
    items: list[ServiceRateRead] = []
    for subtype, info in SERVICE_RATES.items():
        price = info["default_price"]
        hours = info["default_hours"]
        rate = None
        if price is not None and hours is not None and hours > 0:
            rate = (Decimal(price) / Decimal(hours)).quantize(Decimal("0.01"))
        items.append(
            ServiceRateRead(
                subtype=subtype,
                label=info["label"],
                category=info["category"],
                default_price=price,
                default_hours=hours,
                hourly_rate=rate,
            )
        )
    return items
