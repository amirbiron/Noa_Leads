"""
ServiceRate — תעריפי שירות editable, לפי Spec v2.1 §5.10.

Migration 0015 יוצר את הטבלה ומאכלס 10 ערכי ברירת מחדל מ-§15.2. נועה
יכולה לערוך דרך /settings (PATCH). default_price/duration/sessions
nullable כי חלק מהשירותים מסומנים "לבירור".

total_hours ו-hourly_rate לא נשמרים בטבלה — מחושבים ב-API response.
"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ServiceRate(Base):
    __tablename__ = "service_rates"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )

    # ServiceCategory enum value (clinic / workshops / production / digital_course).
    service_category: Mapped[str] = mapped_column(String(50), nullable=False)
    # subtype ייחודי בתוך הקטגוריה (voice_development, lecture_organization וכו').
    service_subtype: Mapped[str] = mapped_column(String(100), nullable=False)
    # תווית עברית להצגה — נשמרת בטבלה כדי לאפשר עריכה.
    label: Mapped[str] = mapped_column(String(200), nullable=False)

    # nullable: שירותים שמסומנים "לבירור" באפיון (production_directing,
    # digital_course) — אין מחיר ברירת מחדל קבוע.
    default_price: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2), nullable=True
    )
    # אורך מפגש בודד בדקות. spec uses minutes (לא hours) כי זה ה-unit
    # שנועה חושבת בו כשמתזמנים פגישות ב-Calendar.
    default_duration_minutes: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    # מספר המפגשים בחבילה. NULL לשירות חד-פעמי שאינו בחבילה קבועה.
    default_sessions_count: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
