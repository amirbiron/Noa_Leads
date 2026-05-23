"""
תבניות הודעה — וואטסאפ או מייל, עם משתנים שמתמלאים מהליד.
"""

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.user import User


class Template(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "templates"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # whatsapp / email
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    # private / organization / dormant
    target_audience: Mapped[str | None] = mapped_column(String(50), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    # רשימת שמות משתנים מותרים, למשל: ["customer_name", "service_type"]
    variables: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    created_by: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    creator: Mapped["User | None"] = relationship(back_populates="created_templates")
