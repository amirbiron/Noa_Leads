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
    משימות תקועות — קריטריון זהה ל-stuck_count ב-dashboard: due_at <= now.
    הקליק על "לא טופלו בזמן" מוביל לרשימה התואמת ל-count.
    """
    rows = await tasks_service.list_stuck_tasks(db)
    now = datetime.now(timezone.utc)
    return [
        StuckTaskItem(
            task_id=task.id,
            task_type=task.type,
            due_at=task.due_at,
            # due_at = alert time בכל סוגי הtasks, אז ימי overdue = days
            # מאז due_at. clamp ל-0 לטיפול בrounding.
            days_stuck=max(0, (now - task.due_at).days),
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
