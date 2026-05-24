"""add booking_token to leads + partial unique index on bookings

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-24

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ===== booking_token לליד =====
    # מפתח URL-safe שמופץ ללקוח ומאפשר לו גישה לדף קביעת תור משלו.
    # 1) מוסיפים nullable כדי להוסיף לטבלה קיימת
    # 2) ממלאים ערכים אקראיים ללידים קיימים
    # 3) הופכים ל-NOT NULL + מוסיפים unique index
    op.add_column(
        "leads",
        sa.Column("booking_token", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.execute("UPDATE leads SET booking_token = gen_random_uuid()")
    op.alter_column("leads", "booking_token", nullable=False)
    op.create_index(
        "idx_leads_booking_token",
        "leads",
        ["booking_token"],
        unique=True,
    )
    # החל מעכשיו, יצירת ליד חדש תקבל token אוטומטית דרך server_default ב-model.

    # ===== מניעת תורים כפולים על אותו lead+slot =====
    # ראה: docs/references/google-calendar-blueprint.md סעיף 4.
    # partial — חל רק על תורים פעילים (לא ביטולים/דחיות).
    op.create_index(
        "idx_bookings_active_slot",
        "bookings",
        ["lead_id", "requested_slot_start"],
        unique=True,
        postgresql_where=sa.text(
            "status IN ('pending_approval', 'approved')"
        ),
    )


def downgrade() -> None:
    op.drop_index("idx_bookings_active_slot", table_name="bookings")
    op.drop_index("idx_leads_booking_token", table_name="leads")
    op.drop_column("leads", "booking_token")
