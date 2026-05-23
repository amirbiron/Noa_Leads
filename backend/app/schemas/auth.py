"""
סכמות auth — login, refresh, token response.
"""

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # שניות עד פקיעת access_token


class TokenPayload(BaseModel):
    """תוכן ה-JWT לאחר פענוח."""

    sub: str   # user_id (string)
    type: str  # "access" / "refresh"
    exp: int
