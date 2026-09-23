"""
Reverse sync — Google Calendar → DB.

הקורא (webhook) מקבל רשימת CalendarChange מ-google_calendar.sync_changes,
ומעביר אותה ל-apply_calendar_changes כאן. כל שינוי מתורגם לעדכון booking
+ ליד + activity log:

- אירוע נמחק / status=cancelled → booking ל-canceled, והליד חוזר
  ל-IN_PROGRESS עם waiting_on=NOAH — **אבל רק אם לא נשארה לו פגישה
  פעילה אחרת** (ליד יכול להחזיק כמה פגישות מאז מיגרציה 0032).
- שינוי זמן → עדכון slot_start/end ב-booking, activity log. ליד נשאר BOOKED.

החלטות שורש (לפי תכנון):
- שינוי שקט בלי התראה ל-Telegram — נועה היא שעשתה את השינוי, לא צריך להציק.
- ליד נשאר BOOKED גם אחרי שינוי זמן (זה עדיין booking פעיל באותו אובייקט).
- ביטול → IN_PROGRESS כדי שהליד יחזור לתור הטיפול של נועה. ההחלטה
  הזו מרוכזת ב-`booking.release_lead_if_no_active_booking`, שמשותף
  לשלושת מסלולי הביטול (Google, ביטול ידני, ו-cron הניקוי).
"""

from __future__ import annotations

import logging
from datetime import timezone
from typing import TYPE_CHECKING, Any

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import ActivityType, BookingCancelSource, BookingStatus
from app.models.booking import Booking
from app.services.activities import log_activity
from app.services.booking import (
    ACTIVE_BOOKING_STATUSES,
    release_lead_if_no_active_booking,
)

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
            Booking.status.in_(ACTIVE_BOOKING_STATUSES),
        )
        .values(status=BookingStatus.CANCELED.value)
    )
    applied = booking_update.rowcount == 1

    # ה-lead_id נדרש גם כשה-UPDATE לא תפס — כדי לרשום את ה-activity.
    # ה-status נשלף יחד איתו כדי להבחין בין שני מצבים שונים לגמרי
    # שמגיעים שניהם כ-`rowcount=0` (ראה למטה).
    existing = (
        await db.execute(
            select(Booking.lead_id, Booking.status).where(
                Booking.id == change.booking_id
            )
        )
    ).one_or_none()
    if existing is None:
        # ה-booking לא קיים בכלל (נמחק, או אירוע שלא שייך לנו) — אין
        # למי לרשום activity.
        await db.commit()
        return "skipped"
    lead_id, existing_status = existing

    # **פגישה מהקישור הפתוח אין לה ליד, ולכן אין לה ציר זמן.**
    #
    # `activities.lead_id` הוא NOT NULL, כלומר ניסיון לרשום activity
    # כאן היה מפיל את ה-webhook כולו — ואיתו את עיבוד כל שאר השינויים
    # באותה מנה. הביטול עצמו כן מוחל: השורה קיימת בדיוק כדי להחזיק את
    # המועד, ואם נועה מחקה את האירוע ביומן המועד חייב להתפנות.
    if lead_id is None:
        if applied:
            logger.info(
                "Open-link booking %s canceled from Google calendar",
                change.booking_id,
            )
        await db.commit()
        return "applied" if applied else "skipped"

    # **הד של ביטול שאנחנו עצמנו ביצענו — לא נרשם שוב.**
    #
    # `cancel_booking` ו-`close_lead` מוחקים את האירוע מ-Google אחרי
    # שהם מסמנים את הפגישה כמבוטלת ורושמים activity. Google מחזיר את
    # המחיקה הזו ב-webhook, ואז ה-UPDATE כאן לא תופס (הפגישה כבר
    # `canceled`) — כלומר **כל ביטול ידני היה מייצר שורה שנייה**
    # בציר הזמן של הליד, על אותו אירוע בדיוק.
    #
    # הרישום ב-`rowcount=0` (כלל 9) נשאר במקומו ונועד למצב אחר:
    # פגישה שעדיין לא מבוטלת אצלנו, ש-Google אומר שבוטלה. שם ה-
    # activity הוא המידע היחיד שמתעד שזה קרה.
    if not applied and existing_status == BookingStatus.CANCELED.value:
        await db.commit()
        return "skipped"

    # ליד חוזר ל-IN_PROGRESS — אבל **רק אם לא נשארה לו פגישה פעילה**.
    # ליד יכול להחזיק כמה פגישות; ביטול של אחת מהן לא אמור להוציא אותו
    # מ-BOOKED בזמן שהשנייה עומדת ביומן. הגארד המשותף עושה את זה
    # במשפט UPDATE אחד עם NOT EXISTS (בלי check-then-act).
    if applied:
        await release_lead_if_no_active_booking(db, lead_id)

    # event_updated_at = הזמן ב-Google שבו האירוע שונה (לא זמן עיבוד
    # webhook). חשוב ל-post_meeting_cron: ביטול שקרה לפני slot_end אומר
    # שהפגישה לא התקיימה, גם אם ה-webhook התעכב.
    #
    # `applied` נרשם תמיד (כלל 9 / Pattern 9): כשה-UPDATE לא תפס — כי
    # webhook מקביל או ביטול ידני הקדימו אותנו — ה-activity עדיין מתעד
    # את מה ש-Google אמר. הגרסה הקודמת חזרה כאן בשקט בלי לרשום כלום,
    # וצרכנים downstream לא ידעו שהאירוע בוטל בכלל.
    cancel_metadata: dict[str, Any] = {
        "booking_id": str(change.booking_id),
        "event_id": change.event_id,
        "source": BookingCancelSource.GOOGLE_SYNC.value,
        "applied": applied,
    }
    if change.updated_at is not None:
        cancel_metadata["event_updated_at"] = change.updated_at.isoformat()

    await log_activity(
        db,
        lead_id=lead_id,
        activity_type=ActivityType.MEETING_CANCELED,
        performed_by=None,  # שינוי שמקורו ב-Google, לא משתמש מחובר
        content=(
            "הפגישה בוטלה מיומן Google"
            if applied
            else "ביטול מ-Google דולג — הפגישה כבר לא הייתה פעילה"
        ),
        metadata=cancel_metadata,
    )

    await db.commit()
    if not applied:
        return "skipped"

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
    old_start = booking.requested_slot_start
    old_end = booking.requested_slot_end
    old_start_iso = old_start.isoformat()
    old_end_iso = old_end.isoformat()
    booking_lead_id = booking.lead_id  # cache למקרה של exception

    # פגישה מהקישור הפתוח — אין ליד ולכן אין ציר זמן לרשום אליו
    # (`activities.lead_id` הוא NOT NULL). ה-UPDATE על המועד כן מוחל:
    # אם נועה הזיזה את האירוע ביומן, המועד החדש הוא זה שצריך להחזיק
    # את הסלוט, אחרת הישן נשאר חסום והחדש נראה פנוי.
    if booking_lead_id is None:
        update_result = await db.execute(
            update(Booking)
            .where(
                Booking.id == change.booking_id,
                Booking.google_calendar_event_id == change.event_id,
                Booking.status.in_(ACTIVE_BOOKING_STATUSES),
                Booking.requested_slot_start == old_start,
                Booking.requested_slot_end == old_end,
            )
            .values(requested_slot_start=new_start, requested_slot_end=new_end)
        )
        await db.commit()
        return "applied" if update_result.rowcount == 1 else "skipped"

    # WHERE כולל סטטוסים פעילים *וגם* הערכים הישנים של start/end —
    # optimistic locking. אם webhook מקביל הקדים אותנו ושינה את ה-slot,
    # ה-UPDATE שלנו לא ימצא שורה (rowcount=0). דפוס שמחליף "להחזיק FOR
    # UPDATE על פני apply" בלי לדרוש single-transaction.
    try:
        update_result = await db.execute(
            update(Booking)
            .where(
                Booking.id == change.booking_id,
                Booking.google_calendar_event_id == change.event_id,
                Booking.status.in_(ACTIVE_BOOKING_STATUSES),
                Booking.requested_slot_start == old_start,
                Booking.requested_slot_end == old_end,
            )
            .values(requested_slot_start=new_start, requested_slot_end=new_end)
        )
        applied = update_result.rowcount == 1

        # רושמים activity גם ב-rowcount=0 (race) — ה-activity משקף את
        # *Google's view* של הפגישה, לא את מה ש-DB הצליח לכתוב. post_meeting
        # cron מסתמך על metadata.new_end כסיגנל המוקדם ביותר על reschedule
        # לעתיד. בלי הרישום, race יכול להשאיר booking.requested_slot_end
        # ישן בעבר וה-cron יוצר task מוקדם מדי.
        log_metadata = {
            "booking_id": str(change.booking_id),
            "event_id": change.event_id,
            "old_start": old_start_iso,
            "old_end": old_end_iso,
            "new_start": new_start.isoformat(),
            "new_end": new_end.isoformat(),
            "source": "google_calendar_sync",
            "applied": applied,
        }
        if change.updated_at is not None:
            log_metadata["event_updated_at"] = change.updated_at.isoformat()

        await log_activity(
            db,
            lead_id=booking_lead_id,
            activity_type=ActivityType.MEETING_RESCHEDULED,
            performed_by=None,
            content=(
                "מועד הפגישה עודכן ביומן Google"
                if applied
                else "עדכון מועד מ-Google דולג (race) — booking עודכן ע\"י סנכרון מקביל"
            ),
            metadata=log_metadata,
        )

        await db.commit()
        if not applied:
            return "skipped"
    except IntegrityError:
        # EXCLUDE constraint דחה — המועד החדש חופף ל-booking פעיל אחר. אי
        # אפשר לייצג זאת ב-DB (overlap = double booking). מחזירים "skipped"
        # *לא* errors — אחרת sync_token לא יתקדם ונתקעים על אותו change
        # לנצח (השגיאה קבועה, לא transient). נועה תקבל activity להתערבות.
        await db.rollback()
        logger.warning(
            "Reschedule for booking %s blocked by overlap constraint "
            "(conflicts with another active booking) — manual intervention needed",
            change.booking_id,
        )
        try:
            await log_activity(
                db,
                lead_id=booking_lead_id,
                activity_type=ActivityType.MEETING_RESCHEDULED,
                performed_by=None,
                content=(
                    "מועד הפגישה ביומן Google שונה אבל מתנגש עם פגישה פעילה "
                    "אחר במערכת — לא ניתן לסנכרן אוטומטית. בדקי ידנית."
                ),
                metadata={
                    "booking_id": str(change.booking_id),
                    "event_id": change.event_id,
                    "old_start": old_start_iso,
                    "old_end": old_end_iso,
                    "attempted_new_start": new_start.isoformat(),
                    "attempted_new_end": new_end.isoformat(),
                    "source": "google_calendar_sync",
                    "conflict": True,
                },
            )
            await db.commit()
        except Exception:
            logger.exception("Failed to log reschedule conflict activity")
            await db.rollback()
        return "skipped"

    logger.info(
        "Booking %s rescheduled via Google Calendar sync: %s → %s",
        change.booking_id,
        old_start_iso,
        new_start.isoformat(),
    )
    return "rescheduled"
