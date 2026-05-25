"""סכמות לאינטגרציית Gmail (Phase 3 Stage 17)."""

from datetime import datetime

from pydantic import BaseModel


class GmailConnectionStatus(BaseModel):
    """מצב החיבור הנוכחי ל-Gmail — לתצוגה ב-/settings."""

    connected: bool
    # מלאים רק אם connected=True
    google_account_email: str | None = None
    history_id: str | None = None
    watch_expiration: datetime | None = None
    # התווית הנוכחית מ-config (Spec §20.11). מוצג ב-UI כדי שנועה תראה
    # איזה label תופעל ע"י classifier בעתיד.
    filter_label_name: str | None = None
    connected_at: datetime | None = None
    # True אם הtoken פג ולא ניתן ל-refresh — דורש re-auth
    auth_invalid: bool = False


class GmailAuthStartResponse(BaseModel):
    """כתובת ה-OAuth של Gmail שאליה ה-frontend צריך להפנות את הbrowser."""

    auth_url: str
