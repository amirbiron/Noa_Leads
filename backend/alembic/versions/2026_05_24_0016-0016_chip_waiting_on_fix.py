"""Fix waiting_on for 2 chips per spec §16.4 update.

UX review identified that:
- "מעוניין בשיחה" had waiting_on=CLIENT but actually Noah needs to schedule
- "לחזור בעוד חודש" had waiting_on=CLIENT but actually Noah follows up

User-edited chips (different UUIDs) are not affected.
See spec-deviations.md F-24 for full context.

Revision ID: 0016
Revises: 0015
Create Date: 2026-05-24
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: Union[str, None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# UUIDs דטרמיניסטיים מ-migration 0013. UPDATE רק לזוג הזה — chips
# שנועה יצרה ידנית עם labels דומים (UUIDs רנדומליים) לא יושפעו.
_FIXED_CHIP_IDS = [
    "00000000-0000-0013-0000-000000000003",  # מעוניין בשיחה
    "00000000-0000-0013-0000-000000000006",  # לחזור בעוד חודש
]


def upgrade() -> None:
    # ::text cast חיוני: ANY עם array של strings נכשל מול עמודת UUID
    # ב-PostgreSQL — אותו דפוס כמו ב-migration 0013.
    op.execute(
        sa.text(
            "UPDATE quick_action_chips SET waiting_on = 'NOAH' "
            "WHERE id::text = ANY(:ids)"
        ).bindparams(ids=_FIXED_CHIP_IDS)
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE quick_action_chips SET waiting_on = 'CLIENT' "
            "WHERE id::text = ANY(:ids)"
        ).bindparams(ids=_FIXED_CHIP_IDS)
    )
