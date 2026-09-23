"""
Routes ציבוריים לדף קביעת תור (/book/{token}).

אין auth — הליד מקבל את ה-URL ישירות מנועה ויש לו את הטוקן.
ה-token עצמו (UUID) משמש כ-credential — מי שיש לו, יכול לראות + ליצור.
"""

import asyncio
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Query

from app.api.deps import DbSession
from app.schemas.booking_page import (
    AvailabilityResponse,
    BookingPageInfo,
    CreateBookingRequest,
    CreateBookingResponse,
    CreateOpenBookingRequest,
    OpenBookingPageInfo,
    OpenBookingResponse,
)
from app.services import booking as booking_service
from app.utils.rate_limit import SlidingWindowLimiter

router = APIRouter(prefix="/booking", tags=["booking"])

# מגבלת קצב ליצירת פגישה. אותו פרופיל חשיפה כמו `/auth/public-access`:
# ציבורי, לא מאומת, וכותב גם ל-DB וגם ליומן Google. 20 לדקה גבוה
# מאוד לשימוש אמיתי (לקוח קובע פגישה אחת) ועוצר סקריפט.
# גלובלית ולא לפי IP — ההסבר ב-`app/utils/rate_limit.py`.
_create_booking_limiter = SlidingWindowLimiter(max_events=20, window_seconds=60)

# מכסה **נפרדת** לקישור הפתוח. שתי מכסות ולא אחת משותפת, כדי שפרץ על
# הקישור הציבורי לא יאכל את המכסה של לידים שמחזיקים טוקן אישי — ולהפך.
_open_booking_limiter = SlidingWindowLimiter(max_events=20, window_seconds=60)
_open_availability_limiter = SlidingWindowLimiter(
    max_events=60, window_seconds=60
)

# תקרת בו-זמניות לקביעת פגישה — נפרדת ממגבלת הקצב, כי היא מגינה על
# משאב אחר לגמרי.
#
# המסלול הזה מחזיק חיבור מה-pool **ונעילת שורה** על הליד לאורך שתי
# קריאות ל-Google (בדיקת busy חוזרת + יצירת האירוע), כל אחת עד 10
# שניות. ה-pool הוא `pool_size=5 + max_overflow=10` = 15 חיבורים
# לכל האפליקציה. מגבלת הקצב מתירה 20 בקשות בדקה — אבל לא אומרת כלום
# על כמה מהן בו-זמנית, ולכן פרץ של 15 על endpoint **לא מאומת** היה
# תופס את כל ה-pool ל-20 שניות, ומשתק גם את הדשבורד של נועה.
#
# 4 משאיר לפחות 11 חיבורים לשאר האפליקציה בכל רגע. מי שלא נכנס מקבל
# 503 בעברית ולא ממתין ללא גבול — תור ארוך על נתיב ציבורי הוא אותה
# בעיה בלבוש אחר.
_BOOKING_CONCURRENCY = 4
_booking_slots = asyncio.Semaphore(_BOOKING_CONCURRENCY)
_ACQUIRE_TIMEOUT_SECONDS = 2


# ===== הקישור הפתוח =====
#
# שלושה routes שמקבילים אחד-לאחד לשלושה של הליד: מידע לדף, זמינות,
# וקביעה — רק בלי token.
#
# **הסדר כאן משמעותי.** הם חייבים להירשם *לפני* `/{token}`, אחרת FastAPI
# מנסה להתאים `/booking/open` לתבנית `/booking/{token}` — ומכיוון ש-
# `token` מוטפס כ-UUID, התוצאה היא 422 ולא נפילה ל-route הבא. אומת
# בבקשה אמיתית. מקור: fastapi.tiangolo.com/tutorial/path-params/#order-matters


@router.get("/open", response_model=OpenBookingPageInfo)
async def get_open_page_info() -> OpenBookingPageInfo:
    # בלי מגבלת קצב, כמו `GET /{token}`: חישוב תאריכים בלבד — בלי DB
    # ובלי קריאה ל-Google — כך שאין כאן משאב שאפשר להעמיס.
    return booking_service.get_open_booking_page_info()


@router.get("/open/availability", response_model=AvailabilityResponse)
async def get_open_availability(
    db: DbSession,
    date_from: date = Query(...),
    date_to: date = Query(...),
) -> AvailabilityResponse:
    _open_availability_limiter.check()
    days, includes_google = await booking_service.get_open_availability(
        db, date_from, date_to
    )
    return AvailabilityResponse(days=days, includes_google_busy=includes_google)


@router.post("/open", response_model=OpenBookingResponse, status_code=201)
async def create_open_booking(
    payload: CreateOpenBookingRequest, db: DbSession
) -> OpenBookingResponse:
    _open_booking_limiter.check()
    # אותה תקרת בו-זמניות כמו המסלול של הליד, ובכוונה **משותפת**: שני
    # המסלולים מתחרים על אותו pool חיבורים ועל אותן קריאות ל-Google,
    # ולכן מה שצריך להיות חסום הוא הסכום שלהם ולא כל אחד לחוד.
    try:
        await asyncio.wait_for(
            _booking_slots.acquire(), timeout=_ACQUIRE_TIMEOUT_SECONDS
        )
    except asyncio.TimeoutError:
        raise booking_service.CalendarTemporarilyUnavailable() from None
    try:
        return await booking_service.create_open_booking(
            db,
            full_name=payload.full_name,
            contact_phone=payload.contact_phone,
            slot_start=payload.slot_start,
            slot_end=payload.slot_end,
        )
    finally:
        _booking_slots.release()


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
    _create_booking_limiter.check()
    try:
        await asyncio.wait_for(
            _booking_slots.acquire(), timeout=_ACQUIRE_TIMEOUT_SECONDS
        )
    except asyncio.TimeoutError:
        raise booking_service.CalendarTemporarilyUnavailable() from None
    try:
        return await booking_service.create_booking_request(
            db,
            token=token,
            slot_start=payload.slot_start,
            slot_end=payload.slot_end,
            contact_phone=payload.contact_phone,
            notes=payload.notes,
        )
    finally:
        _booking_slots.release()
