"""
סכמות לדף קביעת תור הציבורי (/book/{token}).
"""

from datetime import date, datetime, timezone
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class BookingPageInfo(BaseModel):
    """מידע בסיסי לדף קביעת התור — מוצג ללקוח."""

    lead_name: str
    service_category: str | None  # אופציונלי (F-04)
    service_subtype: str | None
    default_duration_minutes: int
    timezone: str = "Asia/Jerusalem"
    # אם True — קיימת כבר בקשת תור פעילה ב-pending_approval/approved.
    # הUI יציג זאת ולא יאפשר בקשה חדשה.
    has_active_booking: bool = False
    active_booking_at: datetime | None = None
    active_booking_end: datetime | None = None
    active_booking_status: str | None = None


class TimeSlot(BaseModel):
    start: datetime
    end: datetime


class DayAvailability(BaseModel):
    date: date
    slots: list[TimeSlot]


class AvailabilityResponse(BaseModel):
    """תוצאת חישוב סלוטים פנויים בטווח תאריכים."""

    days: list[DayAvailability]
    # אם False — סלוטים מבוססים רק על שעות עבודה + DB busy (Google לא מחובר).
    # מודיע ל-UI שייתכן שסלוטים מסוימים יסתרו ביומן של נועה.
    includes_google_busy: bool


class CreateBookingRequest(BaseModel):
    slot_start: datetime
    slot_end: datetime
    # פרטים אופציונליים שהליד יכול לעדכן בעת הזמנה
    notes: str | None = Field(default=None, max_length=500)

    @field_validator("slot_start", "slot_end")
    @classmethod
    def must_be_tz_aware(cls, v: datetime) -> datetime:
        # חובה לכלול timezone offset — אחרת השוואה עם now_utc למטה תיכשל.
        # מנרמלים ל-UTC כדי להבטיח אחידות בכל הקוד.
        if v.tzinfo is None:
            raise ValueError(
                "תאריך/שעה חייבים לכלול אזור זמן (ISO 8601 עם offset)."
            )
        return v.astimezone(timezone.utc)


class CreateBookingResponse(BaseModel):
    booking_id: UUID
    status: str  # "pending_approval"
    slot_start: datetime
    slot_end: datetime

