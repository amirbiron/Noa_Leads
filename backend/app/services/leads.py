"""
שירות leads — CRUD בסיסי + רשימות עם פילטרים + סגירה/פתיחה מחדש.

מעברי סטטוס תמיד אטומיים: UPDATE ... WHERE status IN (...) + rowcount check.
זה מבטל race conditions בין שני משתמשים שמנסים לעדכן אותו ליד בו-זמנית.
"""

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import case, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import (
    CLOSED_LEAD_STATUSES,
    OPEN_LEAD_STATUSES,
    ActivityType,
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
    set_last_inbound: bool = False,
) -> Lead:
    """
    יוצרת ליד חדש + רישום ב-audit log + (כברירת מחדל) משימת first_response.
    הכל בטרנזקציה אחת — אם משהו נכשל, שום דבר לא נשמר.

    commit=False — מאפשר לקוראים להוסיף activities נוספים לפני commit,
    כדי לשמור על אטומיות (ראה intake_after_hours_whatsapp).

    set_last_inbound=True — לליד שנוצר *מ-inbound* של הלקוח (WhatsApp
    after-hours, Gmail intake): קובע last_inbound_at=now ביצירה. בלי זה
    silence-break detection ומיון הדשבורד מתבססים על NULL. *לא* סוגר
    FIRST_RESPONSE — נועה עדיין צריכה לענות (זה קטגוריה B במיפוי, לא
    register_inbound; ראה inbound chokepoint).
    """
    # אם לא צוין owner מפורש, מקצים לפי המשתמש שיצר
    owner_id = payload.owner_id or current_user_id

    now = datetime.now(timezone.utc)
    lead = Lead(
        full_name=payload.full_name,
        phone=payload.phone,
        email=payload.email,
        organization_name=payload.organization_name,
        # אופציונלי (F-04) — אם payload מכיל None, הליד נשמר ללא קטגוריה.
        # str(None) היה הופך ל-"None" string שמעקם את ה-enum.
        service_category=(
            str(payload.service_category)
            if payload.service_category is not None
            else None
        ),
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
        # §7.2 — נמסר מ-NewLeadModal (expand section). cursor bugbot
        # caught: בלי השורה הזו השדה אובד בשתיקה והליד נשמר תמיד עם
        # default False של המודל.
        is_returning_customer=payload.is_returning_customer,
        lead_message=payload.lead_message,
        status=LeadStatus.NEW.value,
        waiting_on="NOAH",
        # ליד שנוצר מ-inbound — last_inbound_at=now. ברירת מחדל None.
        last_inbound_at=now if set_last_inbound else None,
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
        # פוש לטלגרם — רק לליד שנקלט אוטומטית (נועה לא יודעת עליו). הקריטריון
        # הוא היעדר משתמש מחובר (current_user_id is None), *לא* source_channel:
        # כשנועה יוצרת ליד ידנית היא בוחרת מקור אמיתי (המלצה/וואטסאפ/מייל), אז
        # גידור לפי source_channel היה שולח push מיותר. ראה §16.3.
        # **חשוב לסדר:** notify_new_lead חייב להיקרא *אחרי* db.commit().
        # אם נעביר אותו לפני, race עם ה-/dashboard/poll: ה-client עוקב
        # אחרי התראת הטלגרם → polling → ה-row עדיין לא ב-DB → ה-lead לא יופיע.
        # מסלול ה-commit=False (gmail_intake._create_lead_from_draft,
        # intake_after_hours_whatsapp) שולח טלגרם בעצמו בסוף ה-flow.
        if current_user_id is None:
            from app.services import telegram as telegram_service
            await telegram_service.notify_new_lead(lead)
    return lead


# ===================== קריאה =====================

async def get_lead_or_404(db: AsyncSession, lead_id: UUID) -> Lead:
    # populate_existing מאלץ overwrite של identity-map cache במידה והליד
    # נטען קודם באותו session. חיוני אחרי Core update() שעקף את ה-ORM —
    # אחרת היה מוחזר instance עם שדות ישנים (expire_on_commit=False).
    result = await db.execute(
        select(Lead)
        .where(Lead.id == lead_id)
        .execution_options(populate_existing=True)
    )
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
    closed: bool | None = None,
) -> tuple[list[Lead], int]:
    """מחזיר (items, total).

    `closed`:
    - **True** → רק לידים סגורים (WON/LOST/ARCHIVED), ממוינים לפי
      `closed_at` יורד. תצוגת טאב הארכיון (§12.12).
    - **None / False** → רק לידים **פתוחים**. לידים סגורים לעולם לא
      מופיעים ברשימה הראשית (§12.12 — "סגורים בארכיון בלבד"). cursor
      bugbot: הגרסה הישנה `if closed:` החזירה הכל כש-closed=None וגרמה
      ל-WON/LOST/ARCHIVED להיחשף ב-/leads.

    סינון לפי `status` מופעל בנפרד מעל ה-default — אם user שולח
    `status=WON` ב-main list, התוצאה ריקה (closed תמיד נחסם).
    """
    from sqlalchemy import or_

    base = select(Lead)
    if status:
        base = base.where(Lead.status == status)
    if closed is True:
        # טאב הארכיון — שלושת הסטטוסים הסגורים יחד (status יחיד לא מספיק).
        base = base.where(
            Lead.status.in_([s.value for s in CLOSED_LEAD_STATUSES])
        )
    else:
        # רשימה ראשית — closed=None ו-False כאחד מוציאים סגורים (§12.12).
        base = base.where(
            Lead.status.notin_([s.value for s in CLOSED_LEAD_STATUSES])
        )
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
        # escape תווי ILIKE wildcard בתוך הקלט — אחרת "50%" היה תופס כל
        # מי שמתחיל ב-50, ו-"test_name" היה מתאים ל-"testXname".
        # backslash ראשון בסדר ה-replacement כדי לא לדפוק את ה-escapes הבאים.
        escaped_term = (
            term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        )
        pattern = f"%{escaped_term}%"
        filters = [
            Lead.full_name.ilike(pattern, escape="\\"),
            Lead.organization_name.ilike(pattern, escape="\\"),
        ]
        if digits:
            # ספרות בלבד — אין בהן % או _, אז אין צורך ב-escape
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

    # מיון: בארכיון לפי תאריך סגירה יורד (החדש למעלה); אחרת לפי updated_at יורד.
    # nullslast — ליד סגור תמיד עם closed_at, אבל ליתר ביטחון לא לדחוף NULL לראש.
    order_col = (
        Lead.closed_at.desc().nullslast() if closed else Lead.updated_at.desc()
    )
    items_stmt = (
        base.order_by(order_col)
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

    # אם נועה בחרה service_category במפורש (אישור ההצעה או בחירה ידנית
    # אחרת) — מנקים את ה-suggested. ה-banner ב-UI נעלם, ההחלטה סופית.
    if "service_category" in updates and updates["service_category"] is not None:
        lead.suggested_service_category = None
        lead.suggested_service_subtype = None

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


# ===================== אישור הצעת AI לסיווג =====================

async def approve_ai_classification(
    db: AsyncSession, lead_id: UUID, current_user_id: UUID | None
) -> Lead:
    """מעתיק suggested_service_category/subtype → actual + מנקה suggested.

    נקרא מ-POST /leads/{id}/approve-classification בעקבות לחיצה על "אישור"
    ב-banner. אם אין הצעה ממתינה (suggested_service_category is None) —
    raises ValidationError. אם service_category כבר מאוכלסת (נועה כבר
    בחרה ידנית בעבר) — COALESCE שומר עליה, רק suggested מתנקה (idempotent).
    """
    # ולידציית קיום (404 vs 422). לא חלק מהאטומיות — אם הליד נמחק בין
    # ה-SELECT ל-UPDATE, ה-UPDATE יחזיר rowcount=0 וניזרק ValidationError.
    await get_lead_or_404(db, lead_id)

    # אטומי (כלל 2): UPDATE עם WHERE suggested IS NOT NULL + rowcount.
    # שני requests מקבילים — רק אחד יקבל rowcount=1; השני ייכשל ב-422,
    # ולכן רק activity log אחד יירשם. COALESCE שומר על idempotency:
    # אם service_category כבר מאוכלסת (נועה בחרה ידנית קודם) — היא
    # נשמרת, רק ה-suggested מתנקה.
    result = await db.execute(
        update(Lead)
        .where(
            Lead.id == lead_id,
            Lead.suggested_service_category.is_not(None),
        )
        .values(
            # אם service_category ריקה — מעתיקים *את הזוג* (category +
            # subtype) מההצעה. אם כבר מאוכלסת — שני השדות נשמרים. CASE
            # ולא COALESCE כי subtype תלוי category: לוקחים subtype מההצעה
            # רק אם גם category נלקחת ממנה (אחרת ייווצר זוג לא-עקבי כמו
            # category=workshops + subtype=voice_development).
            service_category=func.coalesce(
                Lead.service_category, Lead.suggested_service_category
            ),
            service_subtype=case(
                (Lead.service_category.is_(None), Lead.suggested_service_subtype),
                else_=Lead.service_subtype,
            ),
            suggested_service_category=None,
            suggested_service_subtype=None,
        )
    )
    if result.rowcount == 0:
        raise ValidationError("אין הצעת סיווג ממתינה לליד הזה.")

    await log_activity(
        db,
        lead_id=lead_id,
        activity_type=ActivityType.LEAD_UPDATED,
        performed_by=current_user_id,
        metadata={
            "fields": ["service_category", "service_subtype"],
            "ai_classification_approved": True,
        },
    )

    # כלל 15: service עושה flush, route עושה commit. re-fetch דרך
    # get_lead_or_404 — populate_existing מבטל את ה-identity-map cache
    # שיכול היה להחזיק ערכים ישנים אחרי ה-Core update.
    await db.flush()
    return await get_lead_or_404(db, lead_id)


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
        # closed_at מתעדכן רק כשהסטטוס *באמת* משתנה. סגירה חוזרת לאותו
        # סטטוס (WON→WON כדי לעדכן closed_value) שומרת על תאריך הסגירה
        # המקורי — אחרת ליד שנסגר לפני שבועות היה נכנס בטעות לסיכום
        # הרווחיות של השבוע הנוכחי.
        "closed_at": case(
            (Lead.status != target.value, func.now()),
            else_=Lead.closed_at,
        ),
        "updated_at": func.now(),
    }
    # כלכלת ה-deal — רק כשסוגרים כ-WON. ב-LOST/ARCHIVED אין הכנסה.
    if target == LeadStatus.WON:
        values["closed_value"] = payload.closed_value
        values["actual_hours"] = payload.actual_hours
    else:
        # מאפסים — אם הליד היה WON קודם ונסגר עכשיו כ-LOST, הערכים הישנים
        # היו מטעים את חישוב הרווחיות.
        values["closed_value"] = None
        values["actual_hours"] = None

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

    # ביטול משימות פתוחות לליד הסגור — אחרת הן ימשיכו להופיע ב"פעולות
    # היום" וייקחו מקום לפעולות שעדיין רלוונטיות. local import למניעת circular.
    from app.constants import TaskStatus
    from app.models.task import Task

    await db.execute(
        update(Task)
        .where(
            Task.lead_id == lead_id,
            Task.status.in_(
                [TaskStatus.OPEN.value, TaskStatus.SNOOZED.value]
            ),
        )
        .values(status=TaskStatus.CANCELED.value)
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
            # מנקים נתוני סגירה — הליד שוב פתוח, ה-deal לא קרה
            closed_at=None,
            closed_value=None,
            actual_hours=None,
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


async def get_lead_emails(db: AsyncSession, lead_id: UUID):
    """מייל נכנס שקושרו לליד, מהחדש לישן.

    משתמש ב-idx_email_messages_lead (lead_id + DESC received_at). received_at
    יכול להיות None ב-rows ישנים — nullslast() + secondary sort על created_at
    כ-tie-breaker יציב.
    """
    await get_lead_or_404(db, lead_id)

    from app.models.email_message import EmailMessage  # local — מונע circular
    stmt = (
        select(EmailMessage)
        .where(EmailMessage.lead_id == lead_id)
        .order_by(
            EmailMessage.received_at.desc().nullslast(),
            EmailMessage.created_at.desc(),
        )
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_dormant_suggestion(db: AsyncSession, lead_id: UUID):
    """ה-dormant_suggestion task הפתוח של הליד (§19 D.1), או None.

    מוחזר לכל המלצה פתוחה — כולל פסיבית (archive/no_action) — כי הכרטיס מציג
    אותה תמיד. אם touchpoint סגר אותה (AUTO_CLOSE) — לא תוחזר (הליד כבר טופל).
    """
    await get_lead_or_404(db, lead_id)

    from app.constants import TaskStatus, TaskType
    from app.models.task import Task

    stmt = (
        select(Task)
        .where(
            Task.lead_id == lead_id,
            Task.type == TaskType.DORMANT_SUGGESTION.value,
            Task.status.in_([TaskStatus.OPEN.value, TaskStatus.SNOOZED.value]),
        )
        .order_by(Task.created_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()
