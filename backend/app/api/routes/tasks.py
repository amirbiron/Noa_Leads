"""
Tasks routes — רשימה, snooze, complete.
"""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession
from app.schemas.task import SnoozeRequest, TaskRead
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
