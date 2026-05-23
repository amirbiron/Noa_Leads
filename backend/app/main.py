"""
נקודת כניסה ל-FastAPI.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import auth as auth_routes
from app.api.routes import dashboard as dashboard_routes
from app.api.routes import intake as intake_routes
from app.api.routes import leads as leads_routes
from app.api.routes import programs as programs_routes
from app.api.routes import settings as settings_routes
from app.api.routes import tasks as tasks_routes
from app.api.routes import templates as templates_routes
from app.api.routes import users as users_routes
from app.config import get_settings
from app.core.exceptions import AppException

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # מקום עתידי ל-init של חיבורי DB / clients חיצוניים
    yield


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
        # מציגים את errors ב-FastAPI/Pydantic — אלה הודעות על הקלט עצמו,
        # לא על פנים המערכת. אבל מוסיפים מעטפת אחידה בעברית.
        return JSONResponse(
            status_code=422,
            content={
                "error": "validation_error",
                "message": "נתונים לא תקינים.",
                "details": exc.errors(),
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

    return app


app = create_app()
