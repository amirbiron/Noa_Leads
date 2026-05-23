"""
Authentication routes.
"""

from fastapi import APIRouter

from app.api.deps import DbSession
from app.schemas.auth import LoginRequest, RefreshRequest, TokenResponse
from app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: DbSession) -> TokenResponse:
    return await auth_service.login(db, payload.email, payload.password)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(payload: RefreshRequest, db: DbSession) -> TokenResponse:
    return await auth_service.refresh(db, payload.refresh_token)


@router.post("/logout", status_code=204)
async def logout() -> None:
    # JWT הוא stateless — logout בצד הלקוח (מחיקת הטוקן).
    # בעתיד אפשר להוסיף blacklist ב-Redis.
    return None
