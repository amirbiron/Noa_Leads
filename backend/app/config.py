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
    # Phase 3 Stage 16: model resolution. defaults לפי spec §19.1.
    # ה-overrides per use case nullable — אם None יורש מ-FAST/QUALITY.
    # שינוי מודל בעתיד = env var ב-Render, בלי deploy.
    ai_model_fast: str = "claude-haiku-4-5"
    ai_model_quality: str = "claude-sonnet-4-6"
    ai_model_email_classifier: str | None = None
    ai_model_daily_summary: str | None = None
    ai_model_proposal_draft: str | None = None
    ai_model_dormant_detection: str | None = None
    # Spec §20.11: תווית Gmail למיילים שסוננו ע"י AI כספאם.
    # שינוי אינו retroactive — ראה admin note ב-§20.11.
    ai_filter_label_name: str = "סוננו אוטומטית"
    # Spec §20.12: סף בטחון. מתחת לזה — ליד מסומן low_confidence_classification.
    ai_classify_confidence_threshold: float = 0.7
    # Spec §20.13: כמה פעמים cron retry_pending_classification ינסה לפני
    # יצירת ליד עם manual_review_needed=True. שמרני (10 דקות לAPI להתאושש).
    ai_max_classification_retries: int = 10

    # ===== Google =====
    google_client_id: str | None = None
    google_client_secret: str | None = None
    google_redirect_uri: str | None = None
    # Phase 3 Stage 17: redirect_uri נפרד ל-Gmail OAuth (scope אחר →
    # callback אחר). נדרש לרשום ב-Google Cloud Console.
    gmail_redirect_uri: str | None = None
    gmail_pubsub_topic: str | None = None
    # אופציונלי: service account email שחתום על ה-OIDC token של Pub/Sub
    # Push (Phase 3 Stage 18 commit 4/4). אם מוגדר, ה-webhook יאמת
    # שה-token חתום ע"י ה-SA הספציפי. אם None — רק חתימת Google תיאמת.
    gmail_pubsub_service_account: str | None = None

    # מפתח Fernet להצפנת tokens של Google ב-DB. ייצור:
    # `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
    secrets_encryption_key: str | None = None

    # כתובת ה-frontend — נדרשת ל-OAuth callback (חוזרים לדף /settings)
    # ולקישורים בהתראות. דוגמה: https://noa-leads-frontend.onrender.com
    frontend_url: str = "http://localhost:3000"

    # כתובת ציבורית של ה-backend — נדרשת ל-Google Calendar webhooks.
    # Google דורש HTTPS וURL ציבורי לpush notifications. דוגמה:
    # https://noa-leads-backend.onrender.com. ב-dev: ngrok או דומה.
    # אם None — watch channel לא ייווצר (סנכרון הפוך כבוי).
    backend_url: str | None = None

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
