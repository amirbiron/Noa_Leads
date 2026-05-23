"""
משתמשי המערכת — נועה (owner) ועוזרתה (assistant).
"""

from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.activity import Activity
    from app.models.lead import Lead
    from app.models.task import Task
    from app.models.template import Template


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # owner / assistant
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    # hashing מבוצע ב-passlib (bcrypt) — אין שמירה של plain text
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # chat ID של טלגרם — למשלוח פוש על ליד חדש
    telegram_chat_id: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # relationships — לידים שבבעלות
    owned_leads: Mapped[list["Lead"]] = relationship(
        back_populates="owner",
        foreign_keys="Lead.owner_id",
    )
    performed_activities: Mapped[list["Activity"]] = relationship(
        back_populates="performer",
    )
    assigned_tasks: Mapped[list["Task"]] = relationship(
        back_populates="assignee",
    )
    created_templates: Mapped[list["Template"]] = relationship(
        back_populates="creator",
    )
