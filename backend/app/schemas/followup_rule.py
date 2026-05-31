"""Pydantic schemas ל-FollowupRule (§17.1).

Read: כל השדות. Update: כל השדות אופציונליים, rule_key לא ניתן לעדכון
(הוא חלק מה-path). הוספה/מחיקה אסורה דרך ה-API — הכללים מחוברים
ל-TaskType בקוד.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class FollowupRuleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    rule_key: str
    interval_value: int
    interval_unit: Literal["hours", "days"]
    repeat_count: int
    repeat_interval_value: int
    repeat_interval_unit: Literal["hours", "days"]


class FollowupRuleUpdate(BaseModel):
    """Partial update — שדה None = לא לעדכן. exclude_unset ב-service."""

    interval_value: int | None = Field(default=None, gt=0)
    interval_unit: Literal["hours", "days"] | None = None
    repeat_count: int | None = Field(default=None, ge=1)
    repeat_interval_value: int | None = Field(default=None, gt=0)
    repeat_interval_unit: Literal["hours", "days"] | None = None
