"""
Routes ציבוריים לדף קביעת תור (/book/{token}).

אין auth — הליד מקבל את ה-URL ישירות מנועה ויש לו את הטוקן.
ה-token עצמו (UUID) משמש כ-credential — מי שיש לו, יכול לראות + ליצור.
"""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Query

from app.api.deps import DbSession
from app.schemas.booking_page import (
    AvailabilityResponse,
    BookingPageInfo,
    CreateBookingRequest,
    CreateBookingResponse,
)
from app.services import booking as booking_service

router = APIRouter(prefix="/booking", tags=["booking"])


@router.get("/{token}", response_model=BookingPageInfo)
async def get_page_info(token: UUID, db: DbSession) -> BookingPageInfo:
    return await booking_service.get_booking_page_info(db, token)


@router.get("/{token}/availability", response_model=AvailabilityResponse)
async def get_availability(
    token: UUID,
    db: DbSession,
    date_from: date = Query(...),
    date_to: date = Query(...),
) -> AvailabilityResponse:
    days, includes_google = await booking_service.get_availability(
        db, token, date_from, date_to
    )
    return AvailabilityResponse(days=days, includes_google_busy=includes_google)


@router.post("/{token}", response_model=CreateBookingResponse, status_code=201)
async def create_booking(
    token: UUID, payload: CreateBookingRequest, db: DbSession
) -> CreateBookingResponse:
    return await booking_service.create_booking_request(
        db,
        token=token,
        slot_start=payload.slot_start,
        slot_end=payload.slot_end,
        notes=payload.notes,
    )
