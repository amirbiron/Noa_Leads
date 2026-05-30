"""leads.status_changed_at — זמן שינוי הסטטוס האחרון (C.1 §6.3).

מוסיף עמודת `status_changed_at` (TIMESTAMPTZ) לטבלת leads: מתי הסטטוס של הליד
השתנה בפעם האחרונה. נדרש ל-block "דורש תשומת לב" בסיכום היומי כדי להציג
"ימים בסטטוס נוכחי" מדויק (במקום קירוב מ-due_at של משימה תקועה).

עדכון אוטומטי דרך **DB trigger** (BEFORE UPDATE) שמקדם את השדה רק כש-
`OLD.status IS DISTINCT FROM NEW.status` — תופס את כל אתרי שינוי הסטטוס
(close_lead, booking, chips, lead_actions, booking_sync) + כל אתר עתידי,
בלי drift ובלי לגעת בקוד השירותים. INSERTs מקבלים את server_default now().

backfill: לכל ליד קיים — GREATEST(last_activity_at, created_at). ב-PG
GREATEST מתעלם מ-NULL, ו-created_at תמיד קיים → לעולם לא NULL.

Revision ID: 0025
Revises: 0024
Create Date: 2026-05-30
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0025"
down_revision: Union[str, None] = "0024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "leads",
        sa.Column(
            "status_changed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
    )
    # backfill חד-פעמי ללידים קיימים — הזמן האחרון שידוע בליד מכל מקור,
    # ובהיעדרו זמן היצירה. GREATEST מתעלם מ-NULL ב-Postgres.
    op.execute(
        """
        UPDATE leads
        SET status_changed_at = GREATEST(last_activity_at, created_at)
        """
    )
    # trigger: מקדם את status_changed_at רק כשהסטטוס באמת משתנה. נקודת אכיפה
    # יחידה ב-DB — תופסת כל UPDATE על leads, גם מקוד עתידי, בלי drift.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION set_lead_status_changed_at()
        RETURNS trigger AS $$
        BEGIN
            IF NEW.status IS DISTINCT FROM OLD.status THEN
                NEW.status_changed_at := now();
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_lead_status_changed_at
        BEFORE UPDATE ON leads
        FOR EACH ROW
        -- EXECUTE PROCEDURE (ולא FUNCTION) לתאימות PG13 שעדיין נתמך ב-Render:
        -- PG13 מקבל רק PROCEDURE, ו-PG14+ מקבל את שניהם (PROCEDURE כ-alias).
        EXECUTE PROCEDURE set_lead_status_changed_at();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_lead_status_changed_at ON leads")
    op.execute("DROP FUNCTION IF EXISTS set_lead_status_changed_at()")
    op.drop_column("leads", "status_changed_at")
