"""leads.lead_message — תוכן הפנייה (§7.1).

מוסיף עמודת `lead_message` (TEXT) לטבלת leads: ההודעה שהגיעה בוואטסאפ /
תיאור במילות נועה מה הלקוח רצה. שדה חובה בטופס היצירה הידני (נאכף ב-
LeadCreateManual), אבל nullable ב-DB — קליטה אוטומטית (טופס/וואטסאפ/מייל)
ממלאת אותו מתוכן הפנייה הקיים, ולידים ישנים עשויים להישאר ריקים.

ללא server_default וללא backfill — לידים קיימים הם רשומות בדיקה בלבד.

Revision ID: 0022
Revises: 0021
Create Date: 2026-05-29
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0022"
down_revision: Union[str, None] = "0021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "leads",
        sa.Column("lead_message", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("leads", "lead_message")
