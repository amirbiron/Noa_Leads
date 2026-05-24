"""
Tasks routes — רשימה, snooze, complete, stuck.
"""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession
from app.schemas.task import SnoozeRequest, StuckTaskItem, TaskRead
from app.services import tasks as tasks_service

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("/open", response_model=list[TaskRead])
async def list_open_tasks(
    db: DbSession,
    user: CurrentUser,
    assigned_to: UUID | None = Query(default=None),
    due_before: datetime | None = Query(default=None),
) -> list[TaskRead]:
    items = await tasks_service.list_open_tasks(
        db, assigned_to=assigned_to, due_before=due_before
    )
    return [TaskRead.model_validate(t) for t in items]


@router.get("/stuck", response_model=list[StuckTaskItem])
async def list_stuck_tasks(
    db: DbSession, _user: CurrentUser
) -> list[StuckTaskItem]:
    """
    משימות תקועות — קריטריון זהה ל-stuck_count ב-dashboard
    (overdue per-type grace, snooze respected). כך שהקליק על
    "לא טופלו בזמן" מוביל לרשימה התואמת.
    """
    from app.constants import TaskStatus
    from app.services.dashboard import _OVERDUE_GRACE

    rows = await tasks_service.list_stuck_tasks(db)
    now = datetime.now(timezone.utc)

    def _alert_threshold(task) -> datetime:
        # נקודת הזמן שבה המשימה נחשבת overdue. עבור snooze - due_at,
        # עבור OPEN עם grace - created_at + grace, אחרת - due_at.
        if task.status == TaskStatus.SNOOZED.value:
            return task.due_at
        grace = _OVERDUE_GRACE.get(task.type)
        if grace is not None:
            return task.created_at + grace
        return task.due_at

    return [
        StuckTaskItem(
            task_id=task.id,
            task_type=task.type,
            due_at=task.due_at,
            days_stuck=max(0, (now - _alert_threshold(task)).days),
            lead_id=lead.id,
            lead_name=lead.full_name,
            lead_status=lead.status,
            service_category=lead.service_category,
            waiting_on=lead.waiting_on,
        )
        for task, lead in rows
    ]


@router.post("/{task_id}/snooze", response_model=TaskRead)
async def snooze_task(
    task_id: UUID, payload: SnoozeRequest, db: DbSession, user: CurrentUser
) -> TaskRead:
    task = await tasks_service.snooze_task(db, task_id, payload)
    return TaskRead.model_validate(task)


@router.post("/{task_id}/complete", response_model=TaskRead)
async def complete_task(
    task_id: UUID, db: DbSession, user: CurrentUser
) -> TaskRead:
    task = await tasks_service.complete_task(db, task_id)
    return TaskRead.model_validate(task)
