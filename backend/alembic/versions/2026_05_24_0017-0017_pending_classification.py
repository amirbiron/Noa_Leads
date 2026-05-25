"""Add pending_classification to leads (Phase 3 Stage 16).

Per docs/phase-3-ai-token-management.md §retry: כש-classify_email נכשל
ב-RateLimitError, ה-caller מסמן pending_classification=true. cron
(retry_pending_classification, ייבנה ב-Stage 18) ירוץ כל דקה ויעבד
מחדש לידים עם הדגל. השדה nullable=False עם default false כדי שלידים
קיימים יקבלו ערך מיידי.

partial index חלקי על pending=true: רוב הזמן 0 שורות, אז ה-scan של
ה-cron יהיה O(1). מבוסס על אותו דפוס כמו idx_leads_next_action ב-0001.

Revision ID: 0017
Revises: 0016
Create Date: 2026-05-24
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: Union[str, None] = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "leads",
        sa.Column(
            "pending_classification",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    # partial index — רוב הזמן 0 שורות, scan של ה-cron O(1).
    op.create_index(
        "idx_leads_pending_classification",
        "leads",
        ["pending_classification"],
        postgresql_where=sa.text("pending_classification = true"),
    )


def downgrade() -> None:
    op.drop_index("idx_leads_pending_classification", table_name="leads")
    op.drop_column("leads", "pending_classification")
