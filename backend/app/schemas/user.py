"""
סכמות user — קריאה (UserRead) + יצירת עוזרת חד-פעמית (AssistantCreate).
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    name: str
    role: str
    created_at: datetime


class AssistantCreate(BaseModel):
    """יצירת עוזרת — setup חד-פעמי דרך ההגדרות. נדחה אם כבר קיימת עוזרת (§13.5)."""

    email: EmailStr
    name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=8, max_length=72)
