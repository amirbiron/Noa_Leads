"""lead.suggested_service_category/subtype — AI classification כהצעה לאישור.

עד היום: AI ב-Gmail intake הציב service_category + service_subtype ישירות
על ה-Lead כסיווג סופי. החל מהמיגרציה הזו, הסיווג של AI נשמר בשדות
suggested_* בלבד; ה-actual נשאר NULL עד שנועה מאשרת ידנית (banner UI בעמוד
הליד עם כפתורי "אישור" / "בחירה אחרת").

לידים קיימים: לא נוגעים — service_category הקיים שלהם נשאר כפי שהוא,
suggested_* נשאר NULL (אין banner). ההתנהגות החדשה חלה רק על לידים שיווצרו
מ-Gmail אחרי ה-deploy.

Index חלקי על leads עם suggested ממתינה — לסינון "ליד עם הצעת AI לאישור"
ב-dashboard עתידי.

Revision ID: 0031
Revises: 0030
Create Date: 2026-06-11
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0031"
down_revision: Union[str, None] = "0030"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "leads",
        sa.Column(
            "suggested_service_category",
            sa.String(length=50),
            nullable=True,
        ),
    )
    op.add_column(
        "leads",
        sa.Column(
            "suggested_service_subtype",
            sa.String(length=100),
            nullable=True,
        ),
    )
    # index חלקי — רק לידים עם הצעה ממתינה. תומך ב-dashboard query עתידי
    # "כל הלידים שדורשים אישור סיווג".
    op.create_index(
        "idx_leads_pending_suggestion",
        "leads",
        ["suggested_service_category"],
        postgresql_where=sa.text(
            "suggested_service_category IS NOT NULL AND service_category IS NULL"
        ),
    )


def downgrade() -> None:
    op.drop_index("idx_leads_pending_suggestion", table_name="leads")
    op.drop_column("leads", "suggested_service_subtype")
    op.drop_column("leads", "suggested_service_category")
