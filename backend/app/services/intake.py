"""
שירות intake — קליטת לידים מכל המקורות (טופס/מייל/ידני).
"""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import ActivityType, SourceChannel
from app.models.lead import Lead
from app.schemas.intake import IntakeFormRequest, IntakeResponse
from app.schemas.lead import LeadCreate
from app.services import leads as leads_service
from app.services.activities import log_activity
from app.utils.work_hours import after_hours_reply_message, is_working_time


async def intake_from_form(
    db: AsyncSession, payload: IntakeFormRequest
) -> IntakeResponse:
    """
    קליטה מטופס באתר (public).
    create_lead כבר יוצר את משימת first_response באותה טרנזקציה.
    אם מחוץ לשעות עבודה — מחזיר auto_reply_message.
    """
    lead_create = LeadCreate(
        full_name=payload.full_name,
        phone=payload.phone,
        email=payload.email,
        organization_name=payload.organization_name,
        service_category=payload.service_category,
        service_subtype=payload.service_subtype,
        source_channel=SourceChannel.FORM,
        source_detail=payload.message,
        utm_source=payload.utm_source,
        utm_campaign=payload.utm_campaign,
        utm_content=payload.utm_content,
    )

    # current_user_id=None — קליטה ציבורית, אין משתמש מחובר
    lead = await leads_service.create_lead(db, lead_create, current_user_id=None)

    now = datetime.now(timezone.utc)
    auto_reply = None if is_working_time(now) else after_hours_reply_message(now)
    return IntakeResponse(lead_id=lead.id, auto_reply_message=auto_reply)


async def intake_manual(
    db: AsyncSession, payload: LeadCreate, current_user_id: UUID | None
) -> IntakeResponse:
    """
    הזנה ידנית מהאפליקציה — לרוב מהנייד אחרי שיחת טלפון/וואטסאפ.
    לא מחזיר auto-reply (לא רלוונטי בהזנה ידנית).
    """
    # כופים source_channel=MANUAL — זה ה-endpoint לכך
    payload_copy = payload.model_copy(update={"source_channel": SourceChannel.MANUAL})
    lead = await leads_service.create_lead(db, payload_copy, current_user_id)
    return IntakeResponse(lead_id=lead.id, auto_reply_message=None)


async def intake_after_hours_whatsapp(
    db: AsyncSession,
    full_name: str,
    phone: str,
    message: str | None,
    current_user_id: UUID | None,
) -> Lead:
    """
    קליטת פנייה שהגיעה בוואטסאפ מחוץ לשעות עבודה.
    לפי האפיון: לא שולחים auto-reply בוואטסאפ — שומר על מגע אישי.
    במקום זה: יוצרים ליד + תיעוד שזה אחרי שעות.
    """
    payload = LeadCreate(
        full_name=full_name,
        phone=phone,
        service_category="clinic",  # ברירת מחדל — נועה תעדכן ידנית
        source_channel=SourceChannel.WHATSAPP,
        source_detail=message,
    )
    lead = await leads_service.create_lead(db, payload, current_user_id)

    # תיעוד הקשר אחרי שעות — חשוב ל-audit
    await log_activity(
        db,
        lead_id=lead.id,
        activity_type=ActivityType.INBOUND_MESSAGE_LOGGED,
        performed_by=current_user_id,
        content=message,
        metadata={"after_hours": True, "channel": "whatsapp"},
    )
    await db.commit()
    return lead
