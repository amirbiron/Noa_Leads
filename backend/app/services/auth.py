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
    hash_password,
    verify_password,
)
from app.models.user import User
from app.schemas.auth import TokenResponse


# bcrypt hash אמיתי שנוצר פעם אחת בטעינת המודול. משמש להרצת verify
# על משתמש שלא קיים כדי שזמן התגובה לא יחשוף את קיומו (timing attack).
# בעבר השתמשנו בקבוע פייק ($2b$12$ + "x"*53) שעבד אבל עלול להישבר
# בעדכוני passlib עתידיים. dummy אמיתי יציב לאורך זמן.
_DUMMY_HASH = hash_password("__noa_leads_auth_timing_dummy__")


async def authenticate_user(
    db: AsyncSession, email: str, password: str
) -> User:
    """מאמת user/password. תמיד מחזיר AuthError גנרי — לא חושף אם המייל קיים."""
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    # בדיקת הסיסמה גם אם user is None — למניעת timing attacks.
    if user is None or not user.password_hash:
        # הרצת verify מול hash תקין כדי לשמור על זמן תגובה דומה
        verify_password(password, _DUMMY_HASH)
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
