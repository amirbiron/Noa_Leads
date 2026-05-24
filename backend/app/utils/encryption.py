"""
הצפנה סימטרית עם Fernet (cryptography) להגנה על secrets ב-DB —
בעיקר refresh_token של Google OAuth.

קונפיגורציה: SECRETS_ENCRYPTION_KEY ב-env, ערך Fernet key (44 chars
base64 url-safe). ייצור: `python -c "from cryptography.fernet import Fernet;
print(Fernet.generate_key().decode())"`.

ב-dev/test אם המפתח לא מוגדר — לוג WARN ושמירה plaintext (לא נעצרים).
בפרוד חובה להגדיר; אחרת tokens של חיבור Google ייחשפו ל-DBA.
"""

import logging

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings

logger = logging.getLogger(__name__)

_FERNET: Fernet | None = None
_FERNET_CHECKED = False


def _get_fernet() -> Fernet | None:
    """lazy-init של Fernet. מחזיר None אם המפתח לא מוגדר."""
    global _FERNET, _FERNET_CHECKED
    if _FERNET_CHECKED:
        return _FERNET
    _FERNET_CHECKED = True
    key = get_settings().secrets_encryption_key
    if not key:
        logger.warning(
            "SECRETS_ENCRYPTION_KEY not set — tokens will be stored in plaintext. "
            "OK for dev, but unsafe in production."
        )
        return None
    try:
        _FERNET = Fernet(key.encode() if isinstance(key, str) else key)
    except (ValueError, TypeError) as e:
        logger.error("Invalid SECRETS_ENCRYPTION_KEY: %s. Falling back to plaintext.", e)
        _FERNET = None
    return _FERNET


def encrypt_secret(plaintext: str) -> str:
    """מצפין מחרוזת. ללא מפתח → מחזיר plaintext עם prefix מסמן."""
    cipher = _get_fernet()
    if cipher is None:
        return "plain:" + plaintext
    return cipher.encrypt(plaintext.encode()).decode()


def decrypt_secret(ciphertext: str) -> str:
    """
    מפענח מחרוזת. תומך ב-prefix 'plain:' כדי לאפשר migration עתידי
    מ-plaintext להצפנה (מי שעלה לפני הפעלת ההצפנה).
    """
    if ciphertext.startswith("plain:"):
        return ciphertext[len("plain:") :]
    cipher = _get_fernet()
    if cipher is None:
        # אין מפתח אבל הtoken מוצפן — סימן ל-misconfig. נכשל בקול
        # רם כדי שלא נסיים עם garbage tokens.
        raise RuntimeError(
            "ciphertext is encrypted but SECRETS_ENCRYPTION_KEY is not set"
        )
    try:
        return cipher.decrypt(ciphertext.encode()).decode()
    except InvalidToken as e:
        raise RuntimeError("Failed to decrypt secret — wrong key?") from e
