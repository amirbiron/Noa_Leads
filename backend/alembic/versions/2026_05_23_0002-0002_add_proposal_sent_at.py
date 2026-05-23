"""add proposal_sent_at to leads

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-23

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # שדה ייעודי לתאריך שליחת הצעה — מונע איפוס גיל ההצעה כשפונה
    # פולואפ outbound שמעדכן את last_outbound_at.
    op.add_column(
        "leads",
        sa.Column("proposal_sent_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("leads", "proposal_sent_at")
