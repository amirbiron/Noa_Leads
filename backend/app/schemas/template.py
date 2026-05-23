"""
סכמות תבניות — CRUD ו-render.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.constants import TemplateChannel, TemplateTargetAudience


class TemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    channel: TemplateChannel
    target_audience: TemplateTargetAudience | None = None
    body: str = Field(min_length=1)
    # רשימת variables המוטמעים בתבנית, למשל ["customer_name", "service_type"]
    variables: list[str] | None = None
    is_active: bool = True


class TemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    channel: TemplateChannel | None = None
    target_audience: TemplateTargetAudience | None = None
    body: str | None = Field(default=None, min_length=1)
    variables: list[str] | None = None
    is_active: bool | None = None


class TemplateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    channel: str
    target_audience: str | None
    body: str
    variables: list[str] | None
    is_active: bool
    created_by: UUID | None
    created_at: datetime
    updated_at: datetime


class TemplateRenderResponse(BaseModel):
    template_id: UUID
    lead_id: UUID
    rendered_body: str
    channel: str
    # שמות placeholders שהיו ב-body אבל אין להם ערך ב-lead
    missing_variables: list[str]
