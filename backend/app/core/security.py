"""
JWT + hashing סיסמאות (bcrypt).
"""

from datetime import datetime, timedelta, timezone
from uuid import UUID

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import get_settings
from app.core.exceptions import AuthError

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ===== סיסמאות =====

def hash_password(plain: str) -> str:
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_context.verify(plain, hashed)


# ===== JWT =====

_ACCESS = "access"
_REFRESH = "refresh"


def _create_token(subject: str, token_type: str, expires_delta: timedelta) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
    }
    return jwt.encode(
        payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
    )


def create_access_token(user_id: UUID) -> tuple[str, int]:
    """מחזיר (token, expires_in_seconds)."""
    settings = get_settings()
    delta = timedelta(minutes=settings.jwt_access_token_minutes)
    token = _create_token(str(user_id), _ACCESS, delta)
    return token, int(delta.total_seconds())


def create_refresh_token(user_id: UUID) -> str:
    settings = get_settings()
    delta = timedelta(days=settings.jwt_refresh_token_days)
    return _create_token(str(user_id), _REFRESH, delta)


def decode_token(token: str, expected_type: str) -> UUID:
    """מפענח JWT ומחזיר user_id. זורק AuthError בהודעה גנרית."""
    settings = get_settings()
    try:
        payload = jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
    except JWTError:
        # ההודעה הפנימית של jose לא נחשפת — אנחנו מחזירים הודעה כללית
        raise AuthError() from None

    if payload.get("type") != expected_type:
        raise AuthError()

    sub = payload.get("sub")
    if not sub:
        raise AuthError()

    try:
        return UUID(sub)
    except (ValueError, TypeError):
        raise AuthError() from None


def decode_access_token(token: str) -> UUID:
    return decode_token(token, _ACCESS)


def decode_refresh_token(token: str) -> UUID:
    return decode_token(token, _REFRESH)
