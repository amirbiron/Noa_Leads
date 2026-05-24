"""
סכמות צ'יפים מהירים — לקריאה/יצירה/עדכון מעמוד הגדרות.

לפי Spec v2.1 §5.7 + §16.4. 4 השדות הסמנטיים (target_status, waiting_on,
followup_task_type, auto_followup_days) הם nullable ב-DB כדי לתמוך
בchips של נועה שהיא יוצרת ידנית בלי למלא הכל מיד. ה-Create/Update
משתמשים ב-Enums כדי לחסום ערכים חופשיים, וכל validator מאפשר None.
"""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.constants import LeadStatus, TaskType, WaitingOn


# סטטוסים שצ'יפ *לא* יכול להציב — מנוהלים ע"י flows ייעודיים:
# - BOOKING_PENDING / BOOKED נקבעים ע"י booking flow (יצירת/אישור Booking).
#   chip שמציב אותם ישירות יוצר ליד "תקוע" בלי שורה ב-bookings.
# - WON / LOST / ARCHIVED נקבעים ע"י close_lead (closure_reason / closed_at).
# 6 הצ'יפים מ-§16.4 כולם target IN_PROGRESS — מתואם.
_CHIP_FORBIDDEN_TARGETS = frozenset(
    {
        LeadStatus.BOOKING_PENDING,
        LeadStatus.BOOKED,
        LeadStatus.WON,
        LeadStatus.LOST,
        LeadStatus.ARCHIVED,
    }
)


def _validate_chip_target_status(v: LeadStatus | None) -> LeadStatus | None:
    if v is not None and v in _CHIP_FORBIDDEN_TARGETS:
        raise ValueError(
            "הצ'יפ לא יכול להעביר ליד למצב הזה — השתמשי ב-flow הייעודי "
            "(הזמנת תור / סגירת ליד)."
        )
    return v


class QuickActionChipRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    label: str
    # nullable: צ'יפים שנועה הוסיפה ידנית בלי השדות הסמנטיים. ה-frontend
    # לא יציג צ'יפ ש-target_status שלו None (כי קליק לא יודע מה לעשות).
    target_status: str | None
    waiting_on: str | None
    followup_task_type: str | None
    auto_followup_days: int | None
    sort_order: int
    is_active: bool


class QuickActionChipCreate(BaseModel):
    label: str = Field(min_length=1, max_length=100)
    # ה-enums כתבי validation. None מותר — נועה יכולה ליצור chip כbase
    # ולמלא בהמשך דרך UI.
    target_status: LeadStatus | None = None
    waiting_on: WaitingOn | None = None
    followup_task_type: TaskType | None = None
    auto_followup_days: int | None = Field(default=None, ge=1, le=365)
    sort_order: int = 0
    is_active: bool = True

    @field_validator("target_status")
    @classmethod
    def check_target_status(
        cls, v: LeadStatus | None
    ) -> LeadStatus | None:
        return _validate_chip_target_status(v)


class QuickActionChipUpdate(BaseModel):
    """כל השדות אופציונליים — partial update. None *מפורש* מותר לאפס שדה."""

    label: str | None = Field(default=None, min_length=1, max_length=100)
    target_status: LeadStatus | None = None
    waiting_on: WaitingOn | None = None
    followup_task_type: TaskType | None = None
    auto_followup_days: int | None = Field(default=None, ge=1, le=365)
    sort_order: int | None = None
    is_active: bool | None = None

    @field_validator("target_status")
    @classmethod
    def check_target_status(
        cls, v: LeadStatus | None
    ) -> LeadStatus | None:
        return _validate_chip_target_status(v)
