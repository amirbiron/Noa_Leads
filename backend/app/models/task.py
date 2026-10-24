"""
Task — משימה/פולואפ. מהווה גם תזכורות שמופיעות בדשבורד.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
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
    # קישור אופציונלי ל-booking ספציפי — משמש את post_meeting_cron
    # ל-dedup per-booking (ליד עם 2 פגישות בחלון מקבל 2 משימות נפרדות).
    # SET NULL אם הbooking נמחק — ה-task עצמו עדיין עומד.
    booking_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("bookings.id", ondelete="SET NULL"),
        nullable=True,
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
    # metadata מובנית — למשל המלצת AI ב-dormant_suggestion (§19 D.1):
    # {ai_action, ai_reasoning, ai_generated_at, model_used}. שם attribute
    # task_metadata (לא metadata) כדי לא להתנגש ב-MetaData של SQLAlchemy;
    # עמודת DB בשם "metadata", עקבי עם activities.metadata.
    task_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", JSONB, nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # §17.1 — מונה תזכורות פולואפ שנשלחו עד עכשיו ב-mark_overdue cron.
    # 0 = טרם הוצגה. מוגבל ע"י FollowupRule.repeat_count של ה-rule_key
    # המתאים ל-task.type (live lookup ב-cron, בלי snapshot). ערך מחדל
    # שומר על התנהגות נוכחית של tasks ישנים.
    current_iteration: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
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
