"""
הגדרות אפליקציה — נטענות מתוך משתני סביבה (.env).
"""

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ===== כללי =====
    app_env: str = "development"
    log_level: str = "INFO"
    timezone: str = "Asia/Jerusalem"

    # ===== Database =====
    database_url: str = "postgresql+asyncpg://user:password@localhost:5432/noa_leads"

    # ===== Auth =====
    jwt_secret_key: str = "change-me"
    jwt_algorithm: str = "HS256"
    jwt_access_token_minutes: int = 30
    jwt_refresh_token_days: int = 14

    # ===== CORS =====
    cors_origins: str = "http://localhost:3000"

    # ===== Telegram =====
    telegram_bot_token: str | None = None
    telegram_owner_chat_id: str | None = None

    # ===== Anthropic =====
    anthropic_api_key: str | None = None

    # ===== Google =====
    google_client_id: str | None = None
    google_client_secret: str | None = None
    google_redirect_uri: str | None = None
    gmail_pubsub_topic: str | None = None

    # מפתח Fernet להצפנת tokens של Google ב-DB. ייצור:
    # `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
    secrets_encryption_key: str | None = None

    # כתובת ה-frontend — נדרשת ל-OAuth callback (חוזרים לדף /settings)
    # ולקישורים בהתראות. דוגמה: https://noa-leads-frontend.onrender.com
    frontend_url: str = "http://localhost:3000"

    # ===== שעות עבודה =====
    work_day_start_hour: int = Field(default=9, ge=0, le=23)
    work_day_end_hour: int = Field(default=18, ge=0, le=23)
    friday_close_hour: int = Field(default=16, ge=0, le=23)

    @property
    def cors_origins_list(self) -> list[str]:
        # פיצול אוריג'ינס מופרדים בפסיק
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @field_validator("database_url", mode="after")
    @classmethod
    def _normalize_database_url(cls, v: str) -> str:
        # Render (ו-Heroku) מחזירים postgresql:// או postgres://,
        # אבל SQLAlchemy האסינכרוני דורש postgresql+asyncpg://.
        # מבצעים נרמול שקוף כדי שלא נצטרך לדאוג לזה ב-runtime.
        if v.startswith("postgresql+"):
            return v  # כבר יש driver מפורש
        if v.startswith("postgresql://"):
            return "postgresql+asyncpg://" + v[len("postgresql://"):]
        if v.startswith("postgres://"):
            return "postgresql+asyncpg://" + v[len("postgres://"):]
        return v


@lru_cache
def get_settings() -> Settings:
    # cache כדי לא לטעון את ה-env בכל קריאה
    return Settings()
