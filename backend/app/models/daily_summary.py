"""
DailySummary — סיכום יומי שמופיע בדשבורד.

לפי Spec §16.3 + Changelog v2.1: "daily_summary לא נשלח לטלגרם אלא
מופיע בדשבורד". cron יומי ב-19:00 מחשב את ה-stats ושומר כאן; ה-
dashboard endpoint שולף את ה-row האחרון.

singleton — אין user_id (נועה היחידה). unique על summary_date מאפשר
upsert בלי כפילויות.
"""

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin


class DailySummary(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "daily_summaries"

    summary_date: Mapped[date] = mapped_column(Date, nullable=False, unique=True)

    new_leads_today: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    tasks_done_today: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    tasks_for_tomorrow: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    urgent_open: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
