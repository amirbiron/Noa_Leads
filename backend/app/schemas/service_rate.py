"""
Schemas לתעריפי שירות — Spec v2.1 §5.10.
"""

from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ServiceRateRead(BaseModel):
    """תעריף + ערכים מחושבים (total_hours, hourly_rate) לתצוגה ב-UI."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    service_category: str
    service_subtype: str
    label: str
    default_price: Decimal | None
    default_duration_minutes: int | None
    default_sessions_count: int | None
    # מחושב: (duration × sessions) / 60.
    total_hours: Decimal | None = None
    # מחושב: price / total_hours. None אם price/hours חסרים.
    hourly_rate: Decimal | None = None
    notes: str | None
    is_active: bool


class ServiceRateUpdate(BaseModel):
    """PATCH partial — כל השדות אופציונליים. label לא ניתן לעריכה (קבוע מהspec)."""

    default_price: Decimal | None = Field(default=None, ge=0)
    default_duration_minutes: int | None = Field(
        default=None, ge=1, le=1440
    )  # עד יום אחד; ערכים סבירים: 30-180.
    default_sessions_count: int | None = Field(default=None, ge=1, le=200)
    notes: str | None = None
    is_active: bool | None = None
