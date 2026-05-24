"""
תלות (Dependencies) משותפות ל-FastAPI: שליפת current_user, session.
"""

from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import UserRole
from app.core.exceptions import AuthError, ForbiddenError
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.user import User
from app.services.auth import get_user_by_id


async def current_user(
    db: Annotated[AsyncSession, Depends(get_db)],
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    """שולף את המשתמש המאומת מתוך header Authorization: Bearer <token>."""
    if not authorization:
        raise AuthError()

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise AuthError()

    token = parts[1]
    user_id = decode_access_token(token)
    user = await get_user_by_id(db, user_id)
    if user is None:
        raise AuthError()
    return user


CurrentUser = Annotated[User, Depends(current_user)]
DbSession = Annotated[AsyncSession, Depends(get_db)]


async def require_owner(user: CurrentUser) -> User:
    """guard לפעולות שזמינות רק לבעלים (לא לעוזרת)."""
    if user.role != UserRole.OWNER.value:
        raise ForbiddenError("פעולה זו זמינה לבעלים בלבד.")
    return user


OwnerOnly = Annotated[User, Depends(require_owner)]
