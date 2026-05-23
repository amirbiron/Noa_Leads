"""
JWT + hashing סיסמאות (bcrypt).

passlib הוחלף בשימוש ישיר ב-bcrypt כי passlib 1.7.4 (יצא 2020) לא תואם
ל-bcrypt 4.x — נופל על ה-`__about__` שהוסר וב-`detect_wrap_bug` שמפעיל
checkpw עם > 72 bytes (bcrypt 4.1+ מסרב לחתוך שקט וזורק ValueError).
"""

from datetime import datetime, timedelta, timezone
from uuid import UUID

import bcrypt
from jose import JWTError, jwt

from app.config import get_settings
from app.core.exceptions import AuthError


# bcrypt 4.1+ מסרב לסיסמאות מעל 72 bytes. אנחנו חותכים בעצמנו לפני
# גם hash וגם verify, כך שהתנהגות זהה לגרסאות הישנות (וזהה לדפוס של
# Django/Flask). חשוב: גם ב-verify יש לחתוך באותה צורה — אחרת לסיסמה
# >72 התקפה לא תאומת.
_BCRYPT_MAX = 72


def _to_bytes(plain: str) -> bytes:
    return plain.encode("utf-8")[:_BCRYPT_MAX]


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(_to_bytes(plain), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_to_bytes(plain), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        # hash פגום או encoding לא תקין → טיפול כסיסמה שגויה, לא כשגיאה
        return False


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
