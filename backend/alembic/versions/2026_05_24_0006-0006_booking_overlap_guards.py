"""enforce one-booking-per-lead + no overlapping bookings

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-24

Cursor High findings:
- Concurrent bookings can overlap same slot (different leads, race)
- Two active bookings per lead (different times, race)

Solution:
1. Replace (lead_id, slot_start) index with (lead_id) — one active booking
   per lead, enforced at DB level.
2. EXCLUDE USING gist constraint — no two active bookings can overlap in time.
   Requires btree_gist extension (standard in Postgres, available on Render).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Replace index: was (lead_id, slot_start), now just (lead_id)
    op.drop_index("idx_bookings_active_slot", table_name="bookings")
    op.create_index(
        "idx_bookings_active_lead",
        "bookings",
        ["lead_id"],
        unique=True,
        postgresql_where=sa.text(
            "status IN ('pending_approval', 'approved')"
        ),
    )

    # 2. EXCLUDE constraint על time-range overlap עבור bookings פעילים.
    # btree_gist נדרש כי tstzrange משתמש ב-GiST index. הוא extension סטנדרטי
    # שזמין ב-Postgres על Render.
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.execute(
        """
        ALTER TABLE bookings ADD CONSTRAINT ck_bookings_no_overlap
        EXCLUDE USING gist (
            tstzrange(requested_slot_start, requested_slot_end, '[)') WITH &&
        ) WHERE (status IN ('pending_approval', 'approved'))
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE bookings DROP CONSTRAINT IF EXISTS ck_bookings_no_overlap")
    op.drop_index("idx_bookings_active_lead", table_name="bookings")
    op.create_index(
        "idx_bookings_active_slot",
        "bookings",
        ["lead_id", "requested_slot_start"],
        unique=True,
        postgresql_where=sa.text(
            "status IN ('pending_approval', 'approved')"
        ),
    )
    # ה-extension נשאר — לא מסירים, יכול לשמש בעתיד
