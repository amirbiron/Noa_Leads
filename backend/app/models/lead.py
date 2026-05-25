"""
ליד — הישות המרכזית של המערכת.
"""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Index, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import DateTime

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.activity import Activity
    from app.models.booking import Booking
    from app.models.program import Program
    from app.models.task import Task
    from app.models.user import User


class Lead(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "leads"

    # ===== זיהוי בסיסי =====
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    organization_name: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # ===== קטגוריזציה =====
    # nullable לפי Spec §7.1: שדות חובה הם רק שם/טלפון/מקור. service_category
    # מסווג אחר כך מהכרטיס (ידנית או ע"י AI בפאזה 3). ראה F-04 ב-spec-deviations.
    # clinic / workshops / production / digital_course
    service_category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # voice_development / public_speaking / וכו'
    service_subtype: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # ===== מצב =====
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="NEW", server_default="NEW"
    )
    # VARCHAR(30) לפי Spec §5.1 — מספיק ל-ASSISTANT_PENDING_NOAH (22 תווים).
    waiting_on: Mapped[str] = mapped_column(
        String(30), nullable=False, default="NOAH", server_default="NOAH"
    )
    priority_level: Mapped[str] = mapped_column(
        String(20), nullable=False, default="normal", server_default="normal"
    )
    preferred_contact: Mapped[str] = mapped_column(
        String(20), nullable=False, default="whatsapp", server_default="whatsapp"
    )

    # ===== בעלות =====
    owner_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # ===== צעד הבא =====
    next_action_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    next_action_due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    needs_attention: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # Phase 3 Stage 16: True כשclassifier כשל ב-RateLimitError וצריך retry.
    # retry_pending_classification cron (Stage 18) יסרוק WHERE pending=true.
    pending_classification: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    # ===== מקור =====
    # form / email / manual / referral / facebook / וכו'
    source_channel: Mapped[str] = mapped_column(String(50), nullable=False)
    source_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    utm_source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    utm_campaign: Mapped[str | None] = mapped_column(String(100), nullable=True)
    utm_content: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # ===== היסטוריה =====
    last_inbound_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_outbound_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_activity_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # עד מתי הליד "חם" בעקבות תגובה — קופץ לראש הדשבורד
    reply_boost_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # תאריך שליחת ההצעה — שדה ייעודי כדי שפולואפ על הצעה לא יאפס את הגיל.
    # last_outbound_at משתנה בכל פעולת outbound (פולואפ, תבנית), אבל
    # proposal_sent_at נשמר עד שהליד נסגר או הצעה חדשה נשלחת.
    proposal_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ===== דגלים =====
    dormant_flag: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    is_duplicate_suspected: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    is_returning_customer: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    # ===== סגירה =====
    closure_reason: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # מתמלא ע"י close_lead כשהסטטוס עובר ל-WON/LOST/ARCHIVED
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ===== כלכלת עסקה (לחישוב רווחיות) =====
    # ערך כספי של ה-deal — נמלא בעת סגירה כ-WON.
    # תוכניות מתמשכות עם total_price/actual_hours מנהלות זאת בנפרד דרך Program.
    closed_value: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2), nullable=True
    )
    actual_hours: Mapped[Decimal | None] = mapped_column(
        Numeric(6, 2), nullable=True
    )

    # ===== הערה אישית =====
    personal_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ===== Booking page token =====
    # UUID אקראי שמייצג את הליד בדף קביעת תור ציבורי (/book/{token}).
    # נשלח ידנית ע"י נועה ב-WhatsApp/מייל. unique כדי שלא יקרסו 2 לידים
    # על אותו URL.
    booking_token: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=False,
        unique=True,
        server_default=func.gen_random_uuid(),
    )

    # ===== relationships =====
    owner: Mapped["User | None"] = relationship(
        back_populates="owned_leads",
        foreign_keys=[owner_id],
    )
    activities: Mapped[list["Activity"]] = relationship(
        back_populates="lead",
        cascade="all, delete-orphan",
        order_by="desc(Activity.created_at)",
    )
    tasks: Mapped[list["Task"]] = relationship(
        back_populates="lead",
        cascade="all, delete-orphan",
    )
    bookings: Mapped[list["Booking"]] = relationship(
        back_populates="lead",
    )
    programs: Mapped[list["Program"]] = relationship(
        back_populates="lead",
    )

    __table_args__ = (
        Index("idx_leads_status", "status"),
        Index("idx_leads_owner", "owner_id"),
        # אינדקס חלקי — רק על לידים שדורשים תשומת לב
        Index(
            "idx_leads_needs_attention",
            "needs_attention",
            postgresql_where="needs_attention = TRUE",
        ),
        # אינדקס חלקי — רק על לידים פתוחים, לפי תאריך הפעולה הבאה
        Index(
            "idx_leads_next_action",
            "next_action_due_at",
            postgresql_where="status NOT IN ('WON', 'LOST', 'ARCHIVED')",
        ),
        # Phase 3 Stage 16 — partial index לcron retry_pending_classification.
        # רוב הזמן 0 שורות, scan O(1). מוצהר ב-model + ב-migration 0017.
        Index(
            "idx_leads_pending_classification",
            "pending_classification",
            postgresql_where="pending_classification = TRUE",
        ),
    )
