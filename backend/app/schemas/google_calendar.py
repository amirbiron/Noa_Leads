"""סכמות לאינטגרציית Google Calendar."""

from datetime import datetime

from pydantic import BaseModel, Field


class GoogleConnectionStatus(BaseModel):
    """מצב החיבור הנוכחי ל-Google Calendar — לתצוגה ב-/settings."""

    connected: bool
    # מלאים רק אם connected=True
    google_account_email: str | None = None
    # יומן היעד — היומן שאליו נכתבות הפגישות ושעליו רשום ה-watch.
    calendar_id: str | None = None
    # יומנים *נוספים* שנחשבים "תפוס" בחישוב הזמינות בלבד.
    busy_calendar_ids: list[str] = Field(default_factory=list)
    timezone: str | None = None
    connected_at: datetime | None = None
    # True אם הtoken פג ולא ניתן ל-refresh — דורש re-auth
    auth_invalid: bool = False


class CalendarListItem(BaseModel):
    """יומן אחד ברשימת היומנים של החשבון המחובר."""

    id: str
    summary: str
    primary: bool = False
    # freeBusyReader / reader / writer / owner — ה-UI משתמש בזה כדי
    # להציג אילו יומנים לא יכולים לשמש כיומן יעד (נדרשת כתיבה).
    access_role: str = ""


class CalendarListResponse(BaseModel):
    items: list[CalendarListItem]


class CalendarSelectionRequest(BaseModel):
    """בחירת היומנים ע"י נועה ב-/settings."""

    # היומן שאליו ייקבעו הפגישות. חייב להיות יומן עם הרשאת כתיבה.
    target_calendar_id: str = Field(min_length=1, max_length=255)
    # יומנים נוספים שייחשבו "תפוס". היעד עצמו תמיד נחשב תפוס ולא חייב
    # להופיע כאן. התקרה נגזרת ממגבלת FreeBusy של Google (50 יומנים
    # לשאילתה), פחות היעד עצמו.
    busy_calendar_ids: list[str] = Field(default_factory=list, max_length=49)


class GoogleAuthStartResponse(BaseModel):
    """כתובת ה-OAuth של Google שאליה ה-frontend צריך להפנות את הbrowser."""

    auth_url: str
