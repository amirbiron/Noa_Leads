"""weekly_open_state_snapshots — צילום קבוע למצב פתוח בסוף השבוע.

cron חדש (capture_weekly_open_state) רץ ב-ראשון 00:00 שעון ישראל
(Saturday 21:00 UTC) וכותב row אחד פר-שבוע. `build_weekly_user_prompt`
שולף ממנו במקום לשחזר from-mutable-fields. סוגר 7 ממצאי cursor bugbot
מתמשכים על `_open_state`.

מקביל בדפוס ל-daily_summaries (migration 0012, F-07). singleton, UNIQUE
על week_end_date → first-write-wins (re-run ב-cron לא דורס).

Revision ID: 0028
Revises: 0027
Create Date: 2026-05-30
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0028"
down_revision: Union[str, None] = "0027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "weekly_open_state_snapshots",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "week_end_date",
            sa.Date(),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "open_leads_total", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "stuck_leads_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "stale_proposals_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "overdue_tasks_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "dormant_with_recommendation_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    # שליפה של ה-snapshot העדכני ביותר תהיה לפי week_end_date desc
    op.create_index(
        "idx_weekly_open_state_snapshots_week_end_desc",
        "weekly_open_state_snapshots",
        [sa.text("week_end_date DESC")],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_weekly_open_state_snapshots_week_end_desc",
        table_name="weekly_open_state_snapshots",
    )
    op.drop_table("weekly_open_state_snapshots")
