"""
Routes ל-Google Calendar — OAuth flow + ניהול חיבור.

הפעולות:
- GET /google/status — מצב חיבור (Owner only)
- GET /google/auth/start — מתחיל OAuth, מחזיר auth_url ל-redirect (Owner only)
- GET /google/auth/callback — Google מפנה לכאן (public); שומר ומפנה ל-frontend
- POST /google/disconnect — מחיקת החיבור (Owner only)

הflow חסר cookies (state-as-JWT). ראה: app/services/google_calendar.py.
"""

import logging
from urllib.parse import urlencode

from fastapi import APIRouter, Query
from fastapi.responses import RedirectResponse

from app.api.deps import DbSession, OwnerOnly
from app.config import get_settings
from app.core.exceptions import ValidationError
from app.schemas.google_calendar import (
    GoogleAuthStartResponse,
    GoogleConnectionStatus,
)
from app.services import google_calendar as gc_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/google", tags=["google"])

# allowlist של error codes מ-OAuth — מומרים לקודים שלנו שה-frontend
# יכול להציג בצורה ידידותית. כל ערך אחר → "unknown_error" כדי לא להעביר
# מחרוזות חופשיות מה-provider אל ה-URL הציבורי.
_OAUTH_ERROR_REASONS: dict[str, str] = {
    "access_denied": "consent_denied",
    "invalid_request": "invalid_request",
    "invalid_scope": "invalid_scope",
    "temporarily_unavailable": "provider_unavailable",
    "server_error": "provider_error",
    "unauthorized_client": "unauthorized_client",
    "unsupported_response_type": "unsupported_response_type",
    "interaction_required": "interaction_required",
    "login_required": "login_required",
    "consent_required": "consent_required",
}


def _map_oauth_error(error: str) -> str:
    return _OAUTH_ERROR_REASONS.get(error, "unknown_error")


@router.get("/status", response_model=GoogleConnectionStatus)
async def status(db: DbSession, user: OwnerOnly) -> GoogleConnectionStatus:
    info = await gc_service.get_status(db)
    return GoogleConnectionStatus(**info)


@router.get("/auth/start", response_model=GoogleAuthStartResponse)
async def auth_start(user: OwnerOnly) -> GoogleAuthStartResponse:
    """
    יוצר auth URL. ה-code_verifier מקודד ב-state כ-JWT חתום — אין
    תלות ב-cookies (חיוני ב-Render שבו frontend/backend הם cross-site
    לפי Public Suffix List, ודפדפנים חוסמים cross-site cookies).
    """
    code_verifier = gc_service.generate_code_verifier()
    auth_url = gc_service.build_auth_url(code_verifier)
    return GoogleAuthStartResponse(auth_url=auth_url)


@router.get("/auth/callback", include_in_schema=False)
async def auth_callback(
    db: DbSession,
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
) -> RedirectResponse:
    """
    Google מפנה לכאן עם code+state. מפענחים state (JWT חתום), מוציאים
    את code_verifier, מבצעים exchange, ומפנים חזרה ל-frontend.
    """
    frontend = get_settings().frontend_url.rstrip("/")
    redirect_to_settings = f"{frontend}/settings"

    def _redirect_with_error(reason: str) -> RedirectResponse:
        qs = urlencode({"google": "error", "reason": reason})
        return RedirectResponse(f"{redirect_to_settings}?{qs}")

    if error:
        # המשתמשת לחצה "ביטול" או Google דחה. ממירים לקוד מ-allowlist
        # ומלוגגים את הערך הגולמי לdebug — לא חושפים אותו ב-URL.
        logger.info("OAuth callback returned error: %s", error)
        return _redirect_with_error(_map_oauth_error(error))

    if not code or not state:
        return _redirect_with_error("missing_params")

    try:
        code_verifier = gc_service.decode_oauth_state(state)
    except ValidationError:
        # state פג תוקף או נחתם בכזב
        return _redirect_with_error("state_invalid")

    try:
        await gc_service.exchange_code_and_save(db, code, code_verifier)
    except ValidationError as e:
        return _redirect_with_error(f"validation:{e.user_message}")
    except Exception:
        logger.exception("OAuth callback failed")
        return _redirect_with_error("exchange_failed")

    qs = urlencode({"google": "connected"})
    return RedirectResponse(f"{redirect_to_settings}?{qs}")


@router.post("/disconnect", status_code=204)
async def disconnect(db: DbSession, user: OwnerOnly) -> None:
    await gc_service.disconnect(db)
