"""
שירות programs — תוכניות מתמשכות (שיקום קול 8 מפגשים, ליווי הפקה 3-4 חודשים).

לפי האפיון: "כשנשאר מפגש אחד לסיום, המערכת מקפיצה הצעה אוטומטית:
'התוכנית מסתיימת — שווה להציע המשך'". מימוש: יצירת משימת program_end
ברגע שמגיעים ל-completed == total - 1.
"""

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import (
    ActivityType,
    ProgramStatus,
    TaskStatus,
    TaskType,
)
from app.core.exceptions import (
    InvalidStateTransitionError,
    NotFoundError,
    ValidationError,
)
from app.models.lead import Lead
from app.models.program import Program
from app.models.task import Task
from app.schemas.program import ProgramCreate, ProgramUpdate
from app.services.activities import log_activity
from app.utils.work_hours import next_working_day_start


# ===================== קריאה =====================

async def get_program_or_404(db: AsyncSession, program_id: UUID) -> Program:
    # populate_existing — חובה אחרי Core update() (למשל cancel_program).
    # ראה הסבר ב-leads.get_lead_or_404.
    result = await db.execute(
        select(Program)
        .where(Program.id == program_id)
        .execution_options(populate_existing=True)
    )
    program = result.scalar_one_or_none()
    if program is None:
        raise NotFoundError("תוכנית לא נמצאה.")
    return program


async def list_programs_for_lead(
    db: AsyncSession, lead_id: UUID
) -> list[Program]:
    stmt = (
        select(Program)
        .where(Program.lead_id == lead_id)
        .order_by(Program.started_at.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def list_active_programs(
    db: AsyncSession,
) -> list[tuple[Program, Lead]]:
    """תוכניות פעילות + פרטי הליד שלהן, ממוין לפי קרבת סיום."""
    stmt = (
        select(Program, Lead)
        .join(Lead, Program.lead_id == Lead.id)
        .where(Program.status == ProgramStatus.ACTIVE.value)
        .order_by(
            # קרוב יותר לסיום קודם — חישוב פשוט: שורי שנותר
            (Program.total_sessions - Program.completed_sessions).asc(),
            Program.started_at.asc(),
        )
    )
    result = await db.execute(stmt)
    return [(program, lead) for program, lead in result.all()]


# ===================== יצירה =====================

async def create_program(
    db: AsyncSession, payload: ProgramCreate, current_user_id: UUID | None
) -> Program:
    # מאמתים שהליד קיים
    lead_result = await db.execute(
        select(Lead.id).where(Lead.id == payload.lead_id)
    )
    if lead_result.scalar_one_or_none() is None:
        raise NotFoundError("ליד לא נמצא.")

    program = Program(
        lead_id=payload.lead_id,
        program_type=str(payload.program_type),
        total_sessions=payload.total_sessions,
        total_price=payload.total_price,
        estimated_end_at=payload.estimated_end_at,
        status=ProgramStatus.ACTIVE.value,
    )
    db.add(program)
    await db.flush()

    await log_activity(
        db,
        lead_id=payload.lead_id,
        activity_type=ActivityType.PROGRAM_CREATED,
        performed_by=current_user_id,
        content=f"תוכנית חדשה: {program.total_sessions} מפגשים",
        metadata={
            "program_id": str(program.id),
            "program_type": program.program_type,
            "total_sessions": program.total_sessions,
        },
    )
    await db.commit()
    await db.refresh(program)
    return program


# ===================== עדכון =====================

async def update_program(
    db: AsyncSession,
    program_id: UUID,
    payload: ProgramUpdate,
    current_user_id: UUID | None,
) -> Program:
    program = await get_program_or_404(db, program_id)
    if program.status != ProgramStatus.ACTIVE.value:
        raise InvalidStateTransitionError(
            "ניתן לעדכן רק תוכניות פעילות. לפתיחה מחדש — צור תוכנית חדשה."
        )

    previous_completed = program.completed_sessions
    updates = payload.model_dump(exclude_unset=True)

    if "completed_sessions" in updates:
        new_completed = updates["completed_sessions"]
        if new_completed > program.total_sessions:
            raise ValidationError(
                "מספר המפגשים שבוצעו לא יכול לעלות על סה\"כ המפגשים בתוכנית."
            )
        program.completed_sessions = new_completed

    if "actual_hours" in updates:
        program.actual_hours = updates["actual_hours"]

    if "total_price" in updates:
        program.total_price = updates["total_price"]

    if "estimated_end_at" in updates:
        program.estimated_end_at = updates["estimated_end_at"]

    # === auto: נשאר מפגש אחד → משימת program_end (פעם אחת בלבד) ===
    sessions_left = program.total_sessions - program.completed_sessions
    crossed_threshold = (
        previous_completed < program.total_sessions - 1
        and program.completed_sessions >= program.total_sessions - 1
        and program.completed_sessions < program.total_sessions
    )
    if crossed_threshold:
        await _create_program_end_task_if_missing(db, program)

    # === auto: הגענו לסיום → completed ===
    if program.completed_sessions >= program.total_sessions:
        program.status = ProgramStatus.COMPLETED.value
        await log_activity(
            db,
            lead_id=program.lead_id,
            activity_type=ActivityType.PROGRAM_COMPLETED,
            performed_by=current_user_id,
            content=f"תוכנית הסתיימה: {program.completed_sessions}/{program.total_sessions} מפגשים",
            metadata={"program_id": str(program.id)},
        )
    elif (
        "completed_sessions" in updates
        and program.completed_sessions > previous_completed
    ):
        # log רגיל על מפגש שבוצע
        await log_activity(
            db,
            lead_id=program.lead_id,
            activity_type=ActivityType.PROGRAM_SESSION_DONE,
            performed_by=current_user_id,
            content=(
                f"מפגש {program.completed_sessions}/{program.total_sessions} בוצע"
                + (f" (נשאר {sessions_left})" if sessions_left > 0 else "")
            ),
            metadata={"program_id": str(program.id)},
        )

    await db.commit()
    await db.refresh(program)
    return program


async def _create_program_end_task_if_missing(
    db: AsyncSession, program: Program
) -> None:
    """
    יוצר משימת program_end לליד — אלא אם כבר קיימת כזו פתוחה.
    מונע יצירה כפולה אם המעבר ל-N-1 קורה כמה פעמים (לא צפוי, אבל בטוח).
    """
    existing = await db.execute(
        select(Task.id).where(
            Task.lead_id == program.lead_id,
            Task.type == TaskType.PROGRAM_END.value,
            Task.status.in_([TaskStatus.OPEN.value, TaskStatus.SNOOZED.value]),
        )
    )
    if existing.scalar_one_or_none() is not None:
        return

    due_at = next_working_day_start(datetime.now(timezone.utc)).astimezone(
        timezone.utc
    )
    task = Task(
        lead_id=program.lead_id,
        type=TaskType.PROGRAM_END.value,
        due_at=due_at,
        status=TaskStatus.OPEN.value,
        origin_rule="program_near_end",
    )
    db.add(task)


# ===================== ביטול =====================

async def cancel_program(
    db: AsyncSession, program_id: UUID, current_user_id: UUID | None
) -> Program:
    """מסיים תוכנית אקטיבית כ-canceled. אטומי באמצעות WHERE status."""
    stmt = (
        update(Program)
        .where(
            Program.id == program_id,
            Program.status == ProgramStatus.ACTIVE.value,
        )
        .values(status=ProgramStatus.CANCELED.value)
        .returning(Program.lead_id)
    )
    result = await db.execute(stmt)
    lead_id = result.scalar_one_or_none()
    if lead_id is None:
        existing = await db.execute(
            select(Program.status).where(Program.id == program_id)
        )
        if existing.scalar_one_or_none() is None:
            raise NotFoundError("תוכנית לא נמצאה.")
        raise InvalidStateTransitionError(
            "ניתן לבטל רק תוכנית פעילה."
        )

    await log_activity(
        db,
        lead_id=lead_id,
        activity_type=ActivityType.PROGRAM_CANCELED,
        performed_by=current_user_id,
        metadata={"program_id": str(program_id)},
    )
    await db.commit()
    return await get_program_or_404(db, program_id)


# ===================== מחיקה =====================
# אין hard delete — רק cancel (לפי כלל "ארכיון שקט במקום מחיקה")
