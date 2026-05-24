"""
GoogleCalendarCredentials — singleton table המחזיק tokens של חשבון
Google של נועה. CHECK(id=1) מבטיח שורה אחת בלבד.

ראה: docs/references/google-calendar-blueprint.md סעיף 8.
"""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class GoogleCalendarCredentials(Base):
    __tablename__ = "google_calendar_credentials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    google_account_email: Mapped[str] = mapped_column(String(255), nullable=False)
    calendar_id: Mapped[str] = mapped_column(
        String(255), nullable=False, default="primary"
    )

    # tokens מוצפנים ע"י app.utils.encryption (Fernet)
    refresh_token_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    access_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_expiry: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    timezone: Mapped[str] = mapped_column(
        String(64), nullable=False, default="Asia/Jerusalem"
    )

    # סימני שגיאה מתמשכים — לטיפול חיננים ב-RefreshError
    auth_invalid_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    owner_alert_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint("id = 1", name="ck_google_calendar_credentials_singleton"),
    )
