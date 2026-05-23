"""
סכמות activity — קריאה (timeline) ויצירה ידנית (internal note, log call).
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ActivityRead(BaseModel):
    """item ב-timeline של ליד."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    type: str
    content: str | None
    activity_metadata: dict[str, Any] | None = Field(
        default=None, alias="activity_metadata"
    )
    performed_by: UUID | None
    created_at: datetime


class ActionRequest(BaseModel):
    """גוף בקשה ל-POST /leads/{id}/actions/{action_type}."""

    content: str | None = None
    # מטא-דאטה ספציפית לפעולה — לדוגמה {"template_id": "..."}
    metadata: dict[str, Any] | None = None
