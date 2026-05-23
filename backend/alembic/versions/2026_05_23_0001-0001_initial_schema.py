"""initial schema — כל טבלאות פאזה 1

Revision ID: 0001
Revises:
Create Date: 2026-05-23

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ===== users =====
    op.create_table(
        "users",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("email", sa.String(200), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=True),
        sa.Column("telegram_chat_id", sa.String(50), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # ===== leads =====
    op.create_table(
        "leads",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        # זיהוי בסיסי
        sa.Column("full_name", sa.String(200), nullable=False),
        sa.Column("phone", sa.String(20), nullable=True),
        sa.Column("email", sa.String(200), nullable=True),
        sa.Column("organization_name", sa.String(200), nullable=True),
        # קטגוריזציה
        sa.Column("service_category", sa.String(50), nullable=False),
        sa.Column("service_subtype", sa.String(100), nullable=True),
        # מצב
        sa.Column("status", sa.String(30), nullable=False, server_default="NEW"),
        sa.Column("waiting_on", sa.String(20), nullable=False, server_default="NOAH"),
        sa.Column(
            "priority_level", sa.String(20), nullable=False, server_default="normal"
        ),
        sa.Column(
            "preferred_contact", sa.String(20), nullable=False, server_default="whatsapp"
        ),
        # בעלות
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        # צעד הבא
        sa.Column("next_action_type", sa.String(50), nullable=True),
        sa.Column("next_action_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "needs_attention", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        # מקור
        sa.Column("source_channel", sa.String(50), nullable=False),
        sa.Column("source_detail", sa.Text(), nullable=True),
        sa.Column("utm_source", sa.String(100), nullable=True),
        sa.Column("utm_campaign", sa.String(100), nullable=True),
        sa.Column("utm_content", sa.String(100), nullable=True),
        # היסטוריה
        sa.Column("last_inbound_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_outbound_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_activity_type", sa.String(50), nullable=True),
        sa.Column("reply_boost_until", sa.DateTime(timezone=True), nullable=True),
        # דגלים
        sa.Column(
            "dormant_flag", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column(
            "is_duplicate_suspected",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "is_returning_customer",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        # סגירה והערה
        sa.Column("closure_reason", sa.String(50), nullable=True),
        sa.Column("personal_note", sa.Text(), nullable=True),
        # timestamps
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("idx_leads_status", "leads", ["status"])
    op.create_index("idx_leads_owner", "leads", ["owner_id"])
    op.create_index(
        "idx_leads_needs_attention",
        "leads",
        ["needs_attention"],
        postgresql_where=sa.text("needs_attention = TRUE"),
    )
    op.create_index(
        "idx_leads_next_action",
        "leads",
        ["next_action_due_at"],
        postgresql_where=sa.text("status NOT IN ('WON', 'LOST', 'ARCHIVED')"),
    )

    # ===== activities =====
    op.create_table(
        "activities",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "lead_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("leads.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column(
            "performed_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("idx_activities_lead", "activities", ["lead_id", "created_at"])

    # ===== tasks =====
    op.create_table(
        "tasks",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "lead_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("leads.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column(
            "assigned_to",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("snoozed_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("origin_rule", sa.String(50), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "idx_tasks_open",
        "tasks",
        ["status", "due_at"],
        postgresql_where=sa.text("status = 'open'"),
    )

    # ===== templates =====
    op.create_table(
        "templates",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("target_audience", sa.String(50), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("variables", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # ===== bookings =====
    op.create_table(
        "bookings",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "lead_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("leads.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("requested_slot_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("requested_slot_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status", sa.String(30), nullable=False, server_default="pending_approval"
        ),
        sa.Column("google_calendar_event_id", sa.String(200), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
    )

    # ===== programs =====
    op.create_table(
        "programs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "lead_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("leads.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("program_type", sa.String(50), nullable=False),
        sa.Column("total_sessions", sa.Integer(), nullable=False),
        sa.Column(
            "completed_sessions",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("total_price", sa.Numeric(10, 2), nullable=True),
        sa.Column(
            "actual_hours",
            sa.Numeric(6, 2),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("estimated_end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
    )


def downgrade() -> None:
    op.drop_table("programs")
    op.drop_table("bookings")
    op.drop_table("templates")
    op.drop_index("idx_tasks_open", table_name="tasks")
    op.drop_table("tasks")
    op.drop_index("idx_activities_lead", table_name="activities")
    op.drop_table("activities")
    op.drop_index("idx_leads_next_action", table_name="leads")
    op.drop_index("idx_leads_needs_attention", table_name="leads")
    op.drop_index("idx_leads_owner", table_name="leads")
    op.drop_index("idx_leads_status", table_name="leads")
    op.drop_table("leads")
    op.drop_table("users")
