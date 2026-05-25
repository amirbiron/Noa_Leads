"""
Routes ל-Gmail integration — OAuth flow + ניהול חיבור (Phase 3 Stage 17).

מקביל ל-google_calendar.py אבל עם prefix נפרד (/google-gmail) ו-redirect URI
נפרד (GMAIL_REDIRECT_URI). Google Cloud Console חייב לכלול את שני ה-URIs.

הפעולות:
- GET /google-gmail/status (owner) — מצב חיבור
- GET /google-gmail/auth/start (owner) — מתחיל OAuth, מחזיר auth_url
- GET /google-gmail/auth/callback (public) — Google מפנה לכאן; שומר ומפנה ל-frontend
- POST /google-gmail/disconnect (owner)

ה-cookieless state flow (JWT) משותף עם Calendar — ראה google_calendar.encode_oauth_state.
"""

import logging
from urllib.parse import urlencode

from fastapi import APIRouter, Query
from fastapi.responses import RedirectResponse

from app.api.deps import DbSession, OwnerOnly
from app.config import get_settings
from app.core.exceptions import ValidationError
from app.schemas.google_gmail import (
    GmailAuthStartResponse,
    GmailConnectionStatus,
)
from app.services import gmail as gmail_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/google-gmail", tags=["gmail"])


# שכפול מהקובץ google_calendar.py — allowlist של error codes. שיתוף ב-shared
# module אופציה לעתיד; כרגע המינימליזם עדיף.
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


@router.get("/status", response_model=GmailConnectionStatus)
async def status(db: DbSession, user: OwnerOnly) -> GmailConnectionStatus:
    info = await gmail_service.get_status(db)
    return GmailConnectionStatus(**info)


@router.get("/auth/start", response_model=GmailAuthStartResponse)
async def auth_start(user: OwnerOnly) -> GmailAuthStartResponse:
    """
    יוצר auth URL ל-Gmail (scopes: readonly + modify). state=JWT חתום
    (cookieless flow — משותף עם Calendar).
    """
    code_verifier = gmail_service.generate_code_verifier()
    auth_url = gmail_service.build_auth_url(code_verifier)
    return GmailAuthStartResponse(auth_url=auth_url)


@router.get("/auth/callback", include_in_schema=False)
async def auth_callback(
    db: DbSession,
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
) -> RedirectResponse:
    """Google מפנה לכאן עם code+state. exchange ואחר כך redirect ל-frontend."""
    frontend = get_settings().frontend_url.rstrip("/")
    redirect_to_settings = f"{frontend}/settings"

    def _redirect_with_error(reason: str) -> RedirectResponse:
        qs = urlencode({"gmail": "error", "reason": reason})
        return RedirectResponse(f"{redirect_to_settings}?{qs}")

    if error:
        logger.info("Gmail OAuth callback returned error: %s", error)
        return _redirect_with_error(_map_oauth_error(error))

    if not code or not state:
        return _redirect_with_error("missing_params")

    try:
        code_verifier = gmail_service.decode_oauth_state(state)
    except ValidationError:
        return _redirect_with_error("state_invalid")

    try:
        await gmail_service.exchange_code_and_save(db, code, code_verifier)
    except ValidationError as e:
        return _redirect_with_error(f"validation:{e.user_message}")
    except Exception:
        logger.exception("Gmail OAuth callback failed")
        return _redirect_with_error("exchange_failed")

    qs = urlencode({"gmail": "connected"})
    return RedirectResponse(f"{redirect_to_settings}?{qs}")


@router.post("/disconnect", status_code=204)
async def disconnect(db: DbSession, user: OwnerOnly) -> None:
    await gmail_service.disconnect(db)
