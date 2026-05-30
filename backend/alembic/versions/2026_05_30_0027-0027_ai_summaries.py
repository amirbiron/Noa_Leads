"""ai_summaries — סיכומי AI נרטיביים יומיים/שבועיים (C.1/C.2 §6.5).

טבלה חדשה לאחסון הפלט הנרטיבי של Claude (bottom_line/today/highlights/...),
לצד daily_summaries הסטטיסטי הקיים (לא מחליפה אותו).

input_data = ה-user prompt המבושל; output = ה-result כ-JSONB. unique על
(type, date_range_start, date_range_end) → first-write-wins (ריצה חוזרת לא
יוצרת כפילות ולא דורסת inaccurate_count).

Revision ID: 0027
Revises: 0026
Create Date: 2026-05-30
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0027"
down_revision: Union[str, None] = "0026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ai_summaries",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("type", sa.String(length=10), nullable=False),
        sa.Column("date_range_start", sa.Date(), nullable=False),
        sa.Column("date_range_end", sa.Date(), nullable=False),
        sa.Column("input_data", postgresql.JSONB(), nullable=False),
        sa.Column("output", postgresql.JSONB(), nullable=False),
        sa.Column(
            "inaccurate_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column("model_used", sa.String(length=50), nullable=False),
        sa.Column("tokens_in", sa.Integer(), nullable=True),
        sa.Column("tokens_out", sa.Integer(), nullable=True),
        sa.Column(
            "validation_warning",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "type",
            "date_range_start",
            "date_range_end",
            name="uq_ai_summaries_type_range",
        ),
    )


def downgrade() -> None:
    op.drop_table("ai_summaries")
