"""followup_rules — הגדרות פולואפ של נועה (§17.1).

טבלה לניהול 5 כללי הפולואף. seeded ב-up migration עם ברירות המחדל של
§17.1. שינוי דרך `PATCH /settings/followup-rules/{rule_key}` (owner-only).

repeat_count + repeat_interval — מנגנון תזכורת חוזרת. ברירת מחדל 1 =
התנהגות נוכחית (התראה בודדת). יממש בסבב 2 (cron).

Revision ID: 0029
Revises: 0028
Create Date: 2026-05-30
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0029"
down_revision: Union[str, None] = "0028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "followup_rules",
        sa.Column("rule_key", sa.String(50), primary_key=True),
        sa.Column("interval_value", sa.Integer(), nullable=False),
        sa.Column("interval_unit", sa.String(10), nullable=False),
        sa.Column(
            "repeat_count",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
        sa.Column(
            "repeat_interval_value",
            sa.Integer(),
            nullable=False,
            server_default="24",
        ),
        sa.Column(
            "repeat_interval_unit",
            sa.String(10),
            nullable=False,
            server_default="hours",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "interval_unit IN ('hours', 'days')",
            name="ck_followup_rules_interval_unit",
        ),
        sa.CheckConstraint(
            "repeat_interval_unit IN ('hours', 'days')",
            name="ck_followup_rules_repeat_interval_unit",
        ),
        sa.CheckConstraint(
            "repeat_count >= 1",
            name="ck_followup_rules_repeat_count_min",
        ),
        sa.CheckConstraint(
            "interval_value > 0",
            name="ck_followup_rules_interval_positive",
        ),
        sa.CheckConstraint(
            "repeat_interval_value > 0",
            name="ck_followup_rules_repeat_interval_positive",
        ),
    )

    # Seed — defaults של §17.1. idempotent: ON CONFLICT כדי שריצה חוזרת
    # של migration לא תיכשל ולא תדרוס ערכים שנערכו ידנית.
    op.execute(
        """
        INSERT INTO followup_rules
            (rule_key, interval_value, interval_unit,
             repeat_count, repeat_interval_value, repeat_interval_unit)
        VALUES
            ('first_response',    24, 'hours', 1, 24, 'hours'),
            ('lecture_inquiry',   24, 'hours', 1, 24, 'hours'),
            ('warm_followup',     48, 'hours', 1, 24, 'hours'),
            ('proposal_followup',  3, 'days',  1, 1,  'days'),
            ('dormant_check',     60, 'days',  1, 7,  'days')
        ON CONFLICT (rule_key) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_table("followup_rules")
