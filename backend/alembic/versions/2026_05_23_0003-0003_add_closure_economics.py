"""add closure economics fields to leads

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-23

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # שדות לחישוב רווחיות אמיתי על ליד WON.
    # ה-Program מטפל בתוכניות מתמשכות; השדות כאן ל-deals חד-פעמיים
    # (סדנאות, הרצאות) ולסיכום עסקה כללי על הליד.
    op.add_column(
        "leads",
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "leads",
        sa.Column("closed_value", sa.Numeric(10, 2), nullable=True),
    )
    op.add_column(
        "leads",
        sa.Column("actual_hours", sa.Numeric(6, 2), nullable=True),
    )

    # אינדקס חלקי לתובנות שבועיות — שולפים WON עם closed_at בשבוע הנוכחי
    op.create_index(
        "idx_leads_closed_at",
        "leads",
        ["closed_at"],
        postgresql_where=sa.text("status = 'WON' AND closed_at IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("idx_leads_closed_at", table_name="leads")
    op.drop_column("leads", "actual_hours")
    op.drop_column("leads", "closed_value")
    op.drop_column("leads", "closed_at")
