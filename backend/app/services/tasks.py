"""
שירות tasks — יצירה אוטומטית של משימות, snooze, complete, רשימת פתוחות.
"""

from datetime import datetime, time, timedelta, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import TaskStatus, TaskType
from app.core.exceptions import (
    InvalidStateTransitionError,
    NotFoundError,
    ValidationError,
)
from app.models.lead import Lead
from app.models.task import Task
from app.schemas.task import SnoozePreset, SnoozeRequest
from app.utils.work_hours import (
    ISRAEL_TZ,
    is_holiday,
    is_saturday,
    next_working_day_start,
    to_israel_tz,
)


# ===================== יצירה אוטומטית =====================

async def create_first_response_task(
    db: AsyncSession,
    lead: Lead,
    *,
    assigned_to: UUID | None = None,
) -> Task:
    """
    נוצרת אוטומטית עם פתיחת ליד חדש: משימת "החזרה ראשונה" לליד.
    אם הליד נכנס בשעות עבודה — due_at = עכשיו (יופיע מיד ב"פעולות היום").
    אם נכנס מחוץ לשעות — due_at = תחילת יום העבודה הבא, 09:00.
    """
    now = datetime.now(timezone.utc)
    due_at = _due_at_for_first_response(now)

    task = Task(
        lead_id=lead.id,
        type=TaskType.FIRST_RESPONSE.value,
        assigned_to=assigned_to or lead.owner_id,
        due_at=due_at,
        status=TaskStatus.OPEN.value,
        origin_rule="auto_first_response",
    )
    db.add(task)
    await db.flush()
    return task


def _due_at_for_first_response(now: datetime) -> datetime:
    """
    מחזיר datetime ב-UTC עבור due_at:
    - בתוך שעות עבודה: now (מיידי)
    - מחוץ: תחילת יום העבודה הבא ב-Asia/Jerusalem
    """
    from app.utils.work_hours import is_working_time  # avoid circular at import

    if is_working_time(now):
        return now
    return next_working_day_start(now).astimezone(timezone.utc)


# ===================== Snooze =====================

async def snooze_task(
    db: AsyncSession, task_id: UUID, payload: SnoozeRequest
) -> Task:
    """דחיית משימה לפי קיצור דרך או תאריך מותאם."""
    new_due_at = _resolve_snooze_target(payload)

    # אטומי: רק משימות פתוחות ניתנות ל-snooze
    stmt = (
        update(Task)
        .where(Task.id == task_id, Task.status == TaskStatus.OPEN.value)
        .values(
            status=TaskStatus.SNOOZED.value,
            snoozed_until=new_due_at,
            due_at=new_due_at,
        )
        .returning(Task.id)
    )
    result = await db.execute(stmt)
    if result.scalar_one_or_none() is None:
        # ייתכן: המשימה לא קיימת או שכבר נסגרה
        existing = await db.execute(select(Task.status).where(Task.id == task_id))
        status = existing.scalar_one_or_none()
        if status is None:
            raise NotFoundError("משימה לא נמצאה.")
        raise InvalidStateTransitionError(
            "ניתן לדחות רק משימות פתוחות."
        )

    await db.commit()
    return await _get_task_or_404(db, task_id)


def _resolve_snooze_target(payload: SnoozeRequest) -> datetime:
    """ממיר preset/custom_until ל-datetime tz-aware ב-UTC."""
    if payload.preset == SnoozePreset.CUSTOM:
        # custom_until מסומן חובה ב-validator של ה-schema
        assert payload.custom_until is not None
        custom = payload.custom_until
        if custom.tzinfo is None:
            # מתייחסים לזמן ללא tz כ-Asia/Jerusalem (זה מה שנועה תכניס מהמובייל)
            custom = custom.replace(tzinfo=ISRAEL_TZ)
        return custom.astimezone(timezone.utc)

    now_local = to_israel_tz(datetime.now(timezone.utc))
    today = now_local.date()

    if payload.preset == SnoozePreset.TODAY_AFTERNOON:
        target_local = datetime.combine(today, time(15, 0, tzinfo=ISRAEL_TZ))
        if target_local <= now_local:
            # אם כבר אחרי 15:00, דוחים למחר בבוקר
            target_local = datetime.combine(
                today + timedelta(days=1), time(9, 0, tzinfo=ISRAEL_TZ)
            )
        return target_local.astimezone(timezone.utc)

    if payload.preset == SnoozePreset.TOMORROW_MORNING:
        target_local = datetime.combine(
            today + timedelta(days=1), time(9, 0, tzinfo=ISRAEL_TZ)
        )
        return target_local.astimezone(timezone.utc)

    if payload.preset == SnoozePreset.SUNDAY_MORNING:
        # weekday: שני=0 ... שישי=4, שבת=5, ראשון=6
        days_until_sunday = (6 - today.weekday()) % 7
        if days_until_sunday == 0:
            days_until_sunday = 7  # אם היום ראשון, מתכוונים לראשון הבא
        target_local = datetime.combine(
            today + timedelta(days=days_until_sunday),
            time(9, 0, tzinfo=ISRAEL_TZ),
        )
        return target_local.astimezone(timezone.utc)

    if payload.preset == SnoozePreset.AFTER_HOLIDAY:
        # מחפש את היום הראשון אחרי החג הנוכחי/הקרוב
        candidate = today
        # מתחילים מהמחר (גם אם היום חג — מחפשים את היום שאחרי)
        for _ in range(30):  # safety bound
            candidate = candidate + timedelta(days=1)
            if not is_holiday(candidate) and not is_saturday(candidate):
                break
        target_local = datetime.combine(candidate, time(9, 0, tzinfo=ISRAEL_TZ))
        return target_local.astimezone(timezone.utc)

    raise ValidationError(f"קיצור snooze לא נתמך: {payload.preset}")


# ===================== Complete =====================

async def complete_task(db: AsyncSession, task_id: UUID) -> Task:
    """סגירת משימה. אטומי: רק משימות פתוחות/דחויות נסגרות."""
    now = datetime.now(timezone.utc)
    stmt = (
        update(Task)
        .where(
            Task.id == task_id,
            Task.status.in_([TaskStatus.OPEN.value, TaskStatus.SNOOZED.value]),
        )
        .values(status=TaskStatus.DONE.value, completed_at=now)
        .returning(Task.id)
    )
    result = await db.execute(stmt)
    if result.scalar_one_or_none() is None:
        existing = await db.execute(select(Task.status).where(Task.id == task_id))
        status = existing.scalar_one_or_none()
        if status is None:
            raise NotFoundError("משימה לא נמצאה.")
        raise InvalidStateTransitionError(
            "ניתן לסיים רק משימות פתוחות או דחויות."
        )

    await db.commit()
    return await _get_task_or_404(db, task_id)


# ===================== רשימה =====================

async def list_open_tasks(
    db: AsyncSession,
    *,
    assigned_to: UUID | None = None,
    due_before: datetime | None = None,
) -> list[Task]:
    """משימות פתוחות (כולל snoozed שהגיע מועדן)."""
    stmt = select(Task).where(
        Task.status.in_([TaskStatus.OPEN.value, TaskStatus.SNOOZED.value])
    )
    if assigned_to is not None:
        stmt = stmt.where(Task.assigned_to == assigned_to)
    if due_before is not None:
        stmt = stmt.where(Task.due_at <= due_before)
    stmt = stmt.order_by(Task.due_at.asc())

    result = await db.execute(stmt)
    return list(result.scalars().all())


# ===================== עזרה =====================

async def _get_task_or_404(db: AsyncSession, task_id: UUID) -> Task:
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if task is None:
        raise NotFoundError("משימה לא נמצאה.")
    return task
