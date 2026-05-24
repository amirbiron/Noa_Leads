"""
ביצוע פעולות דינמיות על ליד (POST /leads/{id}/actions/{action_type}).

הלוגיקה המרכזית: מעבר סטטוס *אטומי* — UPDATE ... WHERE status IN (allowed_from).
זה מבטיח שגם אם שני משתמשים לוחצים בו-זמנית, רק אחד מצליח.
"""

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import OPEN_LEAD_STATUSES, LeadStatus, TaskStatus, TaskType
from app.core.exceptions import (
    InvalidStateTransitionError,
    NotFoundError,
    ValidationError,
)
from app.core.state_machine import ACTIONS, ActionDefinition
from app.models.lead import Lead
from app.services.activities import log_activity


# כמה זמן ליד נשאר "boosted" אחרי תגובה — קופץ לראש הדשבורד
REPLY_BOOST_HOURS = 24


def _resolve_action(action_type: str) -> ActionDefinition:
    action = ACTIONS.get(action_type)
    if action is None:
        raise ValidationError(f"פעולה לא מוכרת: {action_type}")
    return action


async def perform_action(
    db: AsyncSession,
    lead_id: UUID,
    action_type: str,
    *,
    current_user_id: UUID | None,
    content: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> Lead:
    """
    מבצע פעולה דינמית על ליד:
    1. ולידציה שהפעולה מוכרת ומותרת מסטטוס הליד הנוכחי.
    2. UPDATE אטומי על הליד עם השדות שהפעולה משנה.
    3. רישום activity ב-audit log.
    4. commit אחד לכל הפעולה.
    """
    action = _resolve_action(action_type)
    now = datetime.now(timezone.utc)

    # ===== הכנת UPDATE statement =====
    # שלב א': בונים values בלי updated_at — כדי לזהות פעולות "סטריליות"
    # כמו add_internal_note שלא צריכות לבמפ את מיון הדשבורד.
    # שלב ב' (בהמשך): אם יש לפחות שדה אחד אחר, מוסיפים updated_at=NOW()
    # כי onupdate של ORM לא מופעל ב-Core update().
    values: dict[str, Any] = {}
    if action.set_last_outbound:
        values["last_outbound_at"] = now
    if action.set_last_inbound:
        values["last_inbound_at"] = now
    if action.set_reply_boost:
        values["reply_boost_until"] = now + timedelta(hours=REPLY_BOOST_HOURS)
    if action.set_proposal_sent_at:
        values["proposal_sent_at"] = now
    if action.set_waiting_on:
        values["waiting_on"] = action.set_waiting_on
    if action.last_activity_tag:
        values["last_activity_type"] = action.last_activity_tag

    # ===== חישוב הסטטוס הבא =====
    # transition_to קודם כל. אחרת auto_progress: NEW → IN_PROGRESS.
    if action.transition_to is not None:
        target_status = action.transition_to.value
        # תנאי allowed_from
        if action.allowed_from is None:
            allowed_from = None
        else:
            allowed_from = [s.value for s in action.allowed_from]
        values["status"] = target_status
        atomic_update_needed = True

    elif action.auto_progress_from_new:
        # שני מסלולים: או שהסטטוס NEW (אז → IN_PROGRESS), או שהוא כבר התקדם (אז לא משנים)
        # ביצוע אטומי: ניסיון update עם status='NEW' → IN_PROGRESS,
        # אם נכשל, ננסה update בלי שינוי סטטוס.
        return await _perform_with_optional_progress(
            db,
            lead_id=lead_id,
            action=action,
            values=values,
            now=now,
            current_user_id=current_user_id,
            content=content,
            metadata=metadata,
        )

    else:
        # פעולה שלא מזיזה סטטוס (לדוגמה: add_internal_note).
        atomic_update_needed = bool(values)
        if action.allowed_from is not None:
            allowed_from = [s.value for s in action.allowed_from]
        elif values:
            # latent design safety: action בלי allowed_from שעדיין מעדכן שדות —
            # אסור לבצע על ליד סגור. fallback ל-OPEN_LEAD_STATUSES.
            allowed_from = [s.value for s in OPEN_LEAD_STATUSES]
        else:
            # אין values בכלל (add_internal_note) — מותר מכל סטטוס.
            allowed_from = None

    if not atomic_update_needed and not values:
        # add_internal_note — אין שינוי בליד, רק activity. בודקים שהליד קיים.
        await _ensure_lead_exists(db, lead_id)
        await log_activity(
            db,
            lead_id=lead_id,
            activity_type=action.activity_type,
            performed_by=current_user_id,
            content=content,
            metadata=metadata,
        )
        await db.commit()
        return await _get_lead(db, lead_id)

    await _atomic_update_with_status_guard(
        db,
        lead_id=lead_id,
        allowed_from=allowed_from,
        values=values,
        action=action,
    )

    await log_activity(
        db,
        lead_id=lead_id,
        activity_type=action.activity_type,
        performed_by=current_user_id,
        content=content,
        metadata=metadata,
    )

    await _close_addressed_tasks(db, lead_id=lead_id, action=action, now=now)
    await _create_followup_task_if_needed(
        db, lead_id=lead_id, action=action, now=now
    )

    await db.commit()
    return await _get_lead(db, lead_id)


# ===================== עזרה פנימית =====================

async def _perform_with_optional_progress(
    db: AsyncSession,
    *,
    lead_id: UUID,
    action: ActionDefinition,
    values: dict[str, Any],
    now: datetime,
    current_user_id: UUID | None,
    content: str | None,
    metadata: dict[str, Any] | None,
) -> Lead:
    """
    Outbound action על ליד שאולי עדיין NEW.
    אטומי: ניסיון יחיד עם UPDATE שמשנה NEW → IN_PROGRESS אם רלוונטי.

    מימוש: שתי שאילתות נפרדות, אבל בסדר נכון:
    1. ניסיון UPDATE WHERE status='NEW' → IN_PROGRESS + שאר השדות.
    2. אם rowcount=0 — UPDATE רגיל בלי שינוי סטטוס, מוגבל לסטטוסים פתוחים.
    """
    # ניסיון 1 — אם הליד עוד ב-NEW, מעבירים ל-IN_PROGRESS אטומית.
    # updated_at חובה (Core update לא מפעיל onupdate).
    values_with_progress = {
        **values,
        "status": LeadStatus.IN_PROGRESS.value,
        "updated_at": func.now(),
    }
    stmt = (
        update(Lead)
        .where(Lead.id == lead_id, Lead.status == LeadStatus.NEW.value)
        .values(**values_with_progress)
        .returning(Lead.id)
    )
    result = await db.execute(stmt)
    if result.scalar_one_or_none() is not None:
        # ההתקדמות הצליחה
        await log_activity(
            db,
            lead_id=lead_id,
            activity_type=action.activity_type,
            performed_by=current_user_id,
            content=content,
            metadata=metadata,
        )
        # מתעדים גם status_changed כדי שזה יופיע ב-timeline
        await log_activity(
            db,
            lead_id=lead_id,
            activity_type="status_changed",
            performed_by=current_user_id,
            metadata={"from": "NEW", "to": "IN_PROGRESS", "trigger": "auto_progress"},
        )
        await _close_addressed_tasks(db, lead_id=lead_id, action=action, now=now)
        await _create_followup_task_if_needed(
            db, lead_id=lead_id, action=action, now=now
        )
        await db.commit()
        return await _get_lead(db, lead_id)

    # ניסיון 2 — הליד כבר לא NEW. UPDATE רגיל, אבל רק אם הסטטוס מורשה.
    allowed_from = [s.value for s in (action.allowed_from or set())]
    if not allowed_from:
        # ב-action שדורש auto_progress, allowed_from תמיד מוגדר.
        # אם לא — שגיאה בקונפיגורציה, לא בקלט.
        await _ensure_lead_exists(db, lead_id)
        raise InvalidStateTransitionError()

    if not values:
        # אין מה לעדכן (לא צפוי לקרות עם auto_progress, אבל ליתר ביטחון)
        await _ensure_lead_exists(db, lead_id)
        await log_activity(
            db,
            lead_id=lead_id,
            activity_type=action.activity_type,
            performed_by=current_user_id,
            content=content,
            metadata=metadata,
        )
        await db.commit()
        return await _get_lead(db, lead_id)

    stmt2 = (
        update(Lead)
        .where(Lead.id == lead_id, Lead.status.in_(allowed_from))
        .values(**values, updated_at=func.now())
        .returning(Lead.id)
    )
    result2 = await db.execute(stmt2)
    if result2.scalar_one_or_none() is None:
        await _ensure_lead_exists(db, lead_id)
        raise InvalidStateTransitionError(
            f"לא ניתן לבצע '{action.description}' במצב הנוכחי של הליד."
        )

    await log_activity(
        db,
        lead_id=lead_id,
        activity_type=action.activity_type,
        performed_by=current_user_id,
        content=content,
        metadata=metadata,
    )
    await _close_addressed_tasks(db, lead_id=lead_id, action=action, now=now)
    await _create_followup_task_if_needed(
        db, lead_id=lead_id, action=action, now=now
    )
    await db.commit()
    return await _get_lead(db, lead_id)


# סוגי tasks שפעולת outbound/inbound מטפלת בהם — לסגירה אוטומטית.
# הרציונל: ברגע שנועה ביצעה touchpoint (שליחת תבנית/שיחה/הודעה נכנסת/
# שליחת הצעה), היא כבר התייחסה לליד — לא רוצים תזכורת תקועה ב-/today.
#
# *לא* כולל:
# - PROPOSAL_FOLLOWUP — תזכורת *אחרי* שההצעה נשלחה. mark_proposal_sent
#   יוצרת את הצורך, לא סוגרת תזכורת כזו.
# - POST_MEETING_UPDATE — קשור לפגישה ספציפית, מסולק רק ע"י close_lead
#   או ידנית.
# - PROGRAM_END — תזכורת לסיום תוכנית מתמשכת, ענין נפרד.
_AUTO_CLOSE_TASK_TYPES = (
    TaskType.FIRST_RESPONSE.value,
    TaskType.FOLLOWUP.value,
    TaskType.AFTER_HOURS_REPLY.value,
    TaskType.DORMANT_CHECK.value,    # היה DORMANT_REACHOUT — שונה לפי Spec §17.1
    TaskType.WARM_FOLLOWUP.value,    # touchpoint סוגר גם פולואפ חם (§17.1)
    TaskType.RETRY_CALL.value,       # אחרי שיחה מוצלחת — אין יותר צורך לנסות שוב
    # SEND_PROPOSAL לא בכאן: הוא נסגר רק על mark_proposal_sent הספציפי
    # (touchpoint כללי לא מבטל את הצורך לשלוח הצעה).
    # LECTURE_INQUIRY לא בכאן: תזכורת ספציפית לארגון, ידנית.
)


async def _close_addressed_tasks(
    db: AsyncSession,
    *,
    lead_id: UUID,
    action: ActionDefinition,
    now: datetime,
) -> None:
    """
    סוגר אוטומטית פעולות פתוחות כשנועה ביצעה touchpoint על ליד.

    Trigger: action שמסומן set_last_outbound (נועה שלחה משהו) או
    set_last_inbound (תיעוד תגובה מהלקוח). שני המקרים מסיימים את
    הצורך ב-FIRST_RESPONSE / FOLLOWUP — הליד לא "תקוע".

    לפני התיקון: סימון "שלחתי הצעה" עדכן status ל-PROPOSAL_SENT אבל
    השאיר את FIRST_RESPONSE פתוח, ונועה ראתה תזכורת תקועה לטיפול
    בליד שכבר טיפלה בו.
    """
    if not (action.set_last_outbound or action.set_last_inbound):
        return

    from app.models.task import Task  # local import — מונע circular
    from app.services.tasks import sync_lead_next_action_cache

    await db.execute(
        update(Task)
        .where(
            Task.lead_id == lead_id,
            Task.type.in_(_AUTO_CLOSE_TASK_TYPES),
            Task.status.in_(
                [TaskStatus.OPEN.value, TaskStatus.SNOOZED.value]
            ),
        )
        .values(
            status=TaskStatus.DONE.value,
            completed_at=now,
        )
    )
    # סנכרון cache: כעת הליד עשוי להיות בלי tasks פתוחים, או עם task
    # אחר (PROPOSAL_FOLLOWUP / POST_MEETING_UPDATE שלא נסגרו אוטומטית).
    await sync_lead_next_action_cache(db, lead_id)


async def _create_followup_task_if_needed(
    db: AsyncSession,
    *,
    lead_id: UUID,
    action: ActionDefinition,
    now: datetime,
) -> None:
    """
    יוצר task פולואפ אוטומטי אחרי פעולות מסוימות:
    - mark_proposal_sent (set_proposal_sent_at=True) → PROPOSAL_FOLLOWUP
      עם grace של FOLLOWUP_GRACE_PROPOSAL_ORG (4 ימים, האפיון יב §484).

    אינדמפוטנטי: אם כבר קיים PROPOSAL_FOLLOWUP פתוח לליד, מדלגים.
    """
    if not action.set_proposal_sent_at:
        return

    from app.constants import FOLLOWUP_GRACE_PROPOSAL_ORG
    from app.models.task import Task
    from app.services.tasks import sync_lead_next_action_cache

    existing = await db.execute(
        select(Task.id).where(
            Task.lead_id == lead_id,
            Task.type == TaskType.PROPOSAL_FOLLOWUP.value,
            Task.status.in_(
                [TaskStatus.OPEN.value, TaskStatus.SNOOZED.value]
            ),
        )
    )
    if existing.scalar_one_or_none() is not None:
        return

    db.add(
        Task(
            lead_id=lead_id,
            type=TaskType.PROPOSAL_FOLLOWUP.value,
            due_at=now + FOLLOWUP_GRACE_PROPOSAL_ORG,
            status=TaskStatus.OPEN.value,
            origin_rule="auto_proposal_followup",
        )
    )
    await db.flush()
    await sync_lead_next_action_cache(db, lead_id)


async def _atomic_update_with_status_guard(
    db: AsyncSession,
    *,
    lead_id: UUID,
    allowed_from: list[str] | None,
    values: dict[str, Any],
    action: ActionDefinition,
) -> None:
    """UPDATE אטומי עם בדיקת rowcount. זורק InvalidStateTransitionError אם נכשל."""
    # updated_at חייב להיכתב במפורש — onupdate ב-ORM לא מופעל ב-Core update().
    # מוסיפים פה בנקודה היחידה שבאמת מבצעת UPDATE, אחרי שווידאנו ש-values אינו ריק.
    final_values = {**values, "updated_at": func.now()}
    stmt = update(Lead).where(Lead.id == lead_id)
    if allowed_from is not None:
        stmt = stmt.where(Lead.status.in_(allowed_from))
    stmt = stmt.values(**final_values).returning(Lead.id)

    result = await db.execute(stmt)
    if result.scalar_one_or_none() is None:
        # ייתכן: ליד לא קיים, או הסטטוס לא מורשה
        await _ensure_lead_exists(db, lead_id)
        raise InvalidStateTransitionError(
            f"לא ניתן לבצע '{action.description}' במצב הנוכחי של הליד."
        )


async def _ensure_lead_exists(db: AsyncSession, lead_id: UUID) -> None:
    res = await db.execute(select(Lead.id).where(Lead.id == lead_id))
    if res.scalar_one_or_none() is None:
        raise NotFoundError("ליד לא נמצא.")


async def _get_lead(db: AsyncSession, lead_id: UUID) -> Lead:
    # populate_existing — חובה אחרי Core update(). ראה הסבר ב-leads.get_lead_or_404.
    res = await db.execute(
        select(Lead)
        .where(Lead.id == lead_id)
        .execution_options(populate_existing=True)
    )
    lead = res.scalar_one_or_none()
    if lead is None:
        raise NotFoundError("ליד לא נמצא.")
    return lead
