"""
Routes לadmin של פגישות — צפייה וביטול ע"י נועה/עוזרת.
שונה מ-routes/booking_page.py שמשרת את הדף הציבורי לליד.

**מה השתנה:** `/pending`, `/{id}/approve` ו-`/{id}/reject` נמחקו יחד עם
שלב האישור — פגישה נקבעת מאושרת מיד. במקומם `/{id}/cancel`, ו-
`/lead/{lead_id}` שמחזיר **רשימה** (ליד יכול להחזיק כמה פגישות).

הרשאה: CurrentUser — גם owner וגם assistant.
"""

from uuid import UUID

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.schemas.booking import BookingRead
from app.services import booking as booking_service

router = APIRouter(prefix="/bookings", tags=["bookings"])


@router.get("/lead/{lead_id}", response_model=list[BookingRead])
async def list_for_lead(
    lead_id: UUID, db: DbSession, _user: CurrentUser
) -> list[BookingRead]:
    """הפגישות של הליד שכרטיס הליד מציג — עתידיות + אחת שהסתיימה זה עתה
    (כדי שכפתור "סמני שהפגישה התקיימה" יישאר זמין). מוין בסדר עולה."""
    rows = await booking_service.get_bookings_for_lead(db, lead_id)
    return [BookingRead.model_validate(b, from_attributes=True) for b in rows]


@router.post("/{booking_id}/cancel", response_model=BookingRead)
async def cancel(
    booking_id: UUID, db: DbSession, user: CurrentUser
) -> BookingRead:
    """מבטל פגישה ומוחק את האירוע מיומן Google."""
    b = await booking_service.cancel_booking(
        db, booking_id=booking_id, performed_by_id=user.id
    )
    return BookingRead.model_validate(b, from_attributes=True)
