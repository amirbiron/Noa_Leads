"""leads.first_outbound_at — זמן ה-outbound הראשון אי-פעם (C.2 §4.2).

מוסיף עמודת `first_outbound_at` (TIMESTAMPTZ) לטבלת leads: מתי שלחנו לליד
outbound בפעם הראשונה. נדרש למדד "זמן תגובה ראשון ממוצע" בסיכום השבועי
(`AVG(first_outbound_at - created_at)`), בלי לערבב פולואפים מאוחרים.

עדכון אוטומטי דרך **DB trigger** (BEFORE UPDATE) שמקדם את השדה רק כש-
`last_outbound_at` משתנה **ו**-`first_outbound_at` עדיין NULL — כלומר רק
בפעם הראשונה, ואז קפוא. תופס את כל אתרי הכתיבה ל-last_outbound_at
(lead_actions, quick_action_chips) + עתידיים, בלי לגעת בקוד השירותים.

backfill: לכל ליד קיים — MIN(created_at) של ה-activity מסוג outbound;
ובהיעדר activity כזה אך עם last_outbound_at (למשל chip-only) — last_outbound_at.

Revision ID: 0026
Revises: 0025
Create Date: 2026-05-30
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0026"
down_revision: Union[str, None] = "0025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "leads",
        sa.Column(
            "first_outbound_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    # backfill מדויק מה-activity log: ה-outbound הראשון לכל ליד. סוגי ה-activity
    # הם פעולות ה-outbound שמהן last_outbound_at נגזר (הודעות/תבניות/שיחות/הצעה).
    op.execute(
        """
        UPDATE leads l
        SET first_outbound_at = sub.first_ts
        FROM (
            SELECT lead_id, MIN(created_at) AS first_ts
            FROM activities
            WHERE type IN (
                'template_marked_sent', 'manual_message_logged',
                'outbound_message_logged', 'call_completed',
                'call_no_answer', 'proposal_sent'
            )
            GROUP BY lead_id
        ) sub
        WHERE sub.lead_id = l.id
        """
    )
    # fallback ללידים בלי activity outbound אך עם last_outbound_at (chip-only):
    op.execute(
        """
        UPDATE leads
        SET first_outbound_at = last_outbound_at
        WHERE first_outbound_at IS NULL AND last_outbound_at IS NOT NULL
        """
    )
    # trigger: מקדם את first_outbound_at רק בפעם הראשונה ש-last_outbound_at
    # מקבל ערך. נקודת אכיפה יחידה ב-DB — תופסת כל UPDATE על leads בלי drift.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION set_lead_first_outbound_at()
        RETURNS trigger AS $$
        BEGIN
            IF NEW.last_outbound_at IS DISTINCT FROM OLD.last_outbound_at
               AND OLD.first_outbound_at IS NULL THEN
                NEW.first_outbound_at := NEW.last_outbound_at;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_lead_first_outbound_at
        BEFORE UPDATE ON leads
        FOR EACH ROW
        -- EXECUTE PROCEDURE (ולא FUNCTION) לתאימות PG13 שעדיין נתמך ב-Render:
        -- PG13 מקבל רק PROCEDURE, ו-PG14+ מקבל את שניהם (PROCEDURE כ-alias).
        EXECUTE PROCEDURE set_lead_first_outbound_at();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_lead_first_outbound_at ON leads")
    op.execute("DROP FUNCTION IF EXISTS set_lead_first_outbound_at()")
    op.drop_column("leads", "first_outbound_at")
