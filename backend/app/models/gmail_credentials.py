"""
GmailCredentials — singleton, מקביל ל-GoogleCalendarCredentials.

טבלה נפרדת מ-google_calendar_credentials (החלטת UX — Phase 3 Stage 17):
scopes שונים, watch lifecycle שונה (Gmail max 7d), failure isolation.

המודל זהה ברובו ל-GoogleCalendarCredentials, עם שינויים:
- history_id במקום sync_token (Gmail API משתמש ב-historyId לסנכרון
  incremental, לא ב-syncToken).
- filter_label_id + filter_label_name_cached — Spec §20.11. ה-cache
  מאפשר זיהוי שינוי AI_FILTER_LABEL_NAME ב-env ועדכון התווית.
"""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class GmailCredentials(Base):
    __tablename__ = "gmail_credentials"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=False
    )
    google_account_email: Mapped[str] = mapped_column(
        String(255), nullable=False
    )

    # tokens מוצפנים ע"י app.utils.encryption (Fernet)
    refresh_token_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    access_token_encrypted: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    token_expiry: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Watch + history-based sync.
    # ב-Gmail, watch() לא מחזירה channel_id — רק historyId + expiration.
    # stop() עוצרת את כל ה-watches של המשתמש (לא דורשת id). watch_expiration
    # IS NOT NULL = יש watch פעיל; הוא ה-marker.
    history_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    watch_expiration: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Label caching (Spec §20.11)
    # filter_label_id — ה-Gmail label.id (נחוץ ל-modify API).
    # filter_label_name_cached — שם בעת היצירה. אם AI_FILTER_LABEL_NAME ב-
    # env השתנה — ensure_filter_label יוצר תווית חדשה.
    filter_label_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )
    filter_label_name_cached: Mapped[str | None] = mapped_column(
        String(200), nullable=True
    )

    # סימני שגיאה מתמשכים
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
        CheckConstraint("id = 1", name="ck_gmail_credentials_singleton"),
    )
