"""
נקודת כניסה ל-FastAPI.
בשלב 0 — שלד בלבד עם health check. הראוטרים האמיתיים נוספים בשלבים הבאים.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    # מקום עתידי ל-init של חיבורי DB / clients חיצוניים
    yield


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

    @app.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "env": settings.app_env}

    return app


app = create_app()
