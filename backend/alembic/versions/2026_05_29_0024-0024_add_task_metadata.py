"""tasks.metadata — JSONB ל-metadata מובנית של משימה (§19 D.1).

מוסיף עמודת `metadata` (JSONB, nullable) לטבלת tasks. נדרשת ל-task מסוג
dormant_suggestion ששומר את המלצת ה-AI ({ai_action, ai_reasoning,
ai_generated_at, model_used}). עקבי עם activities.metadata.

ללא backfill — משימות קיימות נשארות NULL (אין להן metadata).

Revision ID: 0024
Revises: 0023
Create Date: 2026-05-29
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0024"
down_revision: Union[str, None] = "0023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tasks",
        sa.Column("metadata", JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tasks", "metadata")
