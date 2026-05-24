"""leads.waiting_on: VARCHAR(20) → VARCHAR(30)

Revision ID: 0014
Revises: 0013
Create Date: 2026-05-24

תיקון פער מול Spec v2.1 §5.1 שמגדיר `waiting_on VARCHAR(30)`. בקוד היה
VARCHAR(20) — קצר מדי לערך החדש `ASSISTANT_PENDING_NOAH` (22 תווים)
שהוסף ב-F-09. שמירה היתה נכשלת עם data too long ב-INSERT/UPDATE.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "leads",
        "waiting_on",
        existing_type=sa.String(length=20),
        type_=sa.String(length=30),
        existing_nullable=False,
        existing_server_default="NOAH",
    )


def downgrade() -> None:
    # שחזור ל-VARCHAR(20). אם יש שורות עם ערך > 20 תווים (למשל
    # ASSISTANT_PENDING_NOAH), PostgreSQL יזרוק שגיאה ידידותית — מצופה,
    # כי downgrade מעבר לגרסה שלא תומכת בערך זה דורש backfill ידני.
    op.alter_column(
        "leads",
        "waiting_on",
        existing_type=sa.String(length=30),
        type_=sa.String(length=20),
        existing_nullable=False,
        existing_server_default="NOAH",
    )
