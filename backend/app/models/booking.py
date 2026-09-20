"""
Booking — פגישה שהליד קבע בדף הציבורי.

עד מיגרציה 0032 זו הייתה *בקשה* שהמתינה לאישור נועה. מאז — הפגישה
נקבעת ומאושרת מיד (`status='approved'`), והאירוע נוצר ביומן באותה
טרנזקציה. הסטטוס `pending_approval` נשאר ב-enum כדי שנוכל להציג ולבטל
שורות שנוצרו לפני השינוי; המערכת לא מייצרת אותו יותר.
"""

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.lead import Lead


class Booking(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "bookings"

    lead_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("leads.id", ondelete="CASCADE"),
        nullable=False,
    )
    requested_slot_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    requested_slot_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    # pending_approval / approved / rejected / canceled
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="pending_approval",
        server_default="pending_approval",
    )
    # נשמר כדי לאפשר סנכרון דו-כיווני בעתיד
    google_calendar_event_id: Mapped[str | None] = mapped_column(
        String(200), nullable=True
    )

    # === פרטים שהליד מזין בדף קביעת הפגישה (מיגרציה 0032) ===
    # טלפון ליצירת קשר — חובה בדף הציבורי, nullable ב-DB כי לשורות
    # שנוצרו לפני השינוי אין אותו. 32 ולא 20 כמו `leads.phone`: מספר
    # שאינו ישראלי עובר as-is ב-`app/utils/phone.py` ויכול לחרוג מ-20,
    # וכאן זה שדה חובה בדף ציבורי — חריגה הייתה מוצגת ללקוח כ-500.
    contact_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # הערה חופשית מהליד. נכנסת לתיאור האירוע ביומן (עם escape).
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # היומן שבו האירוע נוצר. ראה ההערה במיגרציה 0032 — מחיקה לפי יומן
    # היעד ה*נוכחי* שוברת ביטול של פגישה שנוצרה לפני החלפת יומן.
    google_calendar_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    rejected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    lead: Mapped["Lead"] = relationship(back_populates="bookings")

    # ה-constraint הזה נוצר במיגרציה 0006 ולא היה משוקף כאן. בלי השיקוף,
    # DB טרי שנבנה מה-metadata (CI / dev / prod חדש) מקבל schema שונה
    # מ-prod הממוגרר, ו-`alembic autogenerate` היה מציע למחוק אותו.
    #
    # מה הוא עושה: אוסר על שתי פגישות *פעילות* לחפוף בזמן — גם בין לידים
    # שונים. זו ההגנה היחידה שנשארה אחרי שמיגרציה 0032 הסירה את
    # `idx_bookings_active_lead` (שאסר יותר מפגישה פעילה אחת לאותו ליד),
    # והיא עדיין נכונה: נועה לא יכולה להיות בשתי פגישות באותו זמן.
    # דורש את ה-extension btree_gist, שנטען במיגרציה 0006.
    __table_args__ = (
        ExcludeConstraint(
            (
                text(
                    "tstzrange(requested_slot_start, requested_slot_end, '[)')"
                ),
                "&&",
            ),
            name="ck_bookings_no_overlap",
            using="gist",
            where=text("status IN ('pending_approval', 'approved')"),
        ),
    )
