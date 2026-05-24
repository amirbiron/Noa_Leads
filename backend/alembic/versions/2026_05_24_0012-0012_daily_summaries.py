"""add daily_summaries table (F-07)

Revision ID: 0012
Revises: 0011
Create Date: 2026-05-24

לפי Spec §16.3 + Changelog v2.1: "daily_summary לא נשלח לטלגרם אלא
מופיע בדשבורד". הטבלה שומרת את הסיכום האחרון של ה-cron, וה-dashboard
endpoint שולף אותה בכניסה. ראה F-07 ב-docs/spec-deviations.md.

singleton — אין user_id (נועה היחידה). UNIQUE על summary_date מאפשר
upsert בעת re-run של cron באותו יום.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "daily_summaries",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "summary_date",
            sa.Date(),
            nullable=False,
            unique=True,
        ),
        sa.Column("new_leads_today", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tasks_done_today", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tasks_for_tomorrow", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("urgent_open", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    # index שיעזור לשליפה של ה-summary העדכני
    op.create_index(
        "idx_daily_summaries_date_desc",
        "daily_summaries",
        [sa.text("summary_date DESC")],
    )


def downgrade() -> None:
    op.drop_index("idx_daily_summaries_date_desc", table_name="daily_summaries")
    op.drop_table("daily_summaries")
