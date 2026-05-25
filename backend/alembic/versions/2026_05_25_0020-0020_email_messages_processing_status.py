"""email_messages.processing_status (Phase 3 Stage 18 commit 4/4 — bugbot fix).

מבדיל בין רשומות "סופיות" (heuristic_spam / not_business / lead_created /
manual_review) לבין רשומות שאכן ממתינות לעיבוד AI חוזר (pending).

ה-cron `retry_pending_classification` סרק קודם לפי `lead_id IS NULL` —
אבל גם רשומות שhe-AI כבר סיווג כ-not_business, וגם רשומות שדולגו ע"י
ה-heuristic spam filter, יושבות כ-lead_id=NULL לעולם. בלי הדגל הזה הן
היו נכנסות ל-cron כל דקה, נשלחות שוב ל-AI (גם spam), ואחרי 10 ניסיונות
היו יוצרות manual_review_needed lead — בעצם הרגולציה של ה-heuristic ושל
ה-AI היו מתבטלות.

ערכים:
- `pending`  — צריך classify+extract. cron picks up.
- `lead_created` — נוצר ליד בהצלחה (lead_id IS NOT NULL).
- `not_business` — AI סיווג כלא-עסקי. תווית "סוננו" ב-Gmail. אין ליד.
- `heuristic_spam` — דולג על AI ע"י heuristic. תווית "סוננו". אין ליד.
- `manual_review` — AI נכשל MAX פעמים, נוצר ליד עם manual_review_needed=True.

server_default='pending' — תקין לרשומות קיימות (אם יש; בפרודקשן אין עדיין).

Partial index על pending — רוב הרשומות בעבר היו לא-pending,
ה-cron יוכל למצוא במהירות את המעטות שעדיין צריכות עיבוד.

Revision ID: 0020
Revises: 0019
Create Date: 2026-05-25
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0020"
down_revision: Union[str, None] = "0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "email_messages",
        sa.Column(
            "processing_status",
            sa.String(length=30),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
    )
    # partial index — cron query: WHERE processing_status='pending' AND
    # classification_retry_count < MAX. סריקה O(pending) שהוא אחוזים בודדים
    # מסך הטבלה (רוב המיילים נכנסים למצב סופי תוך דקות).
    op.create_index(
        "idx_email_messages_pending",
        "email_messages",
        ["classification_retry_count"],
        postgresql_where=sa.text("processing_status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index("idx_email_messages_pending", table_name="email_messages")
    op.drop_column("email_messages", "processing_status")
