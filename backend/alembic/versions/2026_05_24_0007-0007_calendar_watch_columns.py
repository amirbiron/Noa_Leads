"""add watch channel + sync token columns to google_calendar_credentials

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-24

תומך בסנכרון הפוך (Google → DB) דרך watch channels + syncToken.

- sync_token: ה-nextSyncToken האחרון. None = צריך full re-sync (אחרי 410).
- watch_channel_id: UUID שיצרנו, נשלח חזרה ע"י Google ב-X-Goog-Channel-Id.
- watch_resource_id: זיהוי שמחזיר Google ביצירת ה-channel — נדרש ל-channels.stop.
- watch_expiration: מתי ה-channel פג. cron מחדש מבעוד מועד.
- watch_token_encrypted: shared secret שיצרנו ונשלח חזרה ע"י Google ב-X-Goog-Channel-Token.
  מאחסנים מוצפן כי זה credential להאמתת webhook (Fernet, כמו refresh_token).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "google_calendar_credentials",
        sa.Column("sync_token", sa.Text(), nullable=True),
    )
    op.add_column(
        "google_calendar_credentials",
        sa.Column("watch_channel_id", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "google_calendar_credentials",
        sa.Column("watch_resource_id", sa.String(length=200), nullable=True),
    )
    op.add_column(
        "google_calendar_credentials",
        sa.Column(
            "watch_expiration",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "google_calendar_credentials",
        sa.Column("watch_token_encrypted", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("google_calendar_credentials", "watch_token_encrypted")
    op.drop_column("google_calendar_credentials", "watch_expiration")
    op.drop_column("google_calendar_credentials", "watch_resource_id")
    op.drop_column("google_calendar_credentials", "watch_channel_id")
    op.drop_column("google_calendar_credentials", "sync_token")
