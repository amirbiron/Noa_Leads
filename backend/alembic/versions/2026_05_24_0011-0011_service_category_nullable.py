"""make leads.service_category nullable (F-04)

Revision ID: 0011
Revises: 0010
Create Date: 2026-05-24

לפי Spec §7.1: שדות חובה ביצירת ליד הם רק שם/טלפון/מקור. service_category
היה NOT NULL בקוד אבל אופציונלי בSpec. ראה F-04 ב-docs/spec-deviations.md.

לידים קיימים עם ערך נשארים כמו שהם — רק מוסר ה-constraint NOT NULL.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "leads",
        "service_category",
        existing_type=sa.String(length=50),
        nullable=True,
    )


def downgrade() -> None:
    # זהירות: ב-downgrade, אם יש לידים עם NULL ב-service_category,
    # ה-ALTER יכשל. מי שצריך downgrade ידאג לזה ידנית.
    op.alter_column(
        "leads",
        "service_category",
        existing_type=sa.String(length=50),
        nullable=False,
    )
