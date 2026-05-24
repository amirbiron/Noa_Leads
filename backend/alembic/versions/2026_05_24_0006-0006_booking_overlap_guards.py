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
    # btree_gist נטען מוקדם — נדרש ל-EXCLUDE בהמשך. range operators
    # ב-cleanup queries הם core postgres ולא דורשים את ה-extension.
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")

    # ===== cleanup לפני הוספת constraints =====
    # 0005 לא מנע את התרחישים שאנחנו עוצרים כאן, אז ייתכן שב-DB קיים
    # שורות legacy שיפילו את ה-CREATE INDEX/CONSTRAINT וכך יחסמו deploy
    # שלם. אסטרטגיה דטרמיניסטית: oldest-wins, החדשים מסומנים CANCELED.
    # downgrade לא משחזר את הסטטוס — לא ניתן לדעת איזה booking היה
    # "האמיתי" לפני הביטול.

    # 1) past active bookings — לא רלוונטיים לעולם הbusiness logic
    # החדש (ראה _expire_stale_bookings ב-app/services/booking.py).
    # מנקים מוקדם כדי לצמצם את המרחב לשלבים הבאים.
    op.execute(
        """
        UPDATE bookings SET status = 'canceled'
        WHERE status IN ('pending_approval', 'approved')
          AND requested_slot_end < now()
        """
    )

    # 2) >1 active לאותו lead — מבטל את החדשים, משאיר את הישן ביותר.
    # tiebreak על id מבטיח שגם בcreated_at זהה נישאר עם 1 active בדיוק.
    op.execute(
        """
        UPDATE bookings SET status = 'canceled'
        WHERE id IN (
            SELECT id FROM (
                SELECT id, ROW_NUMBER() OVER (
                    PARTITION BY lead_id ORDER BY created_at, id
                ) AS rn
                FROM bookings
                WHERE status IN ('pending_approval', 'approved')
            ) sub
            WHERE rn > 1
        )
        """
    )

    # 3) overlapping active בין לידים שונים — אחרי שלב 2 כל ליד מחזיק
    # רק active אחד, אז הoverlap היחיד שיכול להישאר הוא cross-lead.
    # שומר את הישן יותר (lex order של (created_at, id)); החדש מבוטל.
    op.execute(
        """
        UPDATE bookings SET status = 'canceled' WHERE id IN (
            SELECT b1.id
            FROM bookings b1
            JOIN bookings b2 ON b1.id != b2.id
              AND b1.status IN ('pending_approval', 'approved')
              AND b2.status IN ('pending_approval', 'approved')
              AND tstzrange(b1.requested_slot_start, b1.requested_slot_end, '[)') &&
                  tstzrange(b2.requested_slot_start, b2.requested_slot_end, '[)')
              AND (b1.created_at, b1.id) > (b2.created_at, b2.id)
        )
        """
    )

    # ===== constraints =====
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
