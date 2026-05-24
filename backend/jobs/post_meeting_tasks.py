"""
post_meeting_tasks — רץ פעם ביום ב-02:00 (לפני expire_stale_bookings ב-03:30).

מייצר משימת POST_MEETING_UPDATE לכל ליד שעברה לו פגישה ב-48 השעות
האחרונות ועדיין לא נסגרה (WON/LOST) או טופלה ידנית, כדי שנועה תזכור
לעדכן מה היה — הצעה נשלחה? סגירה? פולואפ?

מקור הtrigger: bookings.requested_slot_end < now AND > now-48h, ושאישרו
אותם פעם ב-CRM (status=approved כרגע, או status=canceled אבל יש activity
MEETING_APPROVED עבור booking_id הזה — כלומר expire_stale_cron ניקה
booking שהפגישה שלו אכן התקיימה).

48h lookback = רשת בטחון ליום אחד פספוס (אם cron לא רץ או deploy יצא
באמצע).

מסנן ביטולים שמקורם ב-Google Calendar reverse sync (type=meeting_canceled,
source=google_calendar_sync) — שם הפגישה *לא* קרתה כי בוטלה ביומן.
שינויי זמן (meeting_rescheduled) דווקא כן מקבלים משימה — הפגישה התקיימה
במועד החדש.

dedup: dedup לפי lead_id לאחר השאילתה. ליד עם מספר bookings בחלון יקבל
משימה אחת בלבד. (race עם cron runs מקבילים לא רלוונטי כי Render
מבטיח run יחיד; וזה ה-caller היחיד של POST_MEETING_UPDATE.)
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import String, and_, cast, exists, func, not_, or_, select
from sqlalchemy.dialects import postgresql

from app.constants import (
    ActivityType,
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
        # ביטול מ-Google = הפגישה לא קרתה — אבל *רק* אם הביטול קרה לפני
        # מועד הפגישה. אם נועה מוחקת אירוע אחרי שהפגישה התקיימה (ניקיון
        # יומן), לא רוצים לדכא את ה-post_meeting task.
        #
        # זמן הביטול: עדיפות ל-event_updated_at ממטא-דאטה (זמן אמיתי
        # ב-Google), עם fallback ל-Activity.created_at למשימות ישנות
        # שנשמרו לפני שהשדה נוסף. coalesce חייב cast מפורש ל-timestamptz
        # כי astext מחזיר טקסט. ה-fallback פחות מדויק (סופג webhook delay)
        # אבל זה רק עד שכל ה-activities הישנות יוצאות מהחלון 48h.
        cancel_time = func.coalesce(
            cast(
                Activity.activity_metadata["event_updated_at"].astext,
                postgresql.TIMESTAMP(timezone=True),
            ),
            Activity.created_at,
        )
        google_canceled_subq = (
            select(Activity.id)
            .where(
                Activity.lead_id == Booking.lead_id,
                Activity.type == ActivityType.MEETING_CANCELED.value,
                Activity.activity_metadata["source"].astext
                == "google_calendar_sync",
                Activity.activity_metadata["booking_id"].astext
                == cast(Booking.id, String),
                cancel_time < Booking.requested_slot_end,
            )
            .correlate(Booking)
        )

        # reschedule לעתיד = הפגישה עוד לא התקיימה. ה-booking בשורה
        # עשוי להחזיק עדיין slot_end ישן (sync לא רץ עוד / webhook delay),
        # אבל ה-activity מ-MEETING_RESCHEDULED האחרון כן יחזיק את הזמן
        # החדש ב-metadata.
        #
        # COALESCE בין new_end (מסלול רגיל) ל-attempted_new_end (מסלול
        # שבו ה-UPDATE נכשל ב-IntegrityError — overlap עם booking אחר).
        # שני המקרים מסמנים reschedule אמיתי ב-Google. בלי הfallback,
        # conflict path היה משאיר NULL והguard היה עובר שגוי.
        #
        # חשוב: בודקים רק את ה-activity *האחרון* (ORDER BY created_at DESC
        # LIMIT 1). EXISTS על כל reschedule היה גורם לדיכוי שגוי כש-
        # reschedule מאוחר יותר החזיר את הslot לעבר (הפגישה כן קרתה).
        reschedule_end_text = func.coalesce(
            Activity.activity_metadata["new_end"].astext,
            Activity.activity_metadata["attempted_new_end"].astext,
        )
        latest_reschedule_new_end = (
            select(cast(reschedule_end_text, postgresql.TIMESTAMP(timezone=True)))
            .where(
                Activity.lead_id == Booking.lead_id,
                Activity.type == ActivityType.MEETING_RESCHEDULED.value,
                Activity.activity_metadata["source"].astext
                == "google_calendar_sync",
                Activity.activity_metadata["booking_id"].astext
                == cast(Booking.id, String),
            )
            .order_by(Activity.created_at.desc())
            .limit(1)
            .correlate(Booking)
            .scalar_subquery()
        )

        # זיהוי שbooking היה approved בעבר — דרך activity log. נדרש כדי
        # לא ליצור משימות עבור bookings ש-expire_stale ביטל בעודם
        # pending_approval (מעולם לא אושרו, הפגישה לא קרתה).
        ever_approved_subq = (
            select(Activity.id)
            .where(
                Activity.lead_id == Booking.lead_id,
                Activity.type == ActivityType.MEETING_APPROVED.value,
                Activity.activity_metadata["booking_id"].astext
                == cast(Booking.id, String),
            )
            .correlate(Booking)
        )

        # task שמקושר ל-booking הזה כבר נוצר ע"י cron זה = דילוג.
        # אינדמפוטנטיות per-booking (כל סטטוס: OPEN/DONE/CANCELED), אחרת
        # אחרי שנועה מסמנת done — הריצה הבאה בחלון 48h תיצור משימה כפולה
        # על אותה פגישה. ה-FK ל-booking_id (migration 0008) מאפשר dedup
        # מדויק: ליד עם 2 פגישות שונות בחלון מקבל 2 משימות נפרדות.
        existing_for_this_booking_subq = (
            select(Task.id)
            .where(
                Task.booking_id == Booking.id,
                Task.type == TaskType.POST_MEETING_UPDATE.value,
            )
            .correlate(Booking)
        )

        # status: approved (לרוב) או canceled אבל ever_approved (recovery
        # אחרי expire_stale שניקה). פעם pending_approval שנוקה אינו מתאים.
        approval_qualified = or_(
            Booking.status == BookingStatus.APPROVED.value,
            and_(
                Booking.status == BookingStatus.CANCELED.value,
                exists(ever_approved_subq),
            ),
        )

        stmt = (
            select(Booking.id, Booking.lead_id)
            .join(Lead, Lead.id == Booking.lead_id)
            .where(
                Booking.requested_slot_end > lookback,
                Booking.requested_slot_end < now_utc,
                approval_qualified,
                Lead.status.not_in(
                    [
                        LeadStatus.WON.value,
                        LeadStatus.LOST.value,
                        LeadStatus.ARCHIVED.value,
                    ]
                ),
                not_(exists(google_canceled_subq)),
                # latest reschedule (אם קיים) חייב להיות בעבר — אחרת
                # הפגישה עוד לא קרתה. None = אין reschedule כלל = ok.
                or_(
                    latest_reschedule_new_end.is_(None),
                    latest_reschedule_new_end <= now_utc,
                ),
                not_(exists(existing_for_this_booking_subq)),
            )
        )
        rows = (await db.execute(stmt)).all()

        if not rows:
            logger.info("No post-meeting tasks to create")
            return

        # יוצרים task per-booking. ה-dedup לפי booking_id ב-WHERE כבר
        # מבטיח שלא ניצור 2 משימות לאותה פגישה (גם בין riliki שונות).
        # ליד עם 2 פגישות שונות בחלון מקבל 2 משימות — כל פגישה דורשת
        # התייחסות נפרדת.
        from app.services.tasks import sync_lead_next_action_cache

        affected_lead_ids: set = set()
        for row in rows:
            db.add(
                Task(
                    lead_id=row.lead_id,
                    booking_id=row.id,
                    type=TaskType.POST_MEETING_UPDATE.value,
                    due_at=now_utc,  # יופיע מיד ב-/today
                    status=TaskStatus.OPEN.value,
                    origin_rule="post_meeting_cron",
                )
            )
            affected_lead_ids.add(row.lead_id)
        await db.flush()  # כדי שה-sync הבא יראה את ה-tasks שזה עתה נוספו

        # סנכרון cache עבור כל ליד שקיבל משימה חדשה
        for lead_id in affected_lead_ids:
            await sync_lead_next_action_cache(db, lead_id)
        await db.commit()

    logger.info("Created %d post-meeting tasks", len(rows))


if __name__ == "__main__":
    run_job("post_meeting_tasks", create_post_meeting_tasks)
