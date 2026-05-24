"""
QuickActionChip — צ'יפים editable לסיכום שיחה מהיר.

לפי האפיון ח: 6 צ'יפים כברירת מחדל. נועה יכולה לערוך/להוסיף/למחוק
דרך הגדרות. כל צ'יפ: שם, action_type (מתוך state_machine.ACTIONS),
requires_content (לצ'יפים שדורשים טקסט חופשי כמו "הוסיפי הערה").
"""

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class QuickActionChip(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "quick_action_chips"

    # טקסט שמופיע ל-נועה (ניתן לערוך)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    # ה-action_type שמופעל ב-backend. חייב להתאים למפתח ב-state_machine.ACTIONS.
    action_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # True לצ'יפים שדורשים טקסט חופשי לפני שליחה (כמו add_internal_note).
    requires_content: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # סדר תצוגה — נמוך מופיע ראשון.
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
