"""booking_token DB default + booking_id on tasks

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-24

שני תיקוני שורש מפיירוט bug-report של המשתמש:

1. booking_token NULL ב-INSERT (NotNullViolationError):
   migration 0005 הוסיפה nullable=false, אבל לא קבעה DEFAULT ב-DB.
   SQLAlchemy server_default ב-model תקף רק ב-CREATE TABLE, לא ב-ALTER.
   תיקון: ALTER COLUMN ... SET DEFAULT gen_random_uuid().

2. booking_id ל-tasks: post_meeting_tasks dedup היה per-lead, מה
   שגרם לדיכוי משימות לbookings שונים של אותו ליד באותו חלון.
   nullable=true כדי לתמוך ב-tasks שלא קשורים ל-booking (FOLLOWUP וכו').
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ===== 1. booking_token DEFAULT =====
    op.alter_column(
        "leads",
        "booking_token",
        server_default=sa.text("gen_random_uuid()"),
    )

    # ===== 2. tasks.booking_id =====
    op.add_column(
        "tasks",
        sa.Column(
            "booking_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("bookings.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    # index לעזרה ב-dedup של post_meeting_cron
    op.create_index(
        "idx_tasks_booking_id",
        "tasks",
        ["booking_id"],
        postgresql_where=sa.text("booking_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("idx_tasks_booking_id", table_name="tasks")
    op.drop_column("tasks", "booking_id")
    op.alter_column("leads", "booking_token", server_default=None)
