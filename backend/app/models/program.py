"""
Program — תוכנית מתמשכת ללקוח (שיקום קול 8 מפגשים, ליווי הפקה 3 חודשים וכו').
מאפשר חישוב רווחיות אמיתי: ש"ח/שעה אפקטיבי מול שעות בפועל.
"""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.lead import Lead


class Program(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "programs"

    lead_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("leads.id", ondelete="CASCADE"),
        nullable=False,
    )
    # voice_rehab_8 / stage_arts_4 / production_3months / digital_course_12
    program_type: Mapped[str] = mapped_column(String(50), nullable=False)
    total_sessions: Mapped[int] = mapped_column(Integer, nullable=False)
    completed_sessions: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    total_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    # שעות בפועל — נועה ממלאת אחרי כל מפגש; משמש לחישוב רווחיות
    actual_hours: Mapped[Decimal] = mapped_column(
        Numeric(6, 2), nullable=False, default=0, server_default="0"
    )

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    estimated_end_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # active / completed / canceled
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active", server_default="active"
    )

    lead: Mapped["Lead"] = relationship(back_populates="programs")
