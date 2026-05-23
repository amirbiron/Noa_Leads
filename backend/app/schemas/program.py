"""
סכמות programs — תוכניות מתמשכות לליד.
"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.constants import ProgramType


# ===================== יצירה =====================

class ProgramCreate(BaseModel):
    lead_id: UUID
    program_type: ProgramType
    total_sessions: int = Field(ge=1, le=100)
    total_price: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    estimated_end_at: datetime | None = None


# ===================== עדכון =====================

class ProgramUpdate(BaseModel):
    """עדכון מצב התוכנית — מספר מפגשים שבוצעו, שעות בפועל."""

    completed_sessions: int | None = Field(default=None, ge=0)
    actual_hours: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    total_price: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    estimated_end_at: datetime | None = None


# ===================== קריאה =====================

class ProgramRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    lead_id: UUID
    program_type: str
    total_sessions: int
    completed_sessions: int
    total_price: Decimal | None
    actual_hours: Decimal
    started_at: datetime
    estimated_end_at: datetime | None
    status: str


class ProgramWithLeadRead(ProgramRead):
    """גרסה מורחבת — לתצוגה ב-/programs/active עם פרטי הלקוח."""

    lead_name: str
    lead_organization: str | None
