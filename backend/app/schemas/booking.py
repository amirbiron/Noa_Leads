"""
סכמות לadmin API של פגישות — צפייה וביטול ע"י נועה.
שונה מ-schemas/booking_page.py שמשרת את הדף הציבורי לליד.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class BookingRead(BaseModel):
    """ייצוג פגישה לadmin UI."""

    id: UUID
    lead_id: UUID
    requested_slot_start: datetime
    requested_slot_end: datetime
    status: str
    google_calendar_event_id: str | None
    # הטלפון וההערה שהליד הזין בדף קביעת הפגישה. מוצגים בכרטיס הפגישה
    # כדי שנועה תוכל ליצור קשר בלי לחפש, ונכנסים גם לתיאור האירוע ביומן.
    contact_phone: str | None
    notes: str | None
    created_at: datetime
    approved_at: datetime | None
    rejected_at: datetime | None
