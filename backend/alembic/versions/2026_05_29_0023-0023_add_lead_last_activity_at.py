"""leads.last_activity_at — מקור ל-badge "גיל" מכל מקור (§12.1).

מוסיף עמודת cache `last_activity_at` (TIMESTAMPTZ) לטבלת leads: זמן הפעולה
האחרונה בליד מכל מקור (לקוח/נועה) — בניגוד ל-last_outbound_at שהוא רק outbound
של נועה. מתעדכן מרכזית ב-log_activity בכל יצירת activity.

backfill: לכל ליד קיים — MAX(activities.created_at), ובהיעדר activities נופל
ל-created_at של הליד (כך שלעולם לא NULL ללידים קיימים).

Revision ID: 0023
Revises: 0022
Create Date: 2026-05-29
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0023"
down_revision: Union[str, None] = "0022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "leads",
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=True),
    )
    # backfill מ-MAX(activities.created_at), fallback ל-created_at של הליד.
    op.execute(
        """
        UPDATE leads SET last_activity_at = COALESCE(
            (SELECT MAX(a.created_at) FROM activities a WHERE a.lead_id = leads.id),
            created_at
        )
        """
    )


def downgrade() -> None:
    op.drop_column("leads", "last_activity_at")
