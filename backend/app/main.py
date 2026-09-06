"""
נקודת כניסה ל-FastAPI.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import admin as admin_routes
from app.api.routes import auth as auth_routes
from app.api.routes import booking_page as booking_routes
from app.api.routes import bookings as bookings_routes
from app.api.routes import dashboard as dashboard_routes
from app.api.routes import followup_rules as followup_rules_routes
from app.api.routes import quick_action_chips as chips_routes
from app.api.routes import google_calendar as google_routes
from app.api.routes import gmail_webhook as gmail_webhook_routes
from app.api.routes import google_gmail as gmail_routes
from app.api.routes import google_webhook as google_webhook_routes
from app.api.routes import intake as intake_routes
from app.api.routes import leads as leads_routes
from app.api.routes import programs as programs_routes
from app.api.routes import settings as settings_routes
from app.api.routes import setup as setup_routes
from app.api.routes import tasks as tasks_routes
from app.api.routes import templates as templates_routes
from app.api.routes import transcription as transcription_routes
from app.api.routes import users as users_routes
from app.config import get_settings
from app.core.exceptions import AppException

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # eager validation: encryption חייב להיות תקין לפני שנותנים traffic.
    # אם SECRETS_ENCRYPTION_KEY חסר/invalid או APP_ENV != "development",
    # זה זורק RuntimeError והservice לא יעלה. בלי זה, deploy "מצליח"
    # ו-OAuth flow ראשון נופל שעות מאוחר יותר עם stack trace שקשה
    # לקריאה. ראה: docs/recurring-bug-patterns.md Pattern 5 Variant 5c.
    from app.utils.encryption import assert_encryption_ready

    assert_encryption_ready()
    yield


# מיפוי שדה → הודעת שגיאה ידידותית. השדה מתועד דרך loc האחרון של
# RequestValidationError (לרוב שם המאפיין ב-payload).
_FIELD_FRIENDLY_MESSAGES: dict[str, str] = {
    "phone": "מספר הטלפון שהוזן לא תקין.",
    "email": "כתובת המייל שהוזנה לא תקינה.",
    "full_name": "שם הליד נדרש.",
    "service_category": "יש לבחור קטגוריית שירות.",
    "service_subtype": "יש לבחור תת-קטגוריית שירות.",
    "source_channel": "יש לבחור מקור פנייה.",
    "preferred_contact": "ערך לא תקין לערוץ קשר מועדף.",
    "priority_level": "ערך לא תקין לרמת עדיפות.",
    "slot_start": "מועד התחלה לא תקין.",
    "slot_end": "מועד סיום לא תקין.",
    "date_from": "תאריך התחלה לא תקין.",
    "date_to": "תאריך סיום לא תקין.",
    "closure_reason": "יש לבחור סיבת סגירה.",
    "target_status": "סטטוס יעד לא תקין.",
}


def _humanize_validation_error(exc: RequestValidationError) -> str:
    """
    מתרגם את ה-error הראשון של Pydantic להודעה ידידותית בעברית.

    אם השדה מוכר ב-_FIELD_FRIENDLY_MESSAGES — מחזיר את ההודעה הספציפית.
    אחרת — הודעה גנרית בלבד. שם השדה הפנימי נשמר ב-log (כלל 3 ב-CLAUDE.md:
    אל תחשוף מידע פנימי ב-API responses).
    """
    errors = exc.errors()
    if not errors:
        return "נתונים לא תקינים."

    first = errors[0]
    loc = first.get("loc", ())
    # מדלגים על "body"/"query"/"path" שמופיע ראשון, ולוקחים את השדה
    field_parts = [str(p) for p in loc if p not in ("body", "query", "path")]
    field = field_parts[-1] if field_parts else ""

    if field in _FIELD_FRIENDLY_MESSAGES:
        return _FIELD_FRIENDLY_MESSAGES[field]
    if field:
        logger.warning(
            "Validation error on unmapped field %r: %s",
            field,
            first.get("msg", ""),
        )
    return "נתונים לא תקינים. בדקי שכל השדות מולאו נכון."


def _register_exception_handlers(app: FastAPI) -> None:
    """
    Handlers שלא חושפים פנימיים (כלל 3 ב-CLAUDE.md):
    - הודעות בעברית, גנריות
    - אין stack traces ב-response
    - שגיאות לא צפויות → 500 גנרי
    """

    @app.exception_handler(AppException)
    async def handle_app_exception(_: Request, exc: AppException) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=exc.to_dict())

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        _: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # תרגום ה-error הראשון להודעה ידידותית בעברית. לפי כלל 3 ב-CLAUDE.md
        # — לא חושפים errors גולמיים של Pydantic (מילים טכניות באנגלית +
        # ה-input המקורי שעלול להכיל מידע רגיש).
        message = _humanize_validation_error(exc)
        return JSONResponse(
            status_code=422,
            content={
                "error": "validation_error",
                "message": message,
            },
        )

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        # log פנימי בלבד — לא חוזר ל-client
        logger.exception("Unhandled exception on %s %s", request.method, request.url)
        return JSONResponse(
            status_code=500,
            content={
                "error": "internal_error",
                "message": "אירעה שגיאה פנימית. נסה שוב מאוחר יותר.",
            },
        )


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Noa Leads CRM",
        version="0.1.0",
        description="מערכת ניהול לידים ולקוחות לנועה",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # אין SessionMiddleware: ב-*.onrender.com כל subdomain הוא site נפרד
    # לפי Public Suffix List, ודפדפנים חוסמים cross-site cookies.
    # ה-OAuth state מקודד ב-JWT חתום שעובר דרך פרמטר state של OAuth עצמו
    # (cookieless flow). ראה: app/services/google_calendar.py.

    _register_exception_handlers(app)

    @app.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "env": settings.app_env}

    # ===== Routers =====
    app.include_router(auth_routes.router)
    app.include_router(leads_routes.router)
    app.include_router(tasks_routes.router)
    app.include_router(templates_routes.router)
    app.include_router(intake_routes.router)
    app.include_router(dashboard_routes.router)
    app.include_router(users_routes.router)
    app.include_router(programs_routes.router)
    app.include_router(settings_routes.router)
    app.include_router(followup_rules_routes.router)
    app.include_router(setup_routes.router)
    app.include_router(chips_routes.router)
    app.include_router(google_routes.router)
    app.include_router(gmail_routes.router)
    app.include_router(google_webhook_routes.router)
    app.include_router(gmail_webhook_routes.router)
    app.include_router(booking_routes.router)
    app.include_router(bookings_routes.router)
    app.include_router(transcription_routes.router)
    app.include_router(admin_routes.router)

    return app


app = create_app()
