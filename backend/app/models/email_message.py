"""
EmailMessage — Spec v2.1 §5.9 + §20.10/13.

מייצג מייל שהתקבל (inbound) או נשלח (outbound) דרך Gmail. נשמר גם הHTML
המקורי (לתצוגה/debug) וגם הטקסט הנקי שנשלח ל-AI (`cleaned_text` —
מנוקה ע"י `clean_email_body_for_ai`).

classification_retry_count מאפשר retry-pattern: AIError על הclassifier
לא יוצר ליד מיד — נשמר ה-row עם count=0, cron מנסה שוב כל דקה. אחרי
`AI_MAX_CLASSIFICATION_RETRIES` כשלים — נוצר ליד עם manual_review_needed=
True (Spec §20.13).
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, desc, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin


# ===== processing_status values =====
# Phase 3 Stage 18 commit 4/4 bugbot fix: בלי הדגל ה-cron לא ידע להבחין
# בין רשומה שצריכה retry של AI לבין רשומה שכבר במצב סופי (spam/not_business
# נשארים עם lead_id=NULL לעולם). הקבועים פה ולא ב-app/constants כי שייכים
# סמנטית רק לטבלה הזו (בניגוד ל-LeadStatus שמשותף ל-API + frontend).
PROCESSING_STATUS_PENDING = "pending"          # cron יסרוק
PROCESSING_STATUS_LEAD_CREATED = "lead_created"  # success — ליד תקני
PROCESSING_STATUS_NOT_BUSINESS = "not_business"  # AI אמר לא-עסקי, יש תווית ב-Gmail
PROCESSING_STATUS_HEURISTIC_SPAM = "heuristic_spam"  # heuristic דילג לפני AI
PROCESSING_STATUS_MANUAL_REVIEW = "manual_review"  # MAX retries → ליד עם manual_review_needed


class EmailMessage(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "email_messages"

    # NULL מותר — מייל שעדיין לא קושר לליד (pending_classification, או
    # שכבר סווג כספאם וקיבל תווית בלבד בלי ליד).
    lead_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("leads.id", ondelete="SET NULL"),
        nullable=True,
    )

    # UNIQUE — אותו gmail_message_id לעולם לא יעובד פעמיים.
    gmail_message_id: Mapped[str | None] = mapped_column(
        String(200), unique=True, nullable=True
    )

    # inbound / outbound. nullable כי outbound (שליחה דרך נועה) עוד לא
    # מטופל ב-Stage 18 — נוסיף ב-Stage 20 אם בכלל.
    direction: Mapped[str | None] = mapped_column(String(20), nullable=True)

    from_address: Mapped[str | None] = mapped_column(String(200), nullable=True)
    to_address: Mapped[str | None] = mapped_column(String(200), nullable=True)
    subject: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ה-HTML הגולמי מ-Gmail API. לתצוגה ב-UI ו-debug.
    raw_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    # מה ששלחנו ל-AI אחרי clean_email_body_for_ai.
    cleaned_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # purpose, ratio, raw_len, cleaned_len, truncated, timestamp.
    cleaning_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # זמן ה-Gmail (`internalDate`), לא זמן ה-webhook (יכול להתעכב דקות).
    received_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Spec §20.13: כשclassifier נכשל ב-AIError, count עולה ב-cron retry.
    # אחרי AI_MAX_CLASSIFICATION_RETRIES (default 10) → ליד עם
    # manual_review_needed=True ועוצרים retry.
    classification_retry_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    # ראה PROCESSING_STATUS_* למעלה. רק רשומות 'pending' נסרקות ע"י
    # ה-cron retry_pending_classification. כל מסלול שמסיים עיבוד
    # (lead_created / not_business / heuristic_spam / manual_review)
    # חייב לעדכן את השדה — אחרת ה-cron יחזור אליהן עד MAX retries.
    processing_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default=PROCESSING_STATUS_PENDING,
        server_default=PROCESSING_STATUS_PENDING,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # מיון לפי תאריך לתצוגה ב-timeline של ליד.
    # שימוש ב-desc("received_at") במקום postgresql_ops={"received_at":
    # "DESC"} — postgresql_ops נועד ל-operator classes (text_pattern_ops
    # וכו'), לא לסדר מיון. גרם ל-Alembic autogenerate לזהות diff מדומה
    # ולנסות drop/recreate בכל ריצה (Alembic issue #1285).
    __table_args__ = (
        Index(
            "idx_email_messages_lead",
            "lead_id",
            desc("received_at"),
        ),
        # partial index — cron query (`processing_status = 'pending'`).
        # מקביל למיגרציה 0020, מאפשר ל-alembic autogenerate לא לזהות diff.
        Index(
            "idx_email_messages_pending",
            "classification_retry_count",
            postgresql_where="processing_status = 'pending'",
        ),
    )
