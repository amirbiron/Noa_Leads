"""
שירות צ'יפים מהירים — CRUD לעמוד הגדרות + apply_chip לסיכום שיחה.

לפי Spec v2.1 §5.7 + §16.4. צ'יפ הוא declarative: כשנועה לוחצת עליו,
המערכת מבצעת 4 פעולות אטומיות לפי השדות שלו:
  1. ליד → target_status
  2. ליד.waiting_on → waiting_on
  3. יוצר task מסוג followup_task_type, due_at = now + auto_followup_days
  4. רושם activity
"""

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import (
    CLOSED_LEAD_STATUSES,
    ActivityType,
    BookingStatus,
    LeadStatus,
    TaskStatus,
)
from app.core.exceptions import NotFoundError, ValidationError
from app.models.booking import Booking
from app.models.lead import Lead
from app.models.quick_action_chip import QuickActionChip
from app.models.task import Task
from app.schemas.quick_action_chip import (
    QuickActionChipCreate,
    QuickActionChipUpdate,
)
from app.services.activities import log_activity
from app.services.lead_actions import AUTO_CLOSE_TASK_TYPES
from app.services.tasks import sync_lead_next_action_cache
from app.utils.work_hours import is_working_time, next_working_day_start

logger = logging.getLogger(__name__)


# ===== CRUD =====


async def list_chips(
    db: AsyncSession, *, active_only: bool = False
) -> list[QuickActionChip]:
    """
    כל הצ'יפים, ממוין לפי sort_order עולה.
    active_only=True — רק לתצוגה ב-QuickActions (לא בעמוד הגדרות).
    """
    stmt = select(QuickActionChip).order_by(
        QuickActionChip.sort_order.asc(), QuickActionChip.label.asc()
    )
    if active_only:
        stmt = stmt.where(QuickActionChip.is_active.is_(True))
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def create_chip(
    db: AsyncSession, payload: QuickActionChipCreate
) -> QuickActionChip:
    chip = QuickActionChip(
        label=payload.label,
        target_status=(
            str(payload.target_status) if payload.target_status else None
        ),
        waiting_on=(
            str(payload.waiting_on) if payload.waiting_on else None
        ),
        followup_task_type=(
            str(payload.followup_task_type)
            if payload.followup_task_type
            else None
        ),
        auto_followup_days=payload.auto_followup_days,
        sort_order=payload.sort_order,
        is_active=payload.is_active,
    )
    db.add(chip)
    await db.commit()
    await db.refresh(chip)
    return chip


async def update_chip(
    db: AsyncSession, chip_id: UUID, payload: QuickActionChipUpdate
) -> QuickActionChip:
    values = payload.model_dump(exclude_unset=True)
    if not values:
        return await _get_chip_or_404(db, chip_id)

    # Pydantic enums → str ב-DB.
    for key in ("target_status", "waiting_on", "followup_task_type"):
        if key in values and values[key] is not None:
            values[key] = str(values[key])

    result = await db.execute(
        update(QuickActionChip)
        .where(QuickActionChip.id == chip_id)
        .values(**values)
        .returning(QuickActionChip.id)
    )
    if result.scalar_one_or_none() is None:
        raise NotFoundError("צ'יפ לא נמצא.")
    await db.commit()
    return await _get_chip_or_404(db, chip_id)


async def delete_chip(db: AsyncSession, chip_id: UUID) -> None:
    result = await db.execute(
        delete(QuickActionChip)
        .where(QuickActionChip.id == chip_id)
        .returning(QuickActionChip.id)
    )
    if result.scalar_one_or_none() is None:
        raise NotFoundError("צ'יפ לא נמצא.")
    await db.commit()


async def _get_chip_or_404(
    db: AsyncSession, chip_id: UUID
) -> QuickActionChip:
    result = await db.execute(
        select(QuickActionChip)
        .where(QuickActionChip.id == chip_id)
        .execution_options(populate_existing=True)
    )
    chip = result.scalar_one_or_none()
    if chip is None:
        raise NotFoundError("צ'יפ לא נמצא.")
    return chip


# ===== Apply chip — סיכום שיחה ע"י לחיצה =====


def _calc_followup_due_at(now_utc: datetime, days: int) -> datetime:
    """
    due_at = now + days. אם נופל מחוץ לשעות עבודה (לילה/שבת/חג) — נדחה
    לתחילת יום העבודה הבא. עקבי עם _due_at_for_first_response.

    next_working_day_start מחזיר datetime ב-ISRAEL_TZ; ממירים ל-UTC כדי
    שכל ה-task.due_at בDB יהיו ב-UTC tz-aware אחיד (אחרת מיון/השוואות
    בין tasks משונות tz נשבר ב-postgres).
    """
    candidate = now_utc + timedelta(days=days)
    if not is_working_time(candidate):
        return next_working_day_start(candidate).astimezone(timezone.utc)
    return candidate


async def apply_chip(
    db: AsyncSession,
    *,
    lead_id: UUID,
    chip_id: UUID,
    performed_by: UUID | None,
) -> Lead:
    """
    מבצע את 4 פעולות הצ'יפ אטומית. F-01 + F-05 + F-23.

    שגיאות:
    - chip לא נמצא / לא active → 404 / 400.
    - chip חסר שדות סמנטיים (target_status/waiting_on/followup_task_type/days) → 400.
    - lead לא נמצא → 404.
    - lead סגור → 400 (F-23 guard ברמת ה-API).
    - ליד ב-BOOKING_PENDING/BOOKED עם בקשת תור פעילה + הצ'יפ משנה את
      הסטטוס → 400. אחרת הליד היה מאבד סינכרון עם היומן: BOOKING_PENDING
      היה נושר מ-/dashboard/pending (F-06); BOOKED היה משאיר Google
      Calendar event פעיל בלי context ב-CRM.
    """
    chip = await _get_chip_or_404(db, chip_id)
    if not chip.is_active:
        raise ValidationError("צ'יפ לא פעיל.")
    if (
        chip.target_status is None
        or chip.waiting_on is None
        or chip.followup_task_type is None
        or chip.auto_followup_days is None
    ):
        raise ValidationError(
            "הצ'יפ לא הוגדר במלואו. ערכי את אותו בהגדרות לפני שימוש."
        )

    # Defense in depth: chips שנוצרו לפני הוספת ה-validator ב-schema
    # (או דרך כתיבה ישירה ל-DB) לא יעקפו את ה-flows הייעודיים. השמירה
    # נעשית גם בschema של Create/Update + גם כאן בזמן apply.
    forbidden_targets = {
        LeadStatus.BOOKING_PENDING.value,
        LeadStatus.BOOKED.value,
        LeadStatus.WON.value,
        LeadStatus.LOST.value,
        LeadStatus.ARCHIVED.value,
    }
    if chip.target_status in forbidden_targets:
        raise ValidationError(
            "הצ'יפ מוגדר עם סטטוס שלא ניתן להציב דרך chip "
            "(תור / סגירה). השתמשי ב-flow הייעודי."
        )

    # Lead — חייב להיות פתוח. שליפה לבדיקה + הודעה ידידותית; ה-UPDATE
    # למטה מותנה שוב ב-status (defense-in-depth כנגד race עם close_lead).
    lead = (
        await db.execute(select(Lead).where(Lead.id == lead_id))
    ).scalar_one_or_none()
    if lead is None:
        raise NotFoundError("ליד לא נמצא.")
    closed_values = [s.value for s in CLOSED_LEAD_STATUSES]
    if lead.status in closed_values:
        raise ValidationError(
            "לא ניתן להפעיל צ'יפ על ליד סגור. פתחי אותו מחדש קודם."
        )

    # ליד ב-BOOKING_PENDING / BOOKED עם בקשת תור פעילה — chip apply חסום
    # *תמיד*, גם אם target_status שווה לסטטוס הנוכחי. למה: chip עדיין מעדכן
    # waiting_on, יוצר followup task, ומגדיר touchpoint — בזמן שיש בקשה
    # פעילה ביומן שדורשת טיפול ראשון (אישור/דחייה/ביטול). שינוי jbeg על
    # ליד כזה דורש קודם לסגור את הbooking דרך ה-UI הייעודי.
    #   - BOOKING_PENDING + pending_approval: הליד נושר מ-/dashboard/pending
    #     (F-06), הבקשה נשכחת.
    #   - BOOKED + approved: ה-Google Calendar event נשאר פעיל בלי context.
    blocking_booking_status: str | None = None
    if lead.status == LeadStatus.BOOKING_PENDING.value:
        blocking_booking_status = BookingStatus.PENDING_APPROVAL.value
    elif lead.status == LeadStatus.BOOKED.value:
        blocking_booking_status = BookingStatus.APPROVED.value

    if blocking_booking_status is not None:
        active_booking = (
            await db.execute(
                select(Booking.id)
                .where(
                    Booking.lead_id == lead_id,
                    Booking.status == blocking_booking_status,
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if active_booking is not None:
            if lead.status == LeadStatus.BOOKING_PENDING.value:
                raise ValidationError(
                    "יש בקשת תור הממתינה לאישור. אישרי או דחי אותה לפני הפעלת הצ'יפ."
                )
            raise ValidationError(
                "יש פגישה מאושרת בלוח. בטלי או דחי את הפגישה לפני הפעלת הצ'יפ."
            )

    now_utc = datetime.now(timezone.utc)
    due_at = _calc_followup_due_at(now_utc, chip.auto_followup_days)

    # אטומי בטרנזקציה אחת (אין commit לפני הסוף).
    # 1. UPDATE Lead — מותנה ב-status פתוח. אם race עם close_lead → rowcount=0
    #    ואנחנו עוצרים בלי לבצע את שאר הצעדים.
    #    last_outbound_at + last_activity_type נכתבים כי לחיצה על chip היא
    #    touchpoint לכל דבר (נועה דיברה עם הליד וסיכמה) — אחרת weekly
    #    "responded in time" + מיון הדשבורד לא יראו את הפעולה. לא נוגעים
    #    ב-last_inbound_at / reply_boost_until — אלה לאינטראקציה מהלקוח.
    update_values: dict = {
        "status": chip.target_status,
        "waiting_on": chip.waiting_on,
        "last_outbound_at": now_utc,
        "last_activity_type": ActivityType.CHIP_APPLIED.value,
        "updated_at": func.now(),
    }
    # Side-effect לסטטוס PROPOSAL_SENT: לקבוע proposal_sent_at אם עוד לא
    # נקבע. אחרת check_stuck_proposals לא יכיר את ההצעה ולא יוצר
    # proposal_followup, ו-/dashboard/proposals יציג days_since_proposal
    # לא תקין. COALESCE ב-DB משמרת תאריך הצעה מקורי אם נשלחה כבר.
    # מקביל ל-mark_proposal_sent ב-state_machine.
    if chip.target_status == LeadStatus.PROPOSAL_SENT.value:
        update_values["proposal_sent_at"] = func.coalesce(
            Lead.proposal_sent_at, now_utc
        )

    update_result = await db.execute(
        update(Lead)
        .where(Lead.id == lead_id, Lead.status.notin_(closed_values))
        .values(**update_values)
    )
    if update_result.rowcount != 1:
        await db.rollback()
        raise ValidationError(
            "מצב הליד השתנה תוך כדי הפעולה. רעני את הכרטיס ונסי שוב."
        )

    # 2a. De-dup: לחיצה חוזרת על אותו צ'יפ (או על צ'יפ אחר עם אותו
    #     followup_task_type) לא צריכה לערום משימות. ה-task הישן superseded
    #     ע"י הלחיצה הנוכחית — CANCELED (לא DONE, כי לא בוצע באמת).
    await db.execute(
        update(Task)
        .where(
            Task.lead_id == lead_id,
            Task.type == chip.followup_task_type,
            Task.status.in_(
                [TaskStatus.OPEN.value, TaskStatus.SNOOZED.value]
            ),
        )
        .values(status=TaskStatus.CANCELED.value)
    )

    # 2b. Touchpoint close: לחיצה על chip = נועה סיכמה שיחה, אז התזכורות
    #     לטיפול ראשוני / פולואפ / retry_call כבר לא רלוונטיות → DONE.
    #     מקביל ל-_close_addressed_tasks ב-lead_actions. מדלגים על
    #     followup_task_type של הצ'יפ עצמו — כבר טופל ב-2a.
    other_close_types = [
        t for t in AUTO_CLOSE_TASK_TYPES if t != chip.followup_task_type
    ]
    if other_close_types:
        await db.execute(
            update(Task)
            .where(
                Task.lead_id == lead_id,
                Task.type.in_(other_close_types),
                Task.status.in_(
                    [TaskStatus.OPEN.value, TaskStatus.SNOOZED.value]
                ),
            )
            .values(
                status=TaskStatus.DONE.value,
                completed_at=now_utc,
            )
        )

    # 2c. INSERT Task חדש. assigned_to=lead.owner_id עקבי עם
    # create_first_response_task / check_warm_followups / check_stuck_proposals
    # — כל ה-auto-created tasks מוקצים ל-owner של הליד.
    task = Task(
        lead_id=lead_id,
        type=chip.followup_task_type,
        assigned_to=lead.owner_id,
        status=TaskStatus.OPEN.value,
        due_at=due_at,
        origin_rule=f"chip:{chip.label}",
    )
    db.add(task)
    await db.flush()  # מקבל id ל-activity

    # 3. log activity
    await log_activity(
        db,
        lead_id=lead_id,
        activity_type=ActivityType.CHIP_APPLIED,
        performed_by=performed_by,
        content=chip.label,
        metadata={
            "chip_id": str(chip.id),
            "target_status": chip.target_status,
            "waiting_on": chip.waiting_on,
            "followup_task_type": chip.followup_task_type,
            "auto_followup_days": chip.auto_followup_days,
            "task_id": str(task.id),
            "due_at": due_at.isoformat(),
        },
    )

    # 4. sync next_action cache (כולל F-23 guard פנימי).
    await sync_lead_next_action_cache(db, lead_id)

    await db.commit()

    # שליפה מחודשת — ה-attributes של lead object עלולים להיות stale אחרי commit.
    refreshed = (
        await db.execute(select(Lead).where(Lead.id == lead_id))
    ).scalar_one()
    return refreshed
