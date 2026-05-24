"""
post_meeting_tasks — רץ פעם ביום ב-02:00 (לפני expire_stale_bookings ב-03:30).

מייצר משימת POST_MEETING_UPDATE לכל ליד שעברה לו פגישה ב-24 השעות
האחרונות ועדיין לא נסגרה (WON/LOST) או טופלה ידנית, כדי שנועה תזכור
לעדכן מה היה — הצעה נשלחה? סגירה? פולואפ?

מקור הtrigger: bookings.requested_slot_end < now AND > now-48h, status
ב-(approved, canceled) — כולל canceled מ-expire_stale_cron (אם הריצה
הקודמת פספסה את החלון, ה-booking כבר נוקה אבל הפגישה אכן התקיימה).

מסנן ביטולים מ-Google Calendar (reverse sync) — שם הפגישה *לא* קרתה,
אין מה לעדכן.

אינדמפוטנטי דרך NOT EXISTS task פתוח לאותו ליד.
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import String, cast, exists, not_, select

from app.constants import (
    BookingStatus,
    LeadStatus,
    TaskStatus,
    TaskType,
)
from app.db.session import AsyncSessionLocal
from app.models.activity import Activity
from app.models.booking import Booking
from app.models.lead import Lead
from app.models.task import Task
from jobs._runner import run_job

logger = logging.getLogger("jobs.post_meeting_tasks")


# כמה זמן אחורה לסרוק. 48h נותן רשת בטחון של יום אחד פספוס (אם cron לא רץ).
_LOOKBACK_HOURS = 48


async def create_post_meeting_tasks() -> None:
    now_utc = datetime.now(timezone.utc)
    lookback = now_utc - timedelta(hours=_LOOKBACK_HOURS)

    async with AsyncSessionLocal() as db:
        # ביטול מ-Google = הפגישה לא קרתה. סינון לפי metadata של ה-activity.
        google_canceled_subq = (
            select(Activity.id)
            .where(
                Activity.lead_id == Booking.lead_id,
                Activity.activity_metadata["source"].astext
                == "google_calendar_sync",
                Activity.activity_metadata["booking_id"].astext
                == cast(Booking.id, String),
            )
            .correlate(Booking)
        )

        # task פתוח כבר קיים = דילוג (אינדמפוטנטיות).
        existing_task_subq = (
            select(Task.id)
            .where(
                Task.lead_id == Booking.lead_id,
                Task.type == TaskType.POST_MEETING_UPDATE.value,
                Task.status.in_(
                    [TaskStatus.OPEN.value, TaskStatus.SNOOZED.value]
                ),
            )
            .correlate(Booking)
        )

        # סינון leads שכבר נסגרו — לא מעניין לבקש post-meeting על ליד שהפך
        # WON/LOST/ARCHIVED בהליך אחר (לא מ-cron של expire_stale).
        stmt = (
            select(Booking.id, Booking.lead_id)
            .join(Lead, Lead.id == Booking.lead_id)
            .where(
                Booking.requested_slot_end > lookback,
                Booking.requested_slot_end < now_utc,
                Booking.status.in_(
                    [
                        BookingStatus.APPROVED.value,
                        BookingStatus.CANCELED.value,
                    ]
                ),
                Lead.status.not_in(
                    [
                        LeadStatus.WON.value,
                        LeadStatus.LOST.value,
                        LeadStatus.ARCHIVED.value,
                    ]
                ),
                not_(exists(google_canceled_subq)),
                not_(exists(existing_task_subq)),
            )
        )
        rows = (await db.execute(stmt)).all()

        if not rows:
            logger.info("No post-meeting tasks to create")
            return

        for row in rows:
            db.add(
                Task(
                    lead_id=row.lead_id,
                    type=TaskType.POST_MEETING_UPDATE.value,
                    due_at=now_utc,  # יופיע מיד ב-/today
                    status=TaskStatus.OPEN.value,
                    origin_rule="post_meeting_cron",
                )
            )
        await db.commit()

    logger.info("Created %d post-meeting tasks", len(rows))


if __name__ == "__main__":
    run_job("post_meeting_tasks", create_post_meeting_tasks)
