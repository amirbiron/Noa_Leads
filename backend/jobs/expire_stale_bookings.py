"""
expire_stale_bookings — רץ פעם ביום (מומלץ 03:30).

מבטל אוטומטית bookings שהסלוט שלהם עבר אבל הסטטוס נשאר
pending_approval/approved (למשל פגישה שנועה לא אישרה/דחתה במועד),
ומאפס סטטוס leads שתקועים ב-BOOKING_PENDING/BOOKED בלי תור פעיל.

שלב 14 (סנכרון הפוך) ושלב 15 (post-meeting) מצמצמים את התרחיש אבל לא
מבטלים אותו — webhook יכול להחמיץ ימים אם backend down, ופגישה שעברה
בלי שנועה עדכנה ידנית עדיין נשארת BOOKED. ה-cron הזה הוא רשת בטחון.
"""

import logging

from app.db.session import AsyncSessionLocal
from app.services import booking as booking_service
from jobs._runner import run_job

logger = logging.getLogger("jobs.expire_stale_bookings")


async def expire_stale() -> None:
    async with AsyncSessionLocal() as db:
        count = await booking_service.expire_all_stale_bookings(db)
    logger.info("Expired %d stale bookings", count)


if __name__ == "__main__":
    run_job("expire_stale_bookings", expire_stale)
