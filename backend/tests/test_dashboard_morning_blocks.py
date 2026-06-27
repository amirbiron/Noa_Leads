"""
בדיקות ל"לוח הבוקר" של מסך הבית (PR בלוקים 2+3 — פירוק רשימות):
- get_new_leads_24h_count: לידים שנכנסו ב-24h האחרונות (ללא תלות בסטטוס).
- get_urgent_no_first_response_count: לידים פתוחים 48h+ עם FIRST_RESPONSE/
  LECTURE_INQUIRY פתוח (= לא נשלח עליהם מענה ראשון).

integration מול Postgres — מדלגות אם אין DB (fixture `db`). דפוס תואם
test_dashboard_ai_summaries.py / test_dormant_suggestion_surfacing.py
(delta-based, עמיד לנתונים אחרים בdb).
"""

from datetime import datetime, timedelta, timezone

from app.constants import CLOSED_LEAD_STATUSES, LeadStatus, TaskStatus, TaskType
from app.models.lead import Lead
from app.models.task import Task
from app.services import dashboard as dashboard_service


async def _mk_lead(db, *, created_at: datetime, status: str = "NEW") -> Lead:
    """ליד מינימלי עם created_at מבוקר. status מקבל value (str) של LeadStatus."""
    lead = Lead(
        full_name="בדיקה",
        source_channel="manual",
        status=status,
        created_at=created_at,
    )
    db.add(lead)
    await db.flush()
    return lead


async def _mk_first_response_task(
    db,
    *,
    lead_id,
    status: str = TaskStatus.OPEN.value,
    due_at: datetime | None = None,
    task_type: str = TaskType.FIRST_RESPONSE.value,
) -> Task:
    if due_at is None:
        # ברירת מחדל: SLA 24h מהגעה — לא משפיע על הספירה שמסתמכת על Lead.created_at.
        due_at = datetime.now(timezone.utc) + timedelta(hours=24)
    task = Task(
        lead_id=lead_id,
        type=task_type,
        status=status,
        due_at=due_at,
        origin_rule="intake_first_response",
    )
    db.add(task)
    await db.flush()
    return task


# ===================== Block 2: lead 24h count =====================


async def test_new_leads_24h_counts_only_recent(db):
    """לידים ב-24h האחרונות נספרים; ישנים יותר לא. delta-based."""
    now = datetime.now(timezone.utc)
    before = await dashboard_service.get_new_leads_24h_count(db)

    # נספרים: ב-23h ו-1h. לא נספר: ב-25h.
    await _mk_lead(db, created_at=now - timedelta(hours=23))
    await _mk_lead(db, created_at=now - timedelta(hours=1))
    await _mk_lead(db, created_at=now - timedelta(hours=25))

    after = await dashboard_service.get_new_leads_24h_count(db)
    assert after - before == 2


async def test_new_leads_24h_ignores_status(db):
    """Block 2 הוא מד נפח — סטטוס לא מסנן. NEW/IN_PROGRESS/WON ב-24h כולם נספרים."""
    now = datetime.now(timezone.utc)
    before = await dashboard_service.get_new_leads_24h_count(db)

    await _mk_lead(db, created_at=now - timedelta(hours=5), status=LeadStatus.NEW.value)
    await _mk_lead(
        db, created_at=now - timedelta(hours=5), status=LeadStatus.IN_PROGRESS.value
    )
    await _mk_lead(db, created_at=now - timedelta(hours=5), status=LeadStatus.WON.value)

    after = await dashboard_service.get_new_leads_24h_count(db)
    assert after - before == 3


# ===================== Block 3: urgent (48h no first response) =====================


async def test_urgent_no_response_includes_48h_open_first_response(db):
    """ליד שנכנס לפני 50h עם FIRST_RESPONSE פתוח → נספר."""
    now = datetime.now(timezone.utc)
    before = await dashboard_service.get_urgent_no_first_response_count(db)

    lead = await _mk_lead(db, created_at=now - timedelta(hours=50))
    await _mk_first_response_task(db, lead_id=lead.id, status=TaskStatus.OPEN.value)

    after = await dashboard_service.get_urgent_no_first_response_count(db)
    assert after - before == 1


async def test_urgent_no_response_excludes_under_48h(db):
    """ליד שנכנס לפני 47h עם FIRST_RESPONSE פתוח → לא נספר עדיין (סף 48h)."""
    now = datetime.now(timezone.utc)
    before = await dashboard_service.get_urgent_no_first_response_count(db)

    lead = await _mk_lead(db, created_at=now - timedelta(hours=47))
    await _mk_first_response_task(db, lead_id=lead.id, status=TaskStatus.OPEN.value)

    after = await dashboard_service.get_urgent_no_first_response_count(db)
    assert after - before == 0


async def test_urgent_no_response_excludes_responded(db):
    """ליד שנכנס לפני 50h אבל FIRST_RESPONSE נסגר (DONE) → לא נספר.

    זה ה-flow הרגיל: נועה ענתה → close_touchpoint_tasks סגר את ה-task.
    """
    now = datetime.now(timezone.utc)
    before = await dashboard_service.get_urgent_no_first_response_count(db)

    lead = await _mk_lead(db, created_at=now - timedelta(hours=50))
    await _mk_first_response_task(db, lead_id=lead.id, status=TaskStatus.DONE.value)

    after = await dashboard_service.get_urgent_no_first_response_count(db)
    assert after - before == 0


async def test_urgent_no_response_excludes_closed_leads(db):
    """ליד 50h+ עם FIRST_RESPONSE פתוח אבל בסטטוס LOST → לא נספר."""
    now = datetime.now(timezone.utc)
    before = await dashboard_service.get_urgent_no_first_response_count(db)

    # נוודא ש-LOST אכן ב-CLOSED_LEAD_STATUSES (defensive against enum changes)
    assert LeadStatus.LOST in CLOSED_LEAD_STATUSES

    lead = await _mk_lead(
        db, created_at=now - timedelta(hours=50), status=LeadStatus.LOST.value
    )
    await _mk_first_response_task(db, lead_id=lead.id, status=TaskStatus.OPEN.value)

    after = await dashboard_service.get_urgent_no_first_response_count(db)
    assert after - before == 0


async def test_urgent_no_response_counts_lecture_inquiry(db):
    """LECTURE_INQUIRY פתוח 50h+ מתפקד כמו FIRST_RESPONSE — נספר."""
    now = datetime.now(timezone.utc)
    before = await dashboard_service.get_urgent_no_first_response_count(db)

    lead = await _mk_lead(db, created_at=now - timedelta(hours=50))
    await _mk_first_response_task(
        db,
        lead_id=lead.id,
        status=TaskStatus.OPEN.value,
        task_type=TaskType.LECTURE_INQUIRY.value,
    )

    after = await dashboard_service.get_urgent_no_first_response_count(db)
    assert after - before == 1
