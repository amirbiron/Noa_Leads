"""
סכמות משימות (Tasks) — לקריאה, יצירה, snooze, complete.
"""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.constants import TaskType


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    lead_id: UUID
    type: str
    assigned_to: UUID | None
    due_at: datetime
    status: str
    snoozed_until: datetime | None
    origin_rule: str | None
    created_at: datetime
    completed_at: datetime | None


class TaskWithLeadRead(TaskRead):
    """task + שדות עיקריים מהליד — לתצוגה ב"פעולות היום"."""

    lead_name: str
    lead_status: str
    lead_priority_level: str


class TaskCreate(BaseModel):
    """יצירה ידנית של משימה (לרוב tasks נוצרות אוטומטית בעקבות פעולות)."""

    lead_id: UUID
    type: TaskType
    due_at: datetime
    assigned_to: UUID | None = None


# ===== Snooze — קיצורי דרך לפי האפיון =====

class SnoozePreset(StrEnum):
    TODAY_AFTERNOON = "today_afternoon"
    TOMORROW_MORNING = "tomorrow_morning"
    SUNDAY_MORNING = "sunday_morning"
    AFTER_HOLIDAY = "after_holiday"
    CUSTOM = "custom"


class SnoozeRequest(BaseModel):
    preset: SnoozePreset
    # נדרש רק אם preset=custom
    custom_until: datetime | None = Field(default=None)

    @model_validator(mode="after")
    def _custom_requires_date(self) -> "SnoozeRequest":
        if self.preset == SnoozePreset.CUSTOM and self.custom_until is None:
            raise ValueError(
                "בבחירת 'תאריך מותאם' חובה לציין את התאריך החדש"
            )
        if self.preset != SnoozePreset.CUSTOM and self.custom_until is not None:
            raise ValueError(
                "תאריך מותאם נשלח אבל הקיצור שנבחר הוא לא 'custom'"
            )
        return self
