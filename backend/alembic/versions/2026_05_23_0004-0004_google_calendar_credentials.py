"""add google_calendar_credentials singleton

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-23

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # singleton — חיבור Google יחיד למערכת (נועה). CHECK(id=1) מבטיח שורה אחת.
    # ראה: docs/references/google-calendar-blueprint.md סעיף 8 (מבנה זהה).
    op.create_table(
        "google_calendar_credentials",
        sa.Column(
            "id",
            sa.Integer,
            primary_key=True,
            autoincrement=False,
        ),
        sa.Column("google_account_email", sa.String(255), nullable=False),
        sa.Column("calendar_id", sa.String(255), nullable=False, server_default="primary"),
        # tokens מוצפנים ב-Fernet (SECRETS_ENCRYPTION_KEY). אם המפתח לא
        # מוגדר ב-dev — נשמרים plaintext עם warning בלוג. בפרוד חובה.
        sa.Column("refresh_token_encrypted", sa.Text, nullable=False),
        sa.Column("access_token_encrypted", sa.Text, nullable=True),
        sa.Column("token_expiry", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "timezone", sa.String(64), nullable=False, server_default="Asia/Jerusalem"
        ),
        # סימון כשRefreshError קרה. ננקה אוטומטית בחיבור מחדש.
        sa.Column("auth_invalid_at", sa.DateTime(timezone=True), nullable=True),
        # מתי שלחנו לנועה התראה על נתק — מונע ספאם בכל ניסיון refresh.
        sa.Column("owner_alert_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("id = 1", name="ck_google_calendar_credentials_singleton"),
    )


def downgrade() -> None:
    op.drop_table("google_calendar_credentials")
