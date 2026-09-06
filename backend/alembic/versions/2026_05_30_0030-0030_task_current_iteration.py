"""tasks.current_iteration — מונה תזכורות פולואפ (§17.1 mechanism).

מתווסף ל-Task כדי לתמוך במנגנון התזכורת החוזרת (§17.1). cron
`mark_overdue` מעלה ב-1 בכל פעם שהתראה נשלחת, מוגבל ע"י
`FollowupRule.repeat_count` של ה-rule_key המתאים ל-task.type.

ערך מחדל 0 שומר על התנהגות נוכחית (התראה אחת בלבד, בלי חזרות) ל-tasks
קיימים. tasks חדשים מתחילים אותו דבר; ה-cron מטפל בלוגיקה.

Revision ID: 0030
Revises: 0029
Create Date: 2026-05-30
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0030"
down_revision: Union[str, None] = "0029"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tasks",
        sa.Column(
            "current_iteration",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("tasks", "current_iteration")
