"""
Routes לadmin של bookings — list pending + approve/reject ע"י נועה/עוזרת.
שונה מ-routes/booking_page.py שמשרת את הדף הציבורי לליד.

הרשאה: CurrentUser — גם owner וגם assistant. עוזרת יכולה לאשר/לדחות
בשם נועה (זה מה שמייחד את ה-role הזה).
"""

from uuid import UUID

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.schemas.booking import (
    BookingRead,
    PendingBookingItem,
    PendingBookingsResponse,
)
from app.services import booking as booking_service

router = APIRouter(prefix="/bookings", tags=["bookings"])


@router.get("/pending", response_model=PendingBookingsResponse)
async def list_pending(
    db: DbSession, _user: CurrentUser
) -> PendingBookingsResponse:
    rows = await booking_service.list_pending_bookings(db)
    items = [
        PendingBookingItem(
            id=b.id,
            lead_id=l.id,
            lead_name=l.full_name,
            lead_phone=l.phone,
            service_category=l.service_category,
            service_subtype=l.service_subtype,
            requested_slot_start=b.requested_slot_start,
            requested_slot_end=b.requested_slot_end,
            created_at=b.created_at,
        )
        for b, l in rows
    ]
    return PendingBookingsResponse(items=items)


@router.get("/lead/{lead_id}/active", response_model=BookingRead | None)
async def get_active_for_lead(
    lead_id: UUID, db: DbSession, _user: CurrentUser
) -> BookingRead | None:
    """ה-booking הפעיל (pending_approval/approved, slot בעתיד) של ליד —
    משמש את דף הליד להציג כרטיס אישור."""
    b = await booking_service.get_active_booking_for_lead(db, lead_id)
    if b is None:
        return None
    return BookingRead.model_validate(b, from_attributes=True)


@router.post("/{booking_id}/approve", response_model=BookingRead)
async def approve(
    booking_id: UUID, db: DbSession, user: CurrentUser
) -> BookingRead:
    b = await booking_service.approve_booking(
        db, booking_id=booking_id, performed_by_id=user.id
    )
    return BookingRead.model_validate(b, from_attributes=True)


@router.post("/{booking_id}/reject", response_model=BookingRead)
async def reject(
    booking_id: UUID, db: DbSession, user: CurrentUser
) -> BookingRead:
    b = await booking_service.reject_booking(
        db, booking_id=booking_id, performed_by_id=user.id
    )
    return BookingRead.model_validate(b, from_attributes=True)
