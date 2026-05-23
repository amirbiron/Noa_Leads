"""
Booking — בקשת תור מליד שתמתין לאישור נועה.
פאזה 1: מבנה ה-DB מוכן. הסנכרון ל-Google Calendar בפאזה 2.
"""

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.lead import Lead


class Booking(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "bookings"

    lead_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("leads.id", ondelete="CASCADE"),
        nullable=False,
    )
    requested_slot_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    requested_slot_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    # pending_approval / approved / rejected / canceled
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="pending_approval",
        server_default="pending_approval",
    )
    # נשמר כדי לאפשר סנכרון דו-כיווני בעתיד
    google_calendar_event_id: Mapped[str | None] = mapped_column(
        String(200), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    rejected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    lead: Mapped["Lead"] = relationship(back_populates="bookings")
