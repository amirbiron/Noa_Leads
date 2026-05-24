"""
Routes ל-Google Calendar — OAuth flow + ניהול חיבור.

הפעולות:
- GET /google/status — מצב חיבור (authed)
- GET /google/auth/start — מתחיל OAuth, מחזיר auth_url ל-redirect (authed)
- GET /google/auth/callback — Google מפנה לכאן (public); שומר ומפנה ל-frontend
- POST /google/disconnect — מחיקת החיבור (authed)
"""

from urllib.parse import urlencode

from fastapi import APIRouter, Query, Request
from fastapi.responses import RedirectResponse

from app.api.deps import CurrentUser, DbSession
from app.config import get_settings
from app.core.exceptions import AuthError, ValidationError
from app.schemas.google_calendar import (
    GoogleAuthStartResponse,
    GoogleConnectionStatus,
)
from app.services import google_calendar as gc_service

router = APIRouter(prefix="/google", tags=["google"])


@router.get("/status", response_model=GoogleConnectionStatus)
async def status(db: DbSession, user: CurrentUser) -> GoogleConnectionStatus:
    info = await gc_service.get_status(db)
    return GoogleConnectionStatus(**info)


@router.get("/auth/start", response_model=GoogleAuthStartResponse)
async def auth_start(
    request: Request, user: CurrentUser
) -> GoogleAuthStartResponse:
    """
    יוצר auth URL ושומר state + code_verifier ב-session cookie.
    ה-frontend מקבל את ה-URL ומבצע window.location.href אליו.
    """
    code_verifier = gc_service.generate_code_verifier()
    auth_url, state = gc_service.build_auth_url(code_verifier)
    # SessionMiddleware מסדר את החתימה — בטוח כל עוד SESSION_SECRET_KEY
    # לא נחשף. ה-state וה-verifier נדרשים בקאלבק.
    request.session["google_oauth_state"] = state
    request.session["google_oauth_code_verifier"] = code_verifier
    return GoogleAuthStartResponse(auth_url=auth_url)


@router.get("/auth/callback", include_in_schema=False)
async def auth_callback(
    request: Request,
    db: DbSession,
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
) -> RedirectResponse:
    """
    Google מפנה לכאן עם code+state. אנחנו מחליפים, שומרים, ומפנים חזרה
    ל-frontend עם פרמטר google=connected/error כדי שהUI יציג הודעה.
    """
    frontend = get_settings().frontend_url.rstrip("/")
    redirect_to_settings = f"{frontend}/settings"

    def _redirect_with_error(reason: str) -> RedirectResponse:
        qs = urlencode({"google": "error", "reason": reason})
        return RedirectResponse(f"{redirect_to_settings}?{qs}")

    if error:
        # המשתמשת לחצה "ביטול" או Google דחה
        return _redirect_with_error(error)

    saved_state = request.session.pop("google_oauth_state", None)
    code_verifier = request.session.pop("google_oauth_code_verifier", None)

    if not code or not state or not saved_state or not code_verifier:
        return _redirect_with_error("missing_params")

    if state != saved_state:
        # CSRF protection — state חייב להתאים
        return _redirect_with_error("state_mismatch")

    try:
        await gc_service.exchange_code_and_save(db, code, code_verifier)
    except ValidationError as e:
        return _redirect_with_error(f"validation:{e.user_message}")
    except Exception:
        # לוג פנימי, אבל לא חושפים stack ל-URL
        import logging

        logging.getLogger(__name__).exception("OAuth callback failed")
        return _redirect_with_error("exchange_failed")

    qs = urlencode({"google": "connected"})
    return RedirectResponse(f"{redirect_to_settings}?{qs}")


@router.post("/disconnect", status_code=204)
async def disconnect(db: DbSession, user: CurrentUser) -> None:
    await gc_service.disconnect(db)
