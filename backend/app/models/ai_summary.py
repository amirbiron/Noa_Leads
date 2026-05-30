"""
AiSummary — סיכום AI נרטיבי (C.1 יומי / C.2 שבועי, §6.5).

שכבה נרטיבית חדשה שחיה *לצד* daily_summaries הסטטיסטי (לא מחליפה אותו):
- daily_summaries = ספירות יבשות (snapshot ל-bubble בדשבורד, F-07).
- ai_summaries = הפלט הנרטיבי של Claude (bottom_line/today/highlights/...).

input_data = ה-user_prompt המבושל ששלחנו ל-AI; output = ה-result כ-JSON.
unique על (type, date_range_start, date_range_end) → first-write-wins: ריצה
חוזרת באותו טווח לא יוצרת כפילות ולא דורסת את inaccurate_count של נועה.

PK מסוג UUID (כמו שאר הפרויקט) ולא SERIAL כפי שב-SQL הדוגמתי של §6.5 —
עקביות פנימית עם UUIDPrimaryKeyMixin מנצחת את הדוגמה.
"""

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin


class AiSummary(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "ai_summaries"

    # 'daily' / 'weekly' — מ-SummaryType (כלל 11: ערך מ-enum, לא hardcoded).
    type: Mapped[str] = mapped_column(String(10), nullable=False)
    # טווח הסיכום: ליומי start=end=אותו יום; לשבועי ראשון→שבת (inclusive).
    date_range_start: Mapped[date] = mapped_column(Date, nullable=False)
    date_range_end: Mapped[date] = mapped_column(Date, nullable=False)
    # מה ששלחנו ל-AI (ה-user prompt המבושל) — לדיבוג ושחזור.
    input_data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # מה שחזר מ-AI (result.model_dump()) — מקור התצוגה בדשבורד.
    output: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # counter של כפתור "לא מדויק" (§3.7) — ה-endpoint שמעלה אותו בסבב ו'.
    inaccurate_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    model_used: Mapped[str] = mapped_column(String(50), nullable=False)
    tokens_in: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_out: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # סומן true אם ולידציית-השמות (§6.6#3) לא עברה גם אחרי regen — דגל לבדיקה.
    validation_warning: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "type",
            "date_range_start",
            "date_range_end",
            name="uq_ai_summaries_type_range",
        ),
    )
