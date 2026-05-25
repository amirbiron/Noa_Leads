"""
סכמות email_message — קריאה לכרטיס הליד.

ה-Read schema חושף רק שדות תצוגה (CLAUDE.md כלל 3 — לא לחשוף מידע פנימי
ב-API responses):
- חושף: from, to, subject, cleaned_text, received_at, created_at, id.
- *לא* חושף: gmail_message_id (מזהה Gmail פנימי), raw_html (לא ב-MVP —
  אין sanitizer), cleaning_metadata (debug ל-AI), classification_retry_count
  (cron state), processing_status (workflow פנימי), direction (תמיד inbound).
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class EmailMessageRead(BaseModel):
    """מייל נכנס שקושר לליד — לתצוגה בכרטיס."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    from_address: str | None
    to_address: str | None
    subject: str | None
    cleaned_text: str | None
    # received_at מ-Gmail internalDate (לא זמן ה-webhook). לעיתים None
    # ב-rows ישנים שנשמרו ללא internalDate.
    received_at: datetime | None
    created_at: datetime
