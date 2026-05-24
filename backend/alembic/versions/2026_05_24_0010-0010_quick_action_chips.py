"""quick_action_chips table + seed 6 defaults

Revision ID: 0010
Revises: 0009
Create Date: 2026-05-24

לפי האפיון ח: 6 צ'יפים editable לסיכום שיחה. נועה תוכל לערוך/להוסיף/
למחוק דרך הגדרות. החלטה: §2.1 ב-phase-2.5-plan.md.

ה-seed קורה רק אם הטבלה ריקה. UUIDs דטרמיניסטיים → downgrade בטוח.
"""

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# 6 הצ'יפים הקיימים hardcoded ב-QuickActions.tsx — מועברים ל-DB.
# UUIDs דטרמיניסטיים כך ש-downgrade ימחק רק את ה-seeds, לא צ'יפים
# שנועה תיצור ידנית.
_DEFAULT_CHIPS = [
    {
        "id": "00000000-0000-0010-0000-000000000001",
        "label": "אין מענה",
        "action_type": "log_call_no_answer",
        "requires_content": False,
        "sort_order": 0,
    },
    {
        "id": "00000000-0000-0010-0000-000000000002",
        "label": "סיכמתי שיחה",
        "action_type": "log_call_completed",
        "requires_content": False,
        "sort_order": 1,
    },
    {
        "id": "00000000-0000-0010-0000-000000000003",
        "label": "שלחתי תבנית",
        "action_type": "mark_template_sent",
        "requires_content": False,
        "sort_order": 2,
    },
    {
        "id": "00000000-0000-0010-0000-000000000004",
        "label": "שלחתי הצעה",
        "action_type": "mark_proposal_sent",
        "requires_content": False,
        "sort_order": 3,
    },
    {
        "id": "00000000-0000-0010-0000-000000000005",
        "label": "הוסיפי הערה",
        "action_type": "add_internal_note",
        "requires_content": True,
        "sort_order": 4,
    },
    {
        "id": "00000000-0000-0010-0000-000000000006",
        "label": "הודעה נכנסת",
        "action_type": "log_inbound_message",
        "requires_content": False,
        "sort_order": 5,
    },
]


def upgrade() -> None:
    op.create_table(
        "quick_action_chips",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("label", sa.String(length=100), nullable=False),
        sa.Column("action_type", sa.String(length=50), nullable=False),
        sa.Column(
            "requires_content",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "sort_order",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            onupdate=sa.text("now()"),
            nullable=False,
        ),
    )

    # seed 6 ברירת מחדל — רק אם הטבלה ריקה. בdeploy ראשון: יש 6 entries.
    # ב-rerun (לא צפוי כי alembic locks) — מדלגים.
    bind = op.get_bind()
    existing = bind.execute(
        sa.text("SELECT COUNT(*) FROM quick_action_chips")
    ).scalar_one()
    if existing > 0:
        return

    for chip in _DEFAULT_CHIPS:
        bind.execute(
            sa.text(
                """
                INSERT INTO quick_action_chips
                    (id, label, action_type, requires_content, sort_order,
                     is_active, created_at, updated_at)
                VALUES
                    (:id, :label, :action_type, :requires_content,
                     :sort_order, TRUE, NOW(), NOW())
                """
            ),
            chip,
        )


def downgrade() -> None:
    op.drop_table("quick_action_chips")
