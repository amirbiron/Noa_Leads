"""chips schema לפי SpecV2.1 §5.7 + seed לפי §16.4

Revision ID: 0013
Revises: 0012
Create Date: 2026-05-24

F-01 + F-05 ב-docs/spec-deviations.md.

שינוי schema של quick_action_chips לפי §5.7 v2.1 (declarative model):
- מוסיף: target_status, waiting_on, followup_task_type, auto_followup_days
- מסיר: action_type, requires_content (לא ב-§5.7)

6 ה-seeds מ-migration 0010 לא תאמו לאפיון (כללו "סיכמתי שיחה" / "שלחתי
תבנית" / "הוסיפי הערה" / "הודעה נכנסת" — אף אחד מהם ב-§16.4) ומוחלפים
ב-6 חדשים מטבלת §16.4. UUIDs דטרמיניסטיים → downgrade בטוח.

צ'יפים שנועה הוסיפה ידנית (UUIDs רנדומליים) יישארו עם NULL ב-4 השדות
החדשים. ה-frontend מציג רק chips ש-4 השדות שלהם מאוכלסים — כך שצ'יפים
ישנים לא יישברו אלא רק לא יוצגו עד שנועה תערוך אותם דרך /settings/chips.

בנוסף, data migration: tasks עם type='dormant_reachout' (שם ישן) מקבלים
'dormant_check' (שם חדש לפי §17.1). ראה commit 2 (constants.py).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# 6 הצ'יפים החדשים — מועתקים 1:1 מטבלת §16.4 ב-SpecV2.1.md.
# UUIDs דטרמיניסטיים תחת prefix 0013 כדי שlowngrade ידע מה למחוק.
_DEFAULT_CHIPS_V21 = [
    {
        "id": "00000000-0000-0013-0000-000000000001",
        "label": "אין מענה",
        "target_status": "IN_PROGRESS",
        "waiting_on": "NOAH",
        "followup_task_type": "retry_call",
        "auto_followup_days": 1,
        "sort_order": 0,
    },
    {
        "id": "00000000-0000-0013-0000-000000000002",
        "label": "רוצה פרטים",
        "target_status": "IN_PROGRESS",
        "waiting_on": "NOAH",
        "followup_task_type": "followup",
        "auto_followup_days": 1,
        "sort_order": 1,
    },
    {
        "id": "00000000-0000-0013-0000-000000000003",
        "label": "מעוניין בשיחה",
        "target_status": "IN_PROGRESS",
        "waiting_on": "CLIENT",
        "followup_task_type": "followup",
        "auto_followup_days": 2,
        "sort_order": 2,
    },
    {
        "id": "00000000-0000-0013-0000-000000000004",
        "label": "רוצה הצעה",
        "target_status": "IN_PROGRESS",
        "waiting_on": "NOAH",
        "followup_task_type": "send_proposal",
        "auto_followup_days": 1,
        "sort_order": 3,
    },
    {
        "id": "00000000-0000-0013-0000-000000000005",
        "label": "לא רלוונטי כרגע",
        "target_status": "IN_PROGRESS",
        "waiting_on": "CLIENT",
        "followup_task_type": "dormant_check",
        "auto_followup_days": 60,
        "sort_order": 4,
    },
    {
        "id": "00000000-0000-0013-0000-000000000006",
        "label": "לחזור בעוד חודש",
        "target_status": "IN_PROGRESS",
        "waiting_on": "CLIENT",
        "followup_task_type": "followup",
        "auto_followup_days": 30,
        "sort_order": 5,
    },
]

# 6 ה-UUIDs של ה-seeds הישנים מ-migration 0010.
_OLD_SEED_IDS = [
    f"00000000-0000-0010-0000-00000000000{i}" for i in range(1, 7)
]

# Defaults של 0010 — נחוצים ל-downgrade כדי לשחזר.
_OLD_DEFAULTS = [
    ("00000000-0000-0010-0000-000000000001", "אין מענה", "log_call_no_answer", False, 0),
    ("00000000-0000-0010-0000-000000000002", "סיכמתי שיחה", "log_call_completed", False, 1),
    ("00000000-0000-0010-0000-000000000003", "שלחתי תבנית", "mark_template_sent", False, 2),
    ("00000000-0000-0010-0000-000000000004", "שלחתי הצעה", "mark_proposal_sent", False, 3),
    ("00000000-0000-0010-0000-000000000005", "הוסיפי הערה", "add_internal_note", True, 4),
    ("00000000-0000-0010-0000-000000000006", "הודעה נכנסת", "log_inbound_message", False, 5),
]


def upgrade() -> None:
    bind = op.get_bind()

    # 1. הוספת 4 עמודות חדשות (כולן nullable כדי לתמוך בchips שנועה
    #    יצרה ידנית בלי השדות החדשים — הם יוצגו רק אחרי שתערוך אותם).
    op.add_column(
        "quick_action_chips",
        sa.Column("target_status", sa.String(length=30), nullable=True),
    )
    op.add_column(
        "quick_action_chips",
        sa.Column("waiting_on", sa.String(length=30), nullable=True),
    )
    op.add_column(
        "quick_action_chips",
        sa.Column(
            "followup_task_type", sa.String(length=50), nullable=True
        ),
    )
    op.add_column(
        "quick_action_chips",
        sa.Column("auto_followup_days", sa.Integer(), nullable=True),
    )

    # 2. מחיקת 6 ה-seeds הישנים (UUIDs דטרמיניסטיים מ-0010).
    #    הסמנטיקה שלהם לא תואמת לאפיון — לא ניתן לתרגם 1:1. נועה תקבל
    #    את 6 החדשים מ-§16.4. צ'יפים אחרים נשארים נגיעים.
    bind.execute(
        sa.text(
            # ::text cast חיוני: ANY עם array של strings נכשל מול עמודת
            # UUID ב-PostgreSQL. השוואה כ-text עובדת בכל driver. 6 שורות
            # בלבד — לא משפיע על ביצועים.
            "DELETE FROM quick_action_chips WHERE id::text = ANY(:ids)"
        ),
        {"ids": _OLD_SEED_IDS},
    )

    # 3. הסרת העמודות הישנות (לא ב-§5.7). שאר הקוד (state_machine + actions
    #    דינמיים) ממשיך לתפקד דרך DynamicActionButton, לא תלוי בchips.
    op.drop_column("quick_action_chips", "action_type")
    op.drop_column("quick_action_chips", "requires_content")

    # 4. INSERT 6 הצ'יפים החדשים. idempotent דרך ON CONFLICT (id)
    #    DO NOTHING — re-run של migration 0013 אחרי downgrade לא יכפול.
    for chip in _DEFAULT_CHIPS_V21:
        bind.execute(
            sa.text(
                """
                INSERT INTO quick_action_chips (
                    id, label, target_status, waiting_on,
                    followup_task_type, auto_followup_days,
                    sort_order, is_active, created_at, updated_at
                ) VALUES (
                    :id, :label, :target_status, :waiting_on,
                    :followup_task_type, :auto_followup_days,
                    :sort_order, TRUE, NOW(), NOW()
                ) ON CONFLICT (id) DO NOTHING
                """
            ),
            chip,
        )

    # 5. Data migration: tasks עם type='dormant_reachout' (שם ישן מ-constants
    #    לפני commit 2) → 'dormant_check' (שם הספק §17.1). בטוח גם אם אין שורות.
    bind.execute(
        sa.text(
            "UPDATE tasks SET type = 'dormant_check' "
            "WHERE type = 'dormant_reachout'"
        )
    )


def downgrade() -> None:
    bind = op.get_bind()

    # 1. שחזור tasks: dormant_check → dormant_reachout.
    bind.execute(
        sa.text(
            "UPDATE tasks SET type = 'dormant_reachout' "
            "WHERE type = 'dormant_check'"
        )
    )

    # 2. מחיקת 6 ה-seeds החדשים (UUIDs דטרמיניסטיים 0013).
    bind.execute(
        sa.text(
            # ::text cast חיוני: ANY עם array של strings נכשל מול עמודת
            # UUID ב-PostgreSQL. השוואה כ-text עובדת בכל driver. 6 שורות
            # בלבד — לא משפיע על ביצועים.
            "DELETE FROM quick_action_chips WHERE id::text = ANY(:ids)"
        ),
        {"ids": [c["id"] for c in _DEFAULT_CHIPS_V21]},
    )

    # 3. הוספת העמודות הישנות חזרה — תחילה כ-nullable, מילוי placeholder,
    #    ואז NOT NULL. הצורך ב-placeholder: צ'יפים שנועה הוסיפה ידנית בין
    #    upgrade ל-downgrade לא יהיה להם action_type כלל.
    op.add_column(
        "quick_action_chips",
        sa.Column("action_type", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "quick_action_chips",
        sa.Column(
            "requires_content",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    bind.execute(
        sa.text(
            "UPDATE quick_action_chips SET action_type = 'log_call_completed' "
            "WHERE action_type IS NULL"
        )
    )
    op.alter_column(
        "quick_action_chips",
        "action_type",
        existing_type=sa.String(length=50),
        nullable=False,
    )

    # 4. הסרת 4 העמודות החדשות.
    op.drop_column("quick_action_chips", "auto_followup_days")
    op.drop_column("quick_action_chips", "followup_task_type")
    op.drop_column("quick_action_chips", "waiting_on")
    op.drop_column("quick_action_chips", "target_status")

    # 5. שחזור 6 ה-seeds הישנים של 0010 (idempotent).
    for cid, label, action_type, req_content, sort_order in _OLD_DEFAULTS:
        bind.execute(
            sa.text(
                """
                INSERT INTO quick_action_chips
                    (id, label, action_type, requires_content, sort_order,
                     is_active, created_at, updated_at)
                VALUES
                    (:id, :label, :action_type, :req, :sort_order,
                     TRUE, NOW(), NOW())
                ON CONFLICT (id) DO NOTHING
                """
            ),
            {
                "id": cid,
                "label": label,
                "action_type": action_type,
                "req": req_content,
                "sort_order": sort_order,
            },
        )
