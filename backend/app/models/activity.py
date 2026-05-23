"""
Activity — לוג היסטורי של כל פעולה על ליד (audit trail).
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.lead import Lead
    from app.models.user import User


class Activity(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "activities"

    lead_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("leads.id", ondelete="CASCADE"),
        nullable=False,
    )
    # סוג הפעולה — מתוך ActivityType בקבועים
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    performed_by: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    # תוכן חופשי — למשל סיכום שיחה או הערה
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    # מטא-דאטה מובנית — לדוגמה {"template_id": "...", "old_status": "NEW"}
    activity_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", JSONB, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    lead: Mapped["Lead"] = relationship(back_populates="activities")
    performer: Mapped["User | None"] = relationship(back_populates="performed_activities")

    __table_args__ = (
        # אינדקס מורכב — שליפת timeline של ליד לפי סדר יורד
        Index("idx_activities_lead", "lead_id", "created_at"),
    )
