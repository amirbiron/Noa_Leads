"""
סכמות לadmin API של bookings — אישור/דחייה ע"י נועה.
שונה מ-schemas/booking_page.py שמשרת את הדף הציבורי לליד.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class BookingRead(BaseModel):
    """ייצוג booking לadmin UI."""

    id: UUID
    lead_id: UUID
    requested_slot_start: datetime
    requested_slot_end: datetime
    status: str
    google_calendar_event_id: str | None
    created_at: datetime
    approved_at: datetime | None
    rejected_at: datetime | None


class PendingBookingItem(BaseModel):
    """booking ב-pending_approval + מידע מינימלי על הליד לתצוגה ב-/pending."""

    id: UUID
    lead_id: UUID
    lead_name: str
    lead_phone: str | None
    service_category: str
    service_subtype: str | None
    requested_slot_start: datetime
    requested_slot_end: datetime
    created_at: datetime


class PendingBookingsResponse(BaseModel):
    items: list[PendingBookingItem]
