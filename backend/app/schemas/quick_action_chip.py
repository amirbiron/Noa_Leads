"""
סכמות צ'יפים מהירים — לקריאה/יצירה/עדכון מעמוד הגדרות.
"""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class QuickActionChipRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    label: str
    action_type: str
    requires_content: bool
    sort_order: int
    is_active: bool


class QuickActionChipCreate(BaseModel):
    label: str = Field(min_length=1, max_length=100)
    action_type: str = Field(min_length=1, max_length=50)
    requires_content: bool = False
    sort_order: int = 0
    is_active: bool = True


class QuickActionChipUpdate(BaseModel):
    """כל השדות אופציונליים — partial update."""

    label: str | None = Field(default=None, min_length=1, max_length=100)
    action_type: str | None = Field(default=None, min_length=1, max_length=50)
    requires_content: bool | None = None
    sort_order: int | None = None
    is_active: bool | None = None
