"""
שירות leads — CRUD בסיסי + רשימות עם פילטרים + סגירה/פתיחה מחדש.

מעברי סטטוס תמיד אטומיים: UPDATE ... WHERE status IN (...) + rowcount check.
זה מבטל race conditions בין שני משתמשים שמנסים לעדכן אותו ליד בו-זמנית.
"""

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import (
    CLOSED_LEAD_STATUSES,
    OPEN_LEAD_STATUSES,
    ActivityType,
    ClosureReason,
    LeadStatus,
)
from app.core.exceptions import (
    InvalidStateTransitionError,
    NotFoundError,
    ValidationError,
)
from app.core.state_machine import (
    CLOSE_ALLOWED_FROM,
    REOPEN_ALLOWED_FROM,
)
from app.models.lead import Lead
from app.schemas.lead import (
    LeadCloseRequest,
    LeadCreate,
    LeadTransferRequest,
    LeadUpdate,
)
from app.services.activities import log_activity


# ===================== יצירה =====================

async def create_lead(
    db: AsyncSession,
    payload: LeadCreate,
    current_user_id: UUID | None,
    *,
    create_first_response_task: bool = True,
    commit: bool = True,
) -> Lead:
    """
    יוצרת ליד חדש + רישום ב-audit log + (כברירת מחדל) משימת first_response.
    הכל בטרנזקציה אחת — אם משהו נכשל, שום דבר לא נשמר.

    commit=False — מאפשר לקוראים להוסיף activities נוספים לפני commit,
    כדי לשמור על אטומיות (ראה intake_after_hours_whatsapp).
    """
    # אם לא צוין owner מפורש, מקצים לפי המשתמש שיצר
    owner_id = payload.owner_id or current_user_id

    lead = Lead(
        full_name=payload.full_name,
        phone=payload.phone,
        email=payload.email,
        organization_name=payload.organization_name,
        service_category=str(payload.service_category),
        service_subtype=payload.service_subtype,
        source_channel=str(payload.source_channel),
        source_detail=payload.source_detail,
        utm_source=payload.utm_source,
        utm_campaign=payload.utm_campaign,
        utm_content=payload.utm_content,
        preferred_contact=str(payload.preferred_contact),
        priority_level=str(payload.priority_level),
        owner_id=owner_id,
        personal_note=payload.personal_note,
        status=LeadStatus.NEW.value,
        waiting_on="NOAH",
    )
    db.add(lead)
    await db.flush()  # כדי לקבל id

    await log_activity(
        db,
        lead_id=lead.id,
        activity_type=ActivityType.LEAD_CREATED,
        performed_by=current_user_id,
        metadata={"source_channel": lead.source_channel},
    )

    if create_first_response_task:
        # local import — מונע circular import בין leads ↔ tasks
        from app.services import tasks as tasks_service
        await tasks_service.create_first_response_task(db, lead)

    if commit:
        await db.commit()
        await db.refresh(lead)
        # פוש לטלגרם — לכל מקור חוץ מהזנה ידנית (נועה עצמה הזינה,
        # אין צורך להתריע לעצמה). שגיאות telegram נבלעות בתוך השירות.
        if lead.source_channel != "manual":
            from app.services import telegram as telegram_service
            await telegram_service.notify_new_lead(lead)
    return lead


# ===================== קריאה =====================

async def get_lead_or_404(db: AsyncSession, lead_id: UUID) -> Lead:
    result = await db.execute(select(Lead).where(Lead.id == lead_id))
    lead = result.scalar_one_or_none()
    if lead is None:
        raise NotFoundError("ליד לא נמצא.")
    return lead


async def list_leads(
    db: AsyncSession,
    *,
    page: int,
    page_size: int,
    status: str | None = None,
    waiting_on: str | None = None,
    owner_id: UUID | None = None,
    source_channel: str | None = None,
    needs_attention: bool | None = None,
    search: str | None = None,
) -> tuple[list[Lead], int]:
    """מחזיר (items, total)."""
    from sqlalchemy import or_

    base = select(Lead)
    if status:
        base = base.where(Lead.status == status)
    if waiting_on:
        base = base.where(Lead.waiting_on == waiting_on)
    if owner_id:
        base = base.where(Lead.owner_id == owner_id)
    if source_channel:
        base = base.where(Lead.source_channel == source_channel)
    if needs_attention is not None:
        base = base.where(Lead.needs_attention == needs_attention)

    if search and search.strip():
        # חיפוש מקיף לפי האפיון: שם, ארגון, טלפון מלא, ו-4 ספרות אחרונות.
        # "נועה תזכור לפעמים רק 'הבחור מאינטל' או 'הטלפון שמסתיים ב-4821'".
        term = search.strip()
        digits = "".join(c for c in term if c.isdigit())
        pattern = f"%{term}%"
        filters = [
            Lead.full_name.ilike(pattern),
            Lead.organization_name.ilike(pattern),
        ]
        if digits:
            digit_pattern = f"%{digits}%"
            # התאמה ישירה (אם הטלפון לא מנורמל) — לדוגמה "050-1234567" יכיל "1234"
            filters.append(Lead.phone.ilike(digit_pattern))
            # התאמה אחרי הסרת תווים שאינם ספרות — תופס "+972 50-1234567" → "972501234567"
            normalized_phone = func.regexp_replace(Lead.phone, r"\D", "", "g")
            filters.append(normalized_phone.ilike(digit_pattern))
        base = base.where(or_(*filters))

    # ספירה
    count_stmt = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    # מיון: ליד חדש קודם, אחר כך לפי updated_at יורד
    items_stmt = (
        base.order_by(Lead.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(items_stmt)
    items = list(result.scalars().all())
    return items, total


# ===================== עדכון =====================

async def update_lead(
    db: AsyncSession, lead_id: UUID, payload: LeadUpdate, current_user_id: UUID | None
) -> Lead:
    lead = await get_lead_or_404(db, lead_id)

    # רק שדות שנשלחו במפורש
    updates = payload.model_dump(exclude_unset=True)

    # אם נשלח owner_id = None — מותר רק אם הסטטוס לא פתוח (ולידציה לפי spec)
    if "owner_id" in updates and updates["owner_id"] is None:
        if lead.status in OPEN_LEAD_STATUSES:
            raise ValidationError("ליד פתוח חייב בעל אחריות.")

    # המרת enums למחרוזות לפני שמירה
    for key, value in list(updates.items()):
        if hasattr(value, "value"):
            updates[key] = value.value

    for key, value in updates.items():
        setattr(lead, key, value)

    await log_activity(
        db,
        lead_id=lead.id,
        activity_type=ActivityType.LEAD_UPDATED,
        performed_by=current_user_id,
        metadata={"fields": list(updates.keys())},
    )

    await db.commit()
    await db.refresh(lead)
    return lead


# ===================== סגירה =====================

async def close_lead(
    db: AsyncSession,
    lead_id: UUID,
    payload: LeadCloseRequest,
    current_user_id: UUID | None,
) -> Lead:
    target = payload.target_status
    if target not in CLOSED_LEAD_STATUSES:
        raise ValidationError("ניתן לסגור ליד רק ל-WON, LOST או ARCHIVED.")

    if target == LeadStatus.LOST and payload.closure_reason is None:
        raise ValidationError("חובה לציין סיבת סגירה כשסוגרים כ-LOST.")

    # closure_reason חוקי רק אם target = LOST
    if target != LeadStatus.LOST and payload.closure_reason is not None:
        raise ValidationError("ניתן לציין סיבת סגירה רק כשסוגרים כ-LOST.")

    # מעבר אטומי: רק אם הסטטוס הנוכחי מורשה.
    # closure_reason תמיד נכתב — אם target=WON/ARCHIVED הערך הוא None,
    # אחרת ייתכן שערך LOST ישן יישאר על ליד שכעת WON (באג integrity).
    # updated_at חייב להיכתב במפורש — onupdate של ORM לא מופעל ב-Core update().
    allowed_from = [s.value for s in CLOSE_ALLOWED_FROM]
    values: dict[str, Any] = {
        "status": target.value,
        "next_action_type": None,
        "next_action_due_at": None,
        "needs_attention": False,
        "waiting_on": "NONE",
        "closure_reason": (
            str(payload.closure_reason) if payload.closure_reason else None
        ),
        "updated_at": func.now(),
    }

    stmt = (
        update(Lead)
        .where(Lead.id == lead_id, Lead.status.in_(allowed_from))
        .values(**values)
        .returning(Lead.id)
    )
    result = await db.execute(stmt)
    if result.scalar_one_or_none() is None:
        # ייתכן שהליד לא קיים, או שהסטטוס שלו כבר ARCHIVED
        existing = await db.execute(
            select(Lead.status).where(Lead.id == lead_id)
        )
        if existing.scalar_one_or_none() is None:
            raise NotFoundError("ליד לא נמצא.")
        raise InvalidStateTransitionError(
            "לא ניתן לסגור ליד שכבר נמצא בארכיון."
        )

    # תיוג סמנטי מדויק לכל סוג סגירה — חשוב ל-audit timeline
    activity_type = {
        LeadStatus.WON: ActivityType.LEAD_WON,
        LeadStatus.LOST: ActivityType.LEAD_LOST,
        LeadStatus.ARCHIVED: ActivityType.LEAD_ARCHIVED,
    }[target]
    await log_activity(
        db,
        lead_id=lead_id,
        activity_type=activity_type,
        performed_by=current_user_id,
        content=payload.note,
        metadata={
            "new_status": target.value,
            "closure_reason": (
                str(payload.closure_reason) if payload.closure_reason else None
            ),
        },
    )

    await db.commit()
    return await get_lead_or_404(db, lead_id)


# ===================== העברה לעוזרת / בחזרה =====================

async def transfer_lead(
    db: AsyncSession,
    lead_id: UUID,
    payload: LeadTransferRequest,
    current_user_id: UUID | None,
) -> Lead:
    """
    מעבירה ליד למשתמש אחר (בעיקר נועה → עוזרת).
    מעדכנת owner_id, waiting_on לפי תפקיד היעד, ומתעדת ב-activity.
    """
    from app.models.user import User  # local import למניעת circular

    # ולידציה: היעד קיים
    target_user = await db.execute(
        select(User).where(User.id == payload.target_user_id)
    )
    target = target_user.scalar_one_or_none()
    if target is None:
        raise ValidationError("משתמש יעד לא נמצא.")

    # waiting_on לפי תפקיד היעד: אם מעבירים לעוזרת — הכדור אצלה
    new_waiting_on = "ASSISTANT" if target.role == "assistant" else "NOAH"

    # מעבר אטומי — אסור להעביר ליד סגור
    open_statuses = [s.value for s in OPEN_LEAD_STATUSES]
    stmt = (
        update(Lead)
        .where(Lead.id == lead_id, Lead.status.in_(open_statuses))
        .values(
            owner_id=payload.target_user_id,
            waiting_on=new_waiting_on,
            updated_at=func.now(),
        )
        .returning(Lead.id)
    )
    result = await db.execute(stmt)
    if result.scalar_one_or_none() is None:
        existing = await db.execute(select(Lead.id).where(Lead.id == lead_id))
        if existing.scalar_one_or_none() is None:
            raise NotFoundError("ליד לא נמצא.")
        raise InvalidStateTransitionError(
            "לא ניתן להעביר ליד סגור. יש לפתוח אותו מחדש קודם."
        )

    await log_activity(
        db,
        lead_id=lead_id,
        activity_type=ActivityType.OWNER_CHANGED,
        performed_by=current_user_id,
        content=payload.handoff_note,
        metadata={
            "target_user_id": str(payload.target_user_id),
            "target_role": target.role,
        },
    )
    await db.commit()
    return await get_lead_or_404(db, lead_id)


# ===================== פתיחה מחדש =====================

async def reopen_lead(
    db: AsyncSession, lead_id: UUID, current_user_id: UUID | None
) -> Lead:
    allowed_from = [s.value for s in REOPEN_ALLOWED_FROM]
    stmt = (
        update(Lead)
        .where(Lead.id == lead_id, Lead.status.in_(allowed_from))
        .values(
            status=LeadStatus.IN_PROGRESS.value,
            closure_reason=None,
            waiting_on="NOAH",
            updated_at=func.now(),
        )
        .returning(Lead.id)
    )
    result = await db.execute(stmt)
    if result.scalar_one_or_none() is None:
        existing = await db.execute(select(Lead.status).where(Lead.id == lead_id))
        current = existing.scalar_one_or_none()
        if current is None:
            raise NotFoundError("ליד לא נמצא.")
        raise InvalidStateTransitionError(
            "ניתן לפתוח מחדש רק לידים סגורים (WON / LOST / ARCHIVED)."
        )

    await log_activity(
        db,
        lead_id=lead_id,
        activity_type=ActivityType.LEAD_REOPENED,
        performed_by=current_user_id,
    )
    await db.commit()
    return await get_lead_or_404(db, lead_id)


# ===================== Timeline =====================

async def get_timeline(db: AsyncSession, lead_id: UUID):
    # מאמת קיום הליד תחילה — אחרת מחזירים 404 ולא רשימה ריקה
    await get_lead_or_404(db, lead_id)

    from app.models.activity import Activity  # local import למניעת circular
    stmt = (
        select(Activity)
        .where(Activity.lead_id == lead_id)
        .order_by(Activity.created_at.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())
