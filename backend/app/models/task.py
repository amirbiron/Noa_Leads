"""
Task — משימה/פולואפ. מהווה גם תזכורות שמופיעות בדשבורד.
"""

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.lead import Lead
    from app.models.user import User


class Task(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "tasks"

    lead_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("leads.id", ondelete="CASCADE"),
        nullable=False,
    )
    # סוג המשימה — מתוך TaskType בקבועים
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    assigned_to: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # open / done / canceled / snoozed
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="open", server_default="open"
    )
    snoozed_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # תיוג מקור הכלל שיצר את המשימה (followup rule)
    origin_rule: Mapped[str | None] = mapped_column(String(50), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    lead: Mapped["Lead"] = relationship(back_populates="tasks")
    assignee: Mapped["User | None"] = relationship(back_populates="assigned_tasks")

    __table_args__ = (
        # אינדקס חלקי — רק על משימות פתוחות, ממוין לפי due
        Index(
            "idx_tasks_open",
            "status",
            "due_at",
            postgresql_where="status = 'open'",
        ),
    )
