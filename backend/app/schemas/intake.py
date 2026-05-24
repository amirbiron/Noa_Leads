"""
סכמות intake — קליטת לידים מטופס/מייל/הזנה ידנית.
"""

from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from app.constants import ServiceCategory


class IntakeFormRequest(BaseModel):
    """קלט מטופס באתר — שדות מינימליים, פתוח לציבור."""

    full_name: str = Field(min_length=1, max_length=200)
    phone: str | None = Field(default=None, max_length=20)
    email: EmailStr | None = None
    organization_name: str | None = Field(default=None, max_length=200)
    # אופציונלי לפי Spec §7.1 (F-04). יסווג אחר כך מהכרטיס / AI בפאזה 3.
    service_category: ServiceCategory | None = None
    service_subtype: str | None = Field(default=None, max_length=100)
    message: str | None = Field(default=None, max_length=5000)

    # UTM — נרשם אוטומטית מ-querystring/redirect
    utm_source: str | None = Field(default=None, max_length=100)
    utm_campaign: str | None = Field(default=None, max_length=100)
    utm_content: str | None = Field(default=None, max_length=100)


class IntakeResponse(BaseModel):
    """תשובה לקליטת ליד — id וייתכן auto-reply לפי שעות עבודה."""

    lead_id: UUID
    auto_reply_message: str | None = None  # null = נכנס בשעות עבודה רגילות


class IntakeEmailRequest(BaseModel):
    """webhook מ-Gmail (פאזה 3) — שלד בלבד בשלב הנוכחי."""

    from_email: EmailStr
    from_name: str | None = None
    subject: str | None = None
    body: str | None = None
    received_at: str | None = None  # ISO timestamp
