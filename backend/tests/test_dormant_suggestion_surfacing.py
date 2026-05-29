"""
§19 D.1 — בדיקות חשיפה של dormant_suggestion: "תמיד להציג, לא תמיד להקפיץ".

המלצה פסיבית (archive / no_action) נשמרת ומוצגת בכרטיס, אבל לא מוקפצת בשום
מסלול push. כאן מאמתים את המסלול שתוקן: list_stuck_tasks (/tasks/stuck) —
dormant_suggestion נוצר עם due_at=now ולכן הופך "תקוע" (7+ ימים) תוך שבוע;
בלי הסינון, ליד עם המלצת archive היה מופיע ב-/tasks/stuck.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.constants import LeadStatus, TaskStatus, TaskType
from app.models.lead import Lead
from app.models.task import Task
from app.services.dashboard import get_weekly_insights
from app.services.tasks import list_stuck_tasks


async def _make_dormant_lead_with_stuck_suggestion(db, ai_action: str) -> Lead:
    """ליד IN_PROGRESS עם dormant_suggestion 'תקוע' (due לפני 10 ימים)."""
    lead = Lead(
        full_name=f"בדיקה {ai_action}",
        source_channel="manual",
        status=LeadStatus.IN_PROGRESS.value,
    )
    db.add(lead)
    await db.flush()  # booking_token מתמלא ע"י server_default

    stuck_due = datetime.now(timezone.utc) - timedelta(days=10)
    db.add(
        Task(
            lead_id=lead.id,
            type=TaskType.DORMANT_SUGGESTION.value,
            status=TaskStatus.OPEN.value,
            due_at=stuck_due,
            origin_rule="auto_dormant_suggestion",
            task_metadata={
                "ai_action": ai_action,
                "ai_reasoning": "בדיקה",
                "ai_generated_at": stuck_due.isoformat(),
                "model_used": "test",
            },
        )
    )
    await db.flush()
    return lead


@pytest.mark.parametrize("passive_action", ["archive", "no_action"])
async def test_passive_dormant_suggestion_not_in_stuck(db, passive_action):
    """ליד עם dormant_suggestion פסיבי שעבר 7 ימים → לא מופיע ב-/tasks/stuck."""
    lead = await _make_dormant_lead_with_stuck_suggestion(db, passive_action)

    rows = await list_stuck_tasks(db)
    stuck_lead_ids = {lead_obj.id for _task, lead_obj in rows}

    assert lead.id not in stuck_lead_ids


@pytest.mark.parametrize("active_action", ["gentle_followup", "call"])
async def test_active_dormant_suggestion_is_in_stuck(db, active_action):
    """ליד עם dormant_suggestion אקטיבי שעבר 7 ימים → כן מופיע (regression הפוך)."""
    lead = await _make_dormant_lead_with_stuck_suggestion(db, active_action)

    rows = await list_stuck_tasks(db)
    stuck_lead_ids = {lead_obj.id for _task, lead_obj in rows}

    assert lead.id in stuck_lead_ids


async def test_passive_dormant_suggestion_not_in_weekly_stuck_count(db):
    """תובנה שבועית (§13.9): המלצת archive לא מנפחת את stuck_count.

    delta לפני/אחרי — עמיד לנתונים אחרים ב-DB. archive פסיבי לא מוסיף;
    gentle_followup אקטיבי כן מוסיף (regression דו-כיווני).
    """
    before = (await get_weekly_insights(db)).stuck_count

    await _make_dormant_lead_with_stuck_suggestion(db, "archive")
    assert (await get_weekly_insights(db)).stuck_count == before

    await _make_dormant_lead_with_stuck_suggestion(db, "gentle_followup")
    assert (await get_weekly_insights(db)).stuck_count == before + 1
