"""
סכמות ליד — יצירה, קריאה, עדכון, סגירה.
"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.constants import (
    CLOSED_LEAD_STATUSES,
    ClosureReason,
    LeadStatus,
    PreferredContact,
    PriorityLevel,
    ServiceCategory,
    SourceChannel,
    WaitingOn,
)
from app.utils.phone import normalize_for_storage


# ולידציה משותפת לטלפון — מונעת ייבוא של תווי שליטה / סינטקס פעיל,
# ומפרמטת מספרים ישראליים לפורמט אחיד עם hyphen.
# משמשת גם ב-LeadCreate וגם ב-LeadUpdate כדי לא ליצור drift.
# ראה: docs/Skills/israeli-phone-formatter/SKILL.md
_PHONE_ALLOWED_CHARS = set("0123456789+-() .*")


def _normalize_phone(v: str | None) -> str | None:
    if v is None or v == "":
        return None
    cleaned = v.strip()
    if not cleaned:
        return None
    # סינון תווים לא חוקיים לפני העברה ל-normalize_for_storage שמטפל בסמנטיקה
    if not all(c in _PHONE_ALLOWED_CHARS for c in cleaned):
        raise ValueError("מספר טלפון מכיל תווים לא חוקיים")
    # אימות תבנית ישראלית מלאה + פורמטינג אחיד.
    # ValueError ניזרק עם הסבר בעברית אם נראה ישראלי אבל לא תקין.
    return normalize_for_storage(cleaned)


# ===================== יצירה =====================

class LeadCreate(BaseModel):
    """יצירת ליד חדש — שדות מינימליים בלבד מהמוביילי."""

    full_name: str = Field(min_length=1, max_length=200)
    phone: str | None = Field(default=None, max_length=20)
    email: EmailStr | None = None
    organization_name: str | None = Field(default=None, max_length=200)

    # אופציונלי לפי Spec §7.1 — שם/טלפון/מקור בלבד חובה. service_category
    # יסווג אחר כך מהכרטיס (ידנית או AI בפאזה 3). ראה F-04 ב-spec-deviations.
    service_category: ServiceCategory | None = None
    service_subtype: str | None = Field(default=None, max_length=100)

    source_channel: SourceChannel
    source_detail: str | None = None
    utm_source: str | None = Field(default=None, max_length=100)
    utm_campaign: str | None = Field(default=None, max_length=100)
    utm_content: str | None = Field(default=None, max_length=100)

    preferred_contact: PreferredContact = PreferredContact.WHATSAPP
    priority_level: PriorityLevel = PriorityLevel.NORMAL

    owner_id: UUID | None = None
    personal_note: str | None = None

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str | None) -> str | None:
        return _normalize_phone(v)


# ===================== עדכון =====================

class LeadUpdate(BaseModel):
    """עדכון ליד — כל השדות אופציונליים."""

    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    phone: str | None = Field(default=None, max_length=20)
    email: EmailStr | None = None
    organization_name: str | None = Field(default=None, max_length=200)

    service_category: ServiceCategory | None = None
    service_subtype: str | None = Field(default=None, max_length=100)

    waiting_on: WaitingOn | None = None
    priority_level: PriorityLevel | None = None
    preferred_contact: PreferredContact | None = None

    owner_id: UUID | None = None
    personal_note: str | None = None

    source_detail: str | None = None
    utm_source: str | None = Field(default=None, max_length=100)
    utm_campaign: str | None = Field(default=None, max_length=100)
    utm_content: str | None = Field(default=None, max_length=100)

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str | None) -> str | None:
        # אותה ולידציה כמו ב-LeadCreate — חייב להישאר עקבי לכל הפעולות
        return _normalize_phone(v)

    @field_validator(
        "full_name",
        "waiting_on",
        "priority_level",
        "preferred_contact",
    )
    @classmethod
    def reject_explicit_null(cls, v):
        # שדות NOT NULL ב-DB. ב-PATCH מותר להשמיט אותם (הם נשארים), אבל
        # אסור לשלוח null מפורש — זה היה גורם ל-IntegrityError ב-commit
        # במקום שגיאת ולידציה ברורה.
        # service_category הוצא מהרשימה ב-F-04 — הוא NULLABLE עכשיו.
        if v is None:
            raise ValueError("שדה חובה — לא ניתן לאפס. אפשר להשמיט מה-payload.")
        return v


# ===================== סגירה / פתיחה מחדש =====================

class LeadTransferRequest(BaseModel):
    """העברת ליד לבעלים אחר (לדוגמה: נועה → עוזרת)."""

    target_user_id: UUID
    handoff_note: str | None = Field(default=None, max_length=1000)


class LeadCloseRequest(BaseModel):
    """סגירת ליד כ-WON / LOST / ARCHIVED."""

    target_status: LeadStatus
    closure_reason: ClosureReason | None = None
    note: str | None = None
    # רלוונטי רק ב-WON — שדות הרווחיות. ניתן להשאיר None אם לא יודעים.
    closed_value: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    actual_hours: Decimal | None = Field(default=None, ge=0, decimal_places=2)

    @field_validator("target_status")
    @classmethod
    def must_be_closed_status(cls, v: LeadStatus) -> LeadStatus:
        if v not in CLOSED_LEAD_STATUSES:
            raise ValueError("סטטוס יעד חייב להיות WON, LOST או ARCHIVED")
        return v


# ===================== קריאה =====================

class LeadRead(BaseModel):
    """ייצוג מלא של ליד."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    full_name: str
    phone: str | None
    email: str | None
    organization_name: str | None

    service_category: str | None  # אופציונלי לפי Spec §7.1 (F-04)
    service_subtype: str | None

    status: str
    waiting_on: str
    priority_level: str
    preferred_contact: str

    owner_id: UUID | None

    next_action_type: str | None
    next_action_due_at: datetime | None
    needs_attention: bool

    source_channel: str
    source_detail: str | None
    utm_source: str | None
    utm_campaign: str | None
    utm_content: str | None

    last_inbound_at: datetime | None
    last_outbound_at: datetime | None
    last_activity_type: str | None
    reply_boost_until: datetime | None
    proposal_sent_at: datetime | None

    dormant_flag: bool
    is_duplicate_suspected: bool
    is_returning_customer: bool

    closure_reason: str | None
    closed_at: datetime | None
    closed_value: Decimal | None
    actual_hours: Decimal | None
    personal_note: str | None
    booking_token: UUID

    created_at: datetime
    updated_at: datetime


class LeadListItem(BaseModel):
    """ייצוג מקוצר לליד בתוך רשימה — חוסך bandwidth בנייד."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    full_name: str
    organization_name: str | None
    service_category: str | None  # אופציונלי לפי Spec §7.1 (F-04)
    service_subtype: str | None
    status: str
    waiting_on: str
    priority_level: str
    preferred_contact: str
    needs_attention: bool
    # נחשף ל-frontend לחישוב צבע real-time (Spec §12.9 — overdue → orange).
    # ה-list view מסתמך על זה במקום needs_attention (שmark_overdue cron
    # מעדכן כל 15 דק' — latency שיוצר מצבים סותרים בין list לכרטיס).
    next_action_due_at: datetime | None
    last_inbound_at: datetime | None
    last_outbound_at: datetime | None
    updated_at: datetime
