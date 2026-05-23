"""
שירות activities — תיעוד אוטומטי של פעולות (audit log).
"""

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import ActivityType
from app.models.activity import Activity


async def log_activity(
    db: AsyncSession,
    lead_id: UUID,
    activity_type: ActivityType | str,
    performed_by: UUID | None = None,
    content: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> Activity:
    """
    יוצר רשומת activity לתיעוד. לא מבצע commit — הקורא אחראי.
    זה מאפשר transaction אחד לכל הפעולה (status change + activity log).
    """
    activity = Activity(
        lead_id=lead_id,
        type=str(activity_type),
        performed_by=performed_by,
        content=content,
        activity_metadata=metadata,
    )
    db.add(activity)
    await db.flush()
    return activity
