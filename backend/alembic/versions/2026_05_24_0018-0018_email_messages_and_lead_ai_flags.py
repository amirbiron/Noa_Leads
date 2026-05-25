"""email_messages table + Lead AI flags (Phase 3 Stage 18 prep).

יוצר טבלת email_messages (Spec §5.9 — F-02) ומוסיף 2 דגלים ל-Lead:
- low_confidence_classification (Spec §20.12) — AI סיווג כעסקי אבל
  confidence נמוך. סימן ויזואלי בכרטיס.
- manual_review_needed (Spec §20.13) — אחרי AI_MAX_CLASSIFICATION_RETRIES
  כישלונות ב-classifier. נועה תעבור ידנית.

email_messages כולל classification_retry_count לעקיבה אחרי retries.
לעומת זאת, lead.pending_classification (מ-0017) הוא דגל סטטוס "ממתין
לסיווג" — מצביע על email_messages row שעדיין לא הגיע ל-final state.

partial indexes על שני הדגלים החדשים — רוב הזמן 0 שורות, scan O(1).

Revision ID: 0018
Revises: 0017
Create Date: 2026-05-24
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0018"
down_revision: Union[str, None] = "0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ===== email_messages (F-02 / Spec §5.9) =====
    op.create_table(
        "email_messages",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "lead_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("leads.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "gmail_message_id",
            sa.String(length=200),
            unique=True,
            nullable=True,
        ),
        sa.Column("direction", sa.String(length=20), nullable=True),
        sa.Column("from_address", sa.String(length=200), nullable=True),
        sa.Column("to_address", sa.String(length=200), nullable=True),
        sa.Column("subject", sa.Text(), nullable=True),
        sa.Column("raw_html", sa.Text(), nullable=True),
        sa.Column("cleaned_text", sa.Text(), nullable=True),
        sa.Column("cleaning_metadata", postgresql.JSONB(), nullable=True),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "classification_retry_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    # שימוש ב-sa.desc(column) במקום sa.text("col DESC") — תואם להגדרת
    # ה-Index ב-model (desc("received_at")), כך ש-alembic autogenerate
    # לא יזהה diff בכל ריצה.
    op.create_index(
        "idx_email_messages_lead",
        "email_messages",
        ["lead_id", sa.desc("received_at")],
    )

    # ===== Lead AI flags (Spec §20.12 + §20.13) =====
    op.add_column(
        "leads",
        sa.Column(
            "low_confidence_classification",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "leads",
        sa.Column(
            "manual_review_needed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    # partial indexes — רוב הזמן 0 שורות, scan O(1) מ-/dashboard לסינון
    # "צריכים בדיקה".
    op.create_index(
        "idx_leads_low_confidence",
        "leads",
        ["low_confidence_classification"],
        postgresql_where=sa.text("low_confidence_classification = true"),
    )
    op.create_index(
        "idx_leads_manual_review",
        "leads",
        ["manual_review_needed"],
        postgresql_where=sa.text("manual_review_needed = true"),
    )


def downgrade() -> None:
    # סדר: indexes לפני columns/tables. דפוס עקבי בכל ה-repo (ראה
    # 0001, 0012 וכו'). drop_index לפני drop_table הוא redundant
    # ב-PostgreSQL (DROP TABLE מסיר אינדקסים אוטומטית) — נשמר לסימטריה
    # עם create_index ב-upgrade, ולשקיפות במעקב מיגרציות. לא יכשל גם
    # אם האינדקס כבר נמחק (alembic מטפל ב-IF EXISTS).
    op.drop_index("idx_leads_manual_review", table_name="leads")
    op.drop_index("idx_leads_low_confidence", table_name="leads")
    op.drop_column("leads", "manual_review_needed")
    op.drop_column("leads", "low_confidence_classification")
    op.drop_index("idx_email_messages_lead", table_name="email_messages")
    op.drop_table("email_messages")
