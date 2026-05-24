"""
שירות tasks — יצירה אוטומטית של משימות, snooze, complete, רשימת פתוחות.
"""

from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.constants import CLOSED_LEAD_STATUSES, TaskStatus, TaskType
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


def _next_working_morning_from(d: date) -> datetime:
    """
    מחפש את יום העבודה הקרוב מ-d והלאה — מחזיר את שעת תחילת היום של נועה
    (WORK_DAY_START_HOUR מההגדרות) ב-TZ ישראל. מדלג על שבת ועל חגים.
    משתמש באותה הגדרה כמו next_working_day_start כדי להישאר עקבי.
    """
    start_hour = get_settings().work_day_start_hour
    candidate = d
    for _ in range(14):  # safety bound
        if not is_saturday(candidate) and not is_holiday(candidate):
            return datetime.combine(
                candidate, time(start_hour, 0, tzinfo=ISRAEL_TZ)
            )
        candidate += timedelta(days=1)
    return datetime.combine(candidate, time(start_hour, 0, tzinfo=ISRAEL_TZ))


def _after_next_holiday(from_date: date) -> datetime:
    """
    משמש ל-AFTER_HOLIDAY snooze: מאתר את החג הקרוב מ-from_date והלאה,
    ומחזיר את היום הראשון אחרי שהחג הסתיים (מדלג גם על חוה"מ פסח/סוכות
    ועל שבת אם נופלת באותו טווח).

    מבדיל מ-TOMORROW_MORNING בכך שהוא קופץ מעבר לבלוק שלם של חגים.
    אם אין חג בטווח 30 ימים — fallback ל-_next_working_morning_from.
    """
    start_hour = get_settings().work_day_start_hour

    # שלב א': איתור היום הראשון של בלוק החג הקרוב
    candidate = from_date
    holiday_start: date | None = None
    for _ in range(60):
        if is_holiday(candidate):
            holiday_start = candidate
            break
        candidate += timedelta(days=1)

    if holiday_start is None:
        # אין חג קרוב — מתנהג כמו TOMORROW_MORNING
        return _next_working_morning_from(from_date + timedelta(days=1))

    # שלב ב': דילוג על כל הבלוק הרצוף של חגים + שבתות שבדרך
    candidate = holiday_start
    for _ in range(30):
        if not is_holiday(candidate) and not is_saturday(candidate):
            return datetime.combine(
                candidate, time(start_hour, 0, tzinfo=ISRAEL_TZ)
            )
        candidate += timedelta(days=1)

    return datetime.combine(candidate, time(start_hour, 0, tzinfo=ISRAEL_TZ))


# ===================== יצירה אוטומטית =====================

async def create_first_response_task(
    db: AsyncSession,
    lead: Lead,
    *,
    assigned_to: UUID | None = None,
) -> Task:
    """
    נוצרת אוטומטית עם פתיחת ליד חדש: משימת תזכורת לטיפול ראשון.
    אותו SLA של 24h (Spec §17.1), אבל סוג ה-task משתנה לפי subtype:
    - lecture_organization / lecture_academic → LECTURE_INQUIRY (F-08).
    - אחרת → FIRST_RESPONSE (ברירת מחדל).

    ההבחנה נותנת סמנטיקה ברורה בדשבורד ("פניות מארגונים") ובסיס
    לשימוש בתבנית "פתיחה לארגון" (§18) בעתיד.

    אם הליד נכנס בשעות עבודה — due_at = עכשיו+24h. אם נופל מחוץ לשעות
    עבודה — נדחה לתחילת יום העבודה הבא, 09:00.
    """
    from app.constants import LECTURE_SUBTYPES

    now = datetime.now(timezone.utc)
    due_at = _due_at_for_first_response(now)

    if lead.service_subtype in LECTURE_SUBTYPES:
        task_type = TaskType.LECTURE_INQUIRY.value
        origin = "auto_lecture_inquiry"
    else:
        task_type = TaskType.FIRST_RESPONSE.value
        origin = "auto_first_response"

    task = Task(
        lead_id=lead.id,
        type=task_type,
        assigned_to=assigned_to or lead.owner_id,
        due_at=due_at,
        status=TaskStatus.OPEN.value,
        origin_rule=origin,
    )
    db.add(task)
    await db.flush()
    await sync_lead_next_action_cache(db, lead.id)
    return task


async def sync_lead_next_action_cache(
    db: AsyncSession, lead_id: UUID
) -> None:
    """
    מעדכן את שדות next_action_* בליד לפי ה-task הפעיל הקרוב ביותר.

    הקונספט: tasks = source of truth, leads.next_action_* = cache.
    ראה docs/phase-2.5-plan.md §7.3.

    שמירה ישירה של task.due_at — אין יותר grace adjustment. ה-due_at
    של כל task מייצג את ה-alert time (כשהוא נוצר, חשבו את ה-grace
    לתוכו). שינוי מהמודל הקודם — ראה הערות ב-_due_at_for_first_response.

    F-23: WHERE כולל בדיקה ש-status פתוח. ליד סגור לעולם לא יקבל
    next_action_due_at חי (כלל §6.5 בSpec). אם sync נקרא על ליד סגור
    בעקבות race (task נוצר בו במקביל לסגירה) — ה-UPDATE לא תופס, ה-cache
    נשאר NULL כפי שclose_lead הגדיר. silent no-op מכוון.
    """
    earliest = (
        await db.execute(
            select(Task.type, Task.due_at)
            .where(
                Task.lead_id == lead_id,
                Task.status.in_(
                    [TaskStatus.OPEN.value, TaskStatus.SNOOZED.value]
                ),
            )
            .order_by(Task.due_at.asc())
            .limit(1)
        )
    ).first()

    next_type = earliest.type if earliest is not None else None
    next_due = earliest.due_at if earliest is not None else None

    closed = [s.value for s in CLOSED_LEAD_STATUSES]
    await db.execute(
        update(Lead)
        .where(
            Lead.id == lead_id,
            Lead.status.notin_(closed),
        )
        .values(
            next_action_type=next_type,
            next_action_due_at=next_due,
        )
    )


def _due_at_for_first_response(now: datetime) -> datetime:
    """
    due_at של FIRST_RESPONSE = now + FOLLOWUP_GRACE_FIRST_RESPONSE,
    מותאם לשעות עבודה.

    לפי האפיון יב סעיף 482: "ליד חדש שלא טופל: 24 שעות". ה-due_at
    מייצג את הזמן שבו ה-task נחשב overdue. לפני הזמן הזה הליד מוצג
    ב"פניות חדשות" של דף הבית, ומגיע push לטלגרם — לא נופל בין הכיסאות.

    אם הזמן נופל מחוץ לשעות עבודה (לילה/שבת/חג) — נדחה לתחילת יום
    העבודה הבא, כדי שה-alert יקרה בזמן שנועה עובדת.
    """
    from app.constants import FOLLOWUP_GRACE_FIRST_RESPONSE
    from app.utils.work_hours import is_working_time  # avoid circular at import

    alert_time = now + FOLLOWUP_GRACE_FIRST_RESPONSE
    if is_working_time(alert_time):
        return alert_time
    return next_working_day_start(alert_time).astimezone(timezone.utc)


# ===================== Snooze =====================

async def snooze_task(
    db: AsyncSession, task_id: UUID, payload: SnoozeRequest
) -> Task:
    """דחיית משימה לפי קיצור דרך או תאריך מותאם."""
    new_due_at = _resolve_snooze_target(payload)

    # אטומי: ניתן ל-snooze גם משימה שכבר ב-SNOOZED (re-snooze אחרי שהמועד עבר).
    # הדשבורד מציג snoozed-expired כפתוחות, אז משתמש מצפה לדחות אותן שוב.
    stmt = (
        update(Task)
        .where(
            Task.id == task_id,
            Task.status.in_([TaskStatus.OPEN.value, TaskStatus.SNOOZED.value]),
        )
        .values(
            status=TaskStatus.SNOOZED.value,
            snoozed_until=new_due_at,
            due_at=new_due_at,
        )
        .returning(Task.id, Task.lead_id)
    )
    result = await db.execute(stmt)
    row = result.first()
    if row is None:
        existing = await db.execute(select(Task.status).where(Task.id == task_id))
        status = existing.scalar_one_or_none()
        if status is None:
            raise NotFoundError("משימה לא נמצאה.")
        raise InvalidStateTransitionError(
            "ניתן לדחות רק משימות פתוחות או דחויות."
        )

    # סנכרון cache — due_at השתנה, ה-task הקרוב ביותר עלול להשתנות.
    await sync_lead_next_action_cache(db, row.lead_id)
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
            # כבר אחרי 15:00 — דוחים ליום העבודה הבא, מדלגים על שבת/חג
            target_local = _next_working_morning_from(today + timedelta(days=1))
        return target_local.astimezone(timezone.utc)

    if payload.preset == SnoozePreset.TOMORROW_MORNING:
        # אם "מחר" נופל על שבת/חג, מקפיצים ליום העבודה הבא
        target_local = _next_working_morning_from(today + timedelta(days=1))
        return target_local.astimezone(timezone.utc)

    if payload.preset == SnoozePreset.SUNDAY_MORNING:
        # weekday: שני=0 ... שישי=4, שבת=5, ראשון=6
        days_until_sunday = (6 - today.weekday()) % 7
        if days_until_sunday == 0:
            days_until_sunday = 7  # אם היום ראשון, מתכוונים לראשון הבא
        # אם ראשון נופל על חג (ר"ה / סיגד / וכו'), נדלג ליום העבודה הבא
        target_local = _next_working_morning_from(
            today + timedelta(days=days_until_sunday)
        )
        return target_local.astimezone(timezone.utc)

    if payload.preset == SnoozePreset.AFTER_HOLIDAY:
        # שונה מ-TOMORROW_MORNING: קופץ מעבר לבלוק החג הקרוב, לא רק
        # יום אחד קדימה. אם היום שלפני פסח — נחזור אחרי שמיני של פסח.
        target_local = _after_next_holiday(today)
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
        .returning(Task.id, Task.lead_id)
    )
    result = await db.execute(stmt)
    row = result.first()
    if row is None:
        existing = await db.execute(select(Task.status).where(Task.id == task_id))
        status = existing.scalar_one_or_none()
        if status is None:
            raise NotFoundError("משימה לא נמצאה.")
        raise InvalidStateTransitionError(
            "ניתן לסיים רק משימות פתוחות או דחויות."
        )

    # סנכרון cache בליד — אם זו הייתה המשימה הקרובה, מצא את הבאה.
    await sync_lead_next_action_cache(db, row.lead_id)
    await db.commit()
    return await _get_task_or_404(db, task_id)


# ===================== רשימה =====================

async def list_open_tasks(
    db: AsyncSession,
    *,
    assigned_to: UUID | None = None,
    due_before: datetime | None = None,
) -> list[Task]:
    """
    משימות פתוחות:
    - OPEN: תמיד מוצגות (גם אם due_at בעתיד — חשוב לראות מה מתקרב)
    - SNOOZED: רק אחרי שעבר ה-snooze (due_at <= now). מקודם
      הקוד החזיר *כל* ה-snoozed אם לא הועבר due_before, מה שעקף
      את כל המטרה של snooze.
    """
    now = datetime.now(timezone.utc)
    stmt = select(Task).where(
        or_(
            Task.status == TaskStatus.OPEN.value,
            and_(
                Task.status == TaskStatus.SNOOZED.value,
                Task.due_at <= now,
            ),
        )
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
    # populate_existing — חובה אחרי Core update(). ראה הסבר ב-leads.get_lead_or_404.
    result = await db.execute(
        select(Task)
        .where(Task.id == task_id)
        .execution_options(populate_existing=True)
    )
    task = result.scalar_one_or_none()
    if task is None:
        raise NotFoundError("משימה לא נמצאה.")
    return task


async def list_stuck_tasks(db: AsyncSession) -> list[tuple[Task, Lead]]:
    """
    "ממתין לטיפול" — Spec v2.1 §16.2 + §22.7: לידים שתקועים **7+ ימים**
    (due_at <= now - 7d), לא סתם overdue זמני.

    הבחנה ברורה לפי §16.2:
    - `weekly_insights.stuck_count` (תובנה שבועית, §13.9) — כל overdue,
      אפילו יום אחד. נשאר ב-due_at <= now.
    - `/tasks/stuck` (העמוד הנפרד) — רק 7+ ימים. כאן.

    הסף הוגדר באפיון כדי שהעמוד יציג רק מקרים שבאמת דורשים פעולה
    דחופה, ולא רעש של overdue זמני שבמילא יוצג ב"פעולות היום".

    מודל פשוט (אחרי הסרת grace per-type): due_at = alert time תמיד.
    snooze מעדכן due_at, FIRST_RESPONSE נוצר עם due_at=now+24h, וכו'.

    מסונן ללידים פתוחים (defense in depth — close_lead מבטל tasks).
    מיון לפי due_at עולה (ישנים קודם).
    """
    now_utc = datetime.now(timezone.utc)
    stuck_threshold = now_utc - timedelta(days=7)

    stmt = (
        select(Task, Lead)
        .join(Lead, Task.lead_id == Lead.id)
        .where(
            Task.status.in_(
                [TaskStatus.OPEN.value, TaskStatus.SNOOZED.value]
            ),
            Task.due_at <= stuck_threshold,
            Lead.status.notin_([s.value for s in CLOSED_LEAD_STATUSES]),
        )
        .order_by(Task.due_at.asc())
    )
    rows = (await db.execute(stmt)).all()

    # dedup לפי lead_id — שורה אחת לכל ליד, ה-task הישן ביותר שלו (כי
    # ה-order_by מציב ישנים קודם). מבטיח עמוד נקי גם אם לליד יש כמה
    # tasks תקועים.
    seen_leads: set = set()
    deduped: list[tuple[Task, Lead]] = []
    for task, lead in rows:
        if lead.id in seen_leads:
            continue
        seen_leads.add(lead.id)
        deduped.append((task, lead))
    return deduped
