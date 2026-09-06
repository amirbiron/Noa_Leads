"""
הצפנה סימטרית עם Fernet (cryptography) להגנה על secrets ב-DB —
בעיקר refresh_token של Google OAuth.

קונפיגורציה: SECRETS_ENCRYPTION_KEY ב-env, ערך Fernet key (44 chars
base64 url-safe). ייצור: `python -c "from cryptography.fernet import Fernet;
print(Fernet.generate_key().decode())"`.

**Strict by default (06/2026 hardening):** plaintext fallback מותר *רק*
כש-`APP_ENV == "development"` במפורש. כל ערך אחר — כולל `APP_ENV` חסר,
typo (`"prod"`, `"Production"`), `"staging"`, `"test"` — זורק
RuntimeError. הסיבה: הקוד הקודם הניח ש-`app_env == "production"` הוא
ה-default האמיתי בענן. בפועל, ה-default ב-config.py הוא `"development"`,
ולכן typo או חסר ב-Render = plaintext silent fallback בפרודקשן. עכשיו
ההגנה הפוכה: opt-in מפורש ל-dev fallback, fail-safe לכל השאר.

ראה: docs/recurring-bug-patterns.md Pattern 5 Variant 5c.
"""

import logging

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings

logger = logging.getLogger(__name__)

_FERNET: Fernet | None = None
_FERNET_CHECKED = False

# רק ערך זה מאפשר plaintext fallback. כל הערכים האחרים → raise.
# explicit opt-in: מי שרוצה fallback חייב להוסיף APP_ENV=development במפורש.
_DEV_ENV_VALUE = "development"


def _get_fernet() -> Fernet | None:
    """
    lazy-init של Fernet. מחזיר None *רק* כש-`APP_ENV == "development"`
    במפורש. כל ערך אחר (כולל missing, typo, "staging", "prod") → raise.

    הסיבה: ה-default של `app_env` ב-config.py הוא "development". אם מתאם
    שוכח להוסיף `APP_ENV=production` ל-cron service ב-Render, ה-cron
    יקבל "development" → fallback → tokens נכתבים כ-plaintext בשקט.
    כעת ה-default האפליקטיבי הוא strict, ומישהו חייב לבחור dev במפורש.

    חשוב: _FERNET_CHECKED מסומן True רק במסלולי החזרת ערך, לא במסלולי
    raise. אחרת באג שקט: קריאה ראשונה זורקת RuntimeError, השנייה רואה
    _FERNET_CHECKED=True ומחזירה _FERNET=None — encrypt_secret נופל
    ל-"plain:" prefix ושומר refresh_token של Google כplaintext ב-DB.
    """
    global _FERNET, _FERNET_CHECKED
    if _FERNET_CHECKED:
        return _FERNET

    settings = get_settings()
    key = settings.secrets_encryption_key

    if not key:
        msg = (
            "SECRETS_ENCRYPTION_KEY not set. Generate with: "
            "python -c \"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\""
        )
        # strict by default — fallback רק עם APP_ENV=development מפורש.
        if settings.app_env != _DEV_ENV_VALUE:
            # raise לפני סימון checked — קריאות הבאות יזרקו שוב, לא יחזירו None.
            raise RuntimeError(
                f"{msg} — required when APP_ENV={settings.app_env!r}. "
                f"Plaintext fallback is only allowed with APP_ENV={_DEV_ENV_VALUE!r} "
                "(explicit opt-in). Set SECRETS_ENCRYPTION_KEY or change APP_ENV."
            )
        logger.warning(
            "%s Falling back to plaintext (APP_ENV=development opt-in only).",
            msg,
        )
        _FERNET_CHECKED = True
        return None

    try:
        _FERNET = Fernet(key.encode() if isinstance(key, str) else key)
    except (ValueError, TypeError) as e:
        msg = (
            f"Invalid SECRETS_ENCRYPTION_KEY: {e}. Must be a valid Fernet key "
            "(32 bytes URL-safe base64, 44 chars). Re-generate with: "
            "python -c \"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\""
        )
        # אותו עיקרון של strict by default — invalid key הוא משחית כמו
        # missing, וגם רק dev מורשה fallback.
        if settings.app_env != _DEV_ENV_VALUE:
            # raise בלי לסמן checked.
            raise RuntimeError(msg) from e
        logger.error("%s Falling back to plaintext (development only).", msg)
        _FERNET = None

    _FERNET_CHECKED = True
    return _FERNET


def assert_encryption_ready() -> None:
    """eager validation — נכשל מיד בstartup אם encryption לא תקין.

    משמש ב-`main.py` (lifespan של FastAPI) וב-`jobs/_runner.py` כדי
    שכל service יתחיל עם בדיקה מפורשת, במקום lazy-init בקריאה ראשונה
    ל-decrypt. cron שאמור לקרוא tokens אחרי 10 דקות, לא צריך לחכות
    עד שמגיע לקריאה כדי להבין שאין מפתח.

    זה משלים את ה-`_get_fernet` strict-by-default: גם המהפך של הלוגיקה
    *וגם* eager — defense in depth.
    """
    _get_fernet()


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
