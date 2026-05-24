"""
סכמות צ'יפים מהירים — לקריאה/יצירה/עדכון מעמוד הגדרות.

לפי Spec v2.1 §5.7 + §16.4. 4 השדות הסמנטיים (target_status, waiting_on,
followup_task_type, auto_followup_days) הם nullable ב-DB כדי לתמוך
בchips של נועה שהיא יוצרת ידנית בלי למלא הכל מיד. ה-Create/Update
משתמשים ב-Enums כדי לחסום ערכים חופשיים, וכל validator מאפשר None.
"""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.constants import LeadStatus, TaskType, WaitingOn


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


class QuickActionChipUpdate(BaseModel):
    """כל השדות אופציונליים — partial update. None *מפורש* מותר לאפס שדה."""

    label: str | None = Field(default=None, min_length=1, max_length=100)
    target_status: LeadStatus | None = None
    waiting_on: WaitingOn | None = None
    followup_task_type: TaskType | None = None
    auto_followup_days: int | None = Field(default=None, ge=1, le=365)
    sort_order: int | None = None
    is_active: bool | None = None
