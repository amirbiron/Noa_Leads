"""
WeeklyOpenStateSnapshot — צילום קבוע של שדות "מצב פתוח בסוף השבוע".

מקביל ל-`DailySummary` (F-26 / F-07): cron כותב row אחד פר-שבוע ב-
ראשון 00:00 שעון ישראל (נקודה מתה אחרי מוצ"ש, לפני התעוררות ראשון),
ו-`build_weekly_user_prompt` שולף ממנו במקום לשחזר from-mutable-fields.

הסיבה הארכיטקטונית (סוגר 7 ממצאי cursor bugbot מתמשכים): שחזור עבר
מתוך שדות הווה (`Lead.status`, `Task.due_at` שנדרס ב-snooze, `Lead.closed_at`
שמתאפס ב-reopen) הוא מטבעו לא אמין. צילום ברגע הנכון פותר את כל
הגרסאות של הבעיה.

singleton — אין user_id (נועה היחידה). UNIQUE על `week_end_date` מאפשר
first-write-wins (`ON CONFLICT DO NOTHING`) — re-run של ה-cron באותו
שבוע לא דורס.
"""

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin


class WeeklyOpenStateSnapshot(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "weekly_open_state_snapshots"

    # שבת של השבוע שהסתיים, בישראל. UNIQUE → idempotency של ה-cron.
    week_end_date: Mapped[date] = mapped_column(Date, nullable=False, unique=True)

    open_leads_total: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    stuck_leads_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    stale_proposals_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    overdue_tasks_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    dormant_with_recommendation_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
