"""סכמות לאינטגרציית Google Calendar."""

from datetime import datetime

from pydantic import BaseModel


class GoogleConnectionStatus(BaseModel):
    """מצב החיבור הנוכחי ל-Google Calendar — לתצוגה ב-/settings."""

    connected: bool
    # מלאים רק אם connected=True
    google_account_email: str | None = None
    calendar_id: str | None = None
    timezone: str | None = None
    connected_at: datetime | None = None
    # True אם הtoken פג ולא ניתן ל-refresh — דורש re-auth
    auth_invalid: bool = False


class GoogleAuthStartResponse(BaseModel):
    """כתובת ה-OAuth של Google שאליה ה-frontend צריך להפנות את הbrowser."""

    auth_url: str
