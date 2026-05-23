"""
שירות auth — login, refresh, אימות משתמש.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    verify_password,
)
from app.models.user import User
from app.schemas.auth import TokenResponse


async def authenticate_user(
    db: AsyncSession, email: str, password: str
) -> User:
    """מאמת user/password. תמיד מחזיר AuthError גנרי — לא חושף אם המייל קיים."""
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    # בדיקת הסיסמה גם אם user is None — למניעת timing attacks.
    if user is None or not user.password_hash:
        # הרצת hash dummy כדי לשמור על timing דומה
        verify_password(password, "$2b$12$" + "x" * 53)
        raise AuthError()

    if not verify_password(password, user.password_hash):
        raise AuthError()

    return user


async def login(db: AsyncSession, email: str, password: str) -> TokenResponse:
    user = await authenticate_user(db, email, password)
    access_token, expires_in = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
    )


async def refresh(db: AsyncSession, refresh_token: str) -> TokenResponse:
    user_id = decode_refresh_token(refresh_token)
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise AuthError()
    access_token, expires_in = create_access_token(user.id)
    new_refresh = create_refresh_token(user.id)
    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh,
        expires_in=expires_in,
    )


async def get_user_by_id(db: AsyncSession, user_id: UUID) -> User | None:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()
