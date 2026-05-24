"""
סכמות setup — יצירת משתמש ראשון דרך ה-UI (אין צורך ב-CLI).
"""

from pydantic import BaseModel, EmailStr, Field


class SetupStatusResponse(BaseModel):
    """האם המערכת דורשת הגדרה ראשונית?"""

    setup_needed: bool
    users_count: int


class InitialOwnerCreate(BaseModel):
    """יצירת משתמש Owner ראשון. נדחה אם כבר קיים משתמש כלשהו."""

    email: EmailStr
    name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=8, max_length=72)
