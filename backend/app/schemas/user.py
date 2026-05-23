"""
סכמות user — לקריאה בלבד (יצירה תיעשה דרך CLI/seed).
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    name: str
    role: str
    created_at: datetime
