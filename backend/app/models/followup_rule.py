"""FollowupRule — singleton-per-rule_key. הגדרות פולואפ של נועה (§17.1).

5 שורות seeded ב-migration, אחת לכל כלל פולואפ (first_response,
warm_followup, proposal_followup, dormant_check, lecture_inquiry).
אין הוספה/מחיקה דרך ה-API — הכללים מחוברים ל-TaskType בקוד. רק עריכה.

`rule_key` = TaskType value → lookup ישיר מקוד יצירת ה-task בסבב 2.

ערכי זמן ב-2 שדות: value (int) + unit ('hours' / 'days') — UX-friendly,
ביחידה הטבעית של הכלל לפי §17.1. הקוד יחשב seconds כשצריך.

`repeat_count` כולל את הראשונה. ברירת מחדל 1 = התנהגות נוכחית (התראה
בודדת, בלי חזרות). `repeat_interval_*` משמש רק כש-repeat_count > 1.
"""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class FollowupRule(Base):
    __tablename__ = "followup_rules"

    # PK טבעי = TaskType value. 50 chars תואם לעמודת type ב-tasks.
    rule_key: Mapped[str] = mapped_column(String(50), primary_key=True)

    # זמן עד ההתראה הראשונה, ביחידה הטבעית של הכלל.
    interval_value: Mapped[int] = mapped_column(Integer, nullable=False)
    interval_unit: Mapped[str] = mapped_column(String(10), nullable=False)

    # תזכורת חוזרת. default 1 שומר על התנהגות נוכחית של המערכת.
    repeat_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    repeat_interval_value: Mapped[int] = mapped_column(
        Integer, nullable=False, default=24, server_default="24"
    )
    repeat_interval_unit: Mapped[str] = mapped_column(
        String(10), nullable=False, default="hours", server_default="hours"
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "interval_unit IN ('hours', 'days')",
            name="ck_followup_rules_interval_unit",
        ),
        CheckConstraint(
            "repeat_interval_unit IN ('hours', 'days')",
            name="ck_followup_rules_repeat_interval_unit",
        ),
        CheckConstraint(
            "repeat_count >= 1", name="ck_followup_rules_repeat_count_min"
        ),
        CheckConstraint(
            "interval_value > 0",
            name="ck_followup_rules_interval_positive",
        ),
        CheckConstraint(
            "repeat_interval_value > 0",
            name="ck_followup_rules_repeat_interval_positive",
        ),
    )
