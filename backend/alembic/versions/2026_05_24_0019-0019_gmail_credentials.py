"""gmail_credentials singleton table (Phase 3 Stage 17).

טבלה נפרדת מ-google_calendar_credentials. החלטת UX:
- scopes שונים (gmail.readonly+modify vs calendar.events)
- watch lifecycle שונה (Gmail max 7d עם history_id; Calendar ~30d עם sync_token)
- failure isolation — אם Gmail נשבר, Calendar ממשיך, ולהפך

מבנה זהה ברובו ל-google_calendar_credentials: singleton (CHECK id=1),
tokens מוצפנים ב-Fernet, watch fields, auth_invalid tracking.
תוספות ייחודיות ל-Gmail:
- history_id (במקום sync_token)
- filter_label_id + filter_label_name_cached — Spec §20.11 (תווית
  "סוננו אוטומטית" עם cache invalidation אם AI_FILTER_LABEL_NAME השתנה)

Revision ID: 0019
Revises: 0018
Create Date: 2026-05-24
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: Union[str, None] = "0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "gmail_credentials",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column(
            "google_account_email", sa.String(length=255), nullable=False
        ),
        sa.Column(
            "refresh_token_encrypted", sa.Text(), nullable=False
        ),
        sa.Column(
            "access_token_encrypted", sa.Text(), nullable=True
        ),
        sa.Column(
            "token_expiry", sa.DateTime(timezone=True), nullable=True
        ),
        # Watch + sync state. ב-Gmail, watch() לא מחזירה channel_id —
        # רק historyId + expiration. stop() לא דורשת id (עוצרת את כל
        # ה-watches של ה-user). אין שדה watch_channel_id (היה ב-Calendar).
        sa.Column("history_id", sa.String(length=50), nullable=True),
        sa.Column(
            "watch_expiration", sa.DateTime(timezone=True), nullable=True
        ),
        # Label caching (Spec §20.11)
        sa.Column("filter_label_id", sa.String(length=100), nullable=True),
        sa.Column(
            "filter_label_name_cached",
            sa.String(length=200),
            nullable=True,
        ),
        # Failure tracking
        sa.Column(
            "auth_invalid_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "owner_alert_sent_at", sa.DateTime(timezone=True), nullable=True
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
        sa.CheckConstraint("id = 1", name="ck_gmail_credentials_singleton"),
    )


def downgrade() -> None:
    op.drop_table("gmail_credentials")
