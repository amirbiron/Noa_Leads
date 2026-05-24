"""
Reverse sync — Google Calendar → DB.

הקורא (webhook) מקבל רשימת CalendarChange מ-google_calendar.sync_changes,
ומעביר אותה ל-apply_calendar_changes כאן. כל שינוי מתורגם לעדכון booking
+ ליד + activity log:

- אירוע נמחק / status=cancelled → booking ל-canceled, ליד חוזר ל-IN_PROGRESS
  עם waiting_on=NOAH (החלטה בתכנון שלב 14).
- שינוי זמן → עדכון slot_start/end ב-booking, activity log. ליד נשאר BOOKED.

החלטות שורש (לפי תכנון):
- שינוי שקט בלי התראה ל-Telegram — נועה היא שעשתה את השינוי, לא צריך להציק.
- ליד נשאר BOOKED גם אחרי שינוי זמן (זה עדיין booking פעיל באותו אובייקט).
- ביטול → IN_PROGRESS כדי שהליד יחזור לתור הטיפול של נועה.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import (
    ActivityType,
    BookingStatus,
    LeadStatus,
    WaitingOn,
)
from app.models.booking import Booking
from app.models.lead import Lead
from app.services.activities import log_activity

if TYPE_CHECKING:
    from app.services.google_calendar import CalendarChange

logger = logging.getLogger(__name__)


async def apply_calendar_changes(
    db: AsyncSession, changes: "list[CalendarChange]"
) -> dict[str, int]:
    """
    מטמיע רשימת שינויים מ-Google ב-DB. מחזיר ספירה של מה הוחל.

    כל שינוי מטופל בלולאה — שגיאה בשינוי אחד לא מפילה את האחרים (לוג +
    המשך), כדי שwebhook אחד עם 10 שינויים לא ייכשל בכולם בגלל אחד פגום.
    """
    stats = {"canceled": 0, "rescheduled": 0, "skipped": 0, "errors": 0}

    for change in changes:
        try:
            if change.status == "cancelled":
                applied = await _apply_cancellation(db, change)
            elif change.start and change.end:
                applied = await _apply_reschedule(db, change)
            else:
                # status confirmed אבל אין start/end (all-day או נתון חסר) — דילוג
                applied = "skipped"

            stats[applied] += 1
        except Exception:
            logger.exception(
                "Failed to apply calendar change for booking %s (event %s)",
                change.booking_id,
                change.event_id,
            )
            # rollback קריטי — אחרת ה-session נשאר במצב transaction
            # פתוח/שגוי, וה-change הבא בלולאה ייכשל גם הוא (או יקבל
            # שגיאת PendingRollbackError). השגיאה הראשונית כבר מתועדת.
            try:
                await db.rollback()
            except Exception:
                logger.exception("rollback failed after apply error")
            stats["errors"] += 1

    return stats


async def _apply_cancellation(
    db: AsyncSession, change: "CalendarChange"
) -> str:
    """
    ביטול אירוע ב-Google. WHERE כולל סטטוסים שלא-canceled (אטומי) ומאמת
    שה-event_id תואם כדי לא לבטל booking שמשויך לאירוע אחר באותו ליד.
    """
    booking_update = await db.execute(
        update(Booking)
        .where(
            Booking.id == change.booking_id,
            Booking.google_calendar_event_id == change.event_id,
            Booking.status.in_(
                [
                    BookingStatus.PENDING_APPROVAL.value,
                    BookingStatus.APPROVED.value,
                ]
            ),
        )
        .values(status=BookingStatus.CANCELED.value)
    )
    if booking_update.rowcount != 1:
        # booking כבר נמחק/בוטל/שונה — אין מה לעשות. אינדמפוטנטי.
        await db.commit()
        return "skipped"

    booking = (
        await db.execute(
            select(Booking)
            .where(Booking.id == change.booking_id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()

    # ליד חוזר ל-IN_PROGRESS אם היה BOOKED. אם הליד כבר נסגר (WON/LOST) או
    # התקדם לאן שהוא — לא נוגעים.
    await db.execute(
        update(Lead)
        .where(
            Lead.id == booking.lead_id,
            Lead.status == LeadStatus.BOOKED.value,
        )
        .values(
            status=LeadStatus.IN_PROGRESS.value,
            waiting_on=WaitingOn.NOAH.value,
            last_activity_type=ActivityType.MEETING_CANCELED.value,
            updated_at=func.now(),
        )
    )

    await log_activity(
        db,
        lead_id=booking.lead_id,
        activity_type=ActivityType.MEETING_CANCELED,
        performed_by=None,  # שינוי שמקורו ב-Google, לא משתמש מחובר
        content="הפגישה בוטלה מיומן Google",
        metadata={
            "booking_id": str(change.booking_id),
            "event_id": change.event_id,
            "source": "google_calendar_sync",
        },
    )

    await db.commit()
    logger.info(
        "Booking %s canceled via Google Calendar sync", change.booking_id
    )
    return "canceled"


async def _apply_reschedule(
    db: AsyncSession, change: "CalendarChange"
) -> str:
    """
    שינוי זמן באירוע. אם הזמן לא באמת השתנה (אותם start/end) — דילוג שקט.
    """
    assert change.start is not None and change.end is not None

    booking = (
        await db.execute(
            select(Booking).where(
                Booking.id == change.booking_id,
                Booking.google_calendar_event_id == change.event_id,
            )
        )
    ).scalar_one_or_none()
    if booking is None:
        return "skipped"

    # נירמול ל-UTC להשוואה (DB מחזיק aware datetime ב-UTC)
    new_start = (
        change.start
        if change.start.tzinfo
        else change.start.replace(tzinfo=timezone.utc)
    )
    new_end = (
        change.end
        if change.end.tzinfo
        else change.end.replace(tzinfo=timezone.utc)
    )

    if booking.requested_slot_start == new_start and booking.requested_slot_end == new_end:
        return "skipped"

    # שמירה של הזמן הישן ל-activity לוג לפני ה-UPDATE
    old_start_iso = booking.requested_slot_start.isoformat()
    old_end_iso = booking.requested_slot_end.isoformat()

    # WHERE כולל סטטוסים פעילים בלבד — אם booking נסגר בinternal race, לא דורסים.
    update_result = await db.execute(
        update(Booking)
        .where(
            Booking.id == change.booking_id,
            Booking.google_calendar_event_id == change.event_id,
            Booking.status.in_(
                [
                    BookingStatus.PENDING_APPROVAL.value,
                    BookingStatus.APPROVED.value,
                ]
            ),
        )
        .values(requested_slot_start=new_start, requested_slot_end=new_end)
    )
    if update_result.rowcount != 1:
        await db.commit()
        return "skipped"

    await log_activity(
        db,
        lead_id=booking.lead_id,
        activity_type=ActivityType.MEETING_RESCHEDULED,
        performed_by=None,
        content="מועד הפגישה עודכן ביומן Google",
        metadata={
            "booking_id": str(change.booking_id),
            "event_id": change.event_id,
            "old_start": old_start_iso,
            "old_end": old_end_iso,
            "new_start": new_start.isoformat(),
            "new_end": new_end.isoformat(),
            "source": "google_calendar_sync",
        },
    )

    await db.commit()
    logger.info(
        "Booking %s rescheduled via Google Calendar sync: %s → %s",
        change.booking_id,
        old_start_iso,
        new_start.isoformat(),
    )
    return "rescheduled"
