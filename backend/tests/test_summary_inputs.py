"""
בדיקות שכבת החישוב לסיכום יומי — C.1 §6.3 (app/services/summary_inputs.py).

שני סוגי בדיקות:
- pure: פונקציות ללא DB (פורמט, תרגום, היוריסטיקה) — רצות תמיד.
- integration: ספירות/blocks מול Postgres אמיתי — מדלגות אם אין DB (fixture `db`).

עיקרון נבדק: "AI מפרש, לא מחשב" — כל מספר/מחרוזת שמוזנת ל-AI נכונה ועקבית.
"""

from datetime import date, datetime, timedelta, timezone

from app.constants import (
    ActivityType,
    LeadStatus,
    SourceChannel,
    TaskStatus,
    TaskType,
    UserRole,
)
from app.models.activity import Activity
from app.models.lead import Lead
from app.models.task import Task
from app.models.user import User
from app.services import summary_inputs as si

# ===================== בדיקות pure (ללא DB) =====================


def test_compute_days_in_system(monkeypatch):
    """days_in_system = ימי-לוח מאז start, כולל יום ההתחלה (=1)."""

    class _S:
        system_start_date = date(2026, 5, 23)

    monkeypatch.setattr(si, "get_settings", lambda: _S())
    assert si.compute_days_in_system(date(2026, 5, 23)) == 1
    assert si.compute_days_in_system(date(2026, 5, 30)) == 8
    # תאריך לפני ההתחלה (תצורה שגויה) — רצפה 1, לא שלילי.
    assert si.compute_days_in_system(date(2026, 5, 1)) == 1


def test_hebrew_weekday():
    # 2026-05-31 הוא יום ראשון.
    assert si._hebrew_weekday(date(2026, 5, 31)) == "יום ראשון"
    assert si._hebrew_weekday(date(2026, 5, 25)) == "יום שני"


def test_format_breakdown_sources():
    rows = [("instagram", 2), ("facebook", 1), ("referral", 1)]
    out = si._format_breakdown(rows, si.SOURCE_CHANNEL_HE, prefix="מ")
    assert out == "2 מאינסטגרם, 1 מפייסבוק, 1 מהמלצה"


def test_format_breakdown_empty_and_unknown():
    assert si._format_breakdown([], si.SOURCE_CHANNEL_HE, prefix="מ") == "-"
    assert si._format_breakdown([(None, 3)], si.SOURCE_CHANNEL_HE) == "3 אחר"
    # ערך עם count=0 לא נספר.
    assert si._format_breakdown([("facebook", 0)], si.SOURCE_CHANNEL_HE) == "-"


def test_lead_display_name():
    assert si._lead_display_name(Lead(full_name="דנה", organization_name=None)) == "דנה"
    assert (
        si._lead_display_name(Lead(full_name="רוני", organization_name="חברת ABC"))
        == "רוני מחברת ABC"
    )
    assert (
        si._lead_display_name(Lead(full_name="", organization_name="עיריית רעננה"))
        == "עיריית רעננה"
    )
    assert si._lead_display_name(Lead(full_name="", organization_name=None)) == "ללא"


def test_role_label():
    assert si._role_label(UserRole.OWNER.value) == "נועה"
    assert si._role_label(UserRole.ASSISTANT.value) == "העוזרת"
    assert si._role_label(None) == "-"


def test_tomorrow_focus_suggestion():
    assert si.compute_tomorrow_focus_suggestion({}, "(ריק)") is None
    stale = "- סוג: הצעה ללא מענה | ליד: דניאל | ימים מאז שליחה: 5"
    assert "הצעה" in si.compute_tomorrow_focus_suggestion({}, stale)
    stuck = "- סוג: ליד תקוע | ליד: דנה | ימים בסטטוס נוכחי: 9"
    assert "תקוע" in si.compute_tomorrow_focus_suggestion({}, stuck)


# ===================== בדיקות integration (DB) =====================

_NOW = datetime(2026, 5, 30, 16, 0, tzinfo=timezone.utc)  # קבוע ל-determinism
_IN_WINDOW = _NOW - timedelta(hours=2)
_BEFORE_WINDOW = _NOW - timedelta(hours=30)


async def _mk_user(db, role: str) -> User:
    """יוצר משתמש עם email ייחודי (rollback מנקה)."""
    import uuid

    u = User(email=f"{role}-{uuid.uuid4().hex[:8]}@test.local", name=role, role=role)
    db.add(u)
    await db.flush()
    return u


async def _mk_lead(db, **kw) -> Lead:
    defaults = dict(
        full_name="ליד בדיקה",
        source_channel=SourceChannel.MANUAL.value,
        status=LeadStatus.IN_PROGRESS.value,
    )
    defaults.update(kw)
    lead = Lead(**defaults)
    db.add(lead)
    await db.flush()
    return lead


async def test_activity_counts_by_role(db):
    """שיחות והודעות יוצאות מפולחות נכון לפי תפקיד; מחוץ לחלון לא נספר."""
    noa = await _mk_user(db, UserRole.OWNER.value)
    assistant = await _mk_user(db, UserRole.ASSISTANT.value)
    lead = await _mk_lead(db)

    def act(user, atype, when):
        return Activity(lead_id=lead.id, performed_by=user.id, type=atype, created_at=when)

    db.add_all([
        act(noa, ActivityType.CALL_COMPLETED.value, _IN_WINDOW),
        act(noa, ActivityType.CALL_COMPLETED.value, _IN_WINDOW),
        act(noa, ActivityType.TEMPLATE_MARKED_SENT.value, _IN_WINDOW),
        act(assistant, ActivityType.OUTBOUND_MESSAGE_LOGGED.value, _IN_WINDOW),
        act(assistant, ActivityType.MANUAL_MESSAGE_LOGGED.value, _IN_WINDOW),
        # מחוץ לחלון — לא נספר:
        act(noa, ActivityType.CALL_COMPLETED.value, _BEFORE_WINDOW),
    ])
    await db.flush()

    counts = await si._activity_counts_by_role(db, _NOW - timedelta(hours=24), _NOW)
    assert counts["noa_calls"] == 2
    assert counts["noa_outbound"] == 1
    assert counts["assistant_calls"] == 0
    assert counts["assistant_outbound"] == 2


async def test_tasks_completed_by_role(db):
    """משימות DONE בחלון מפולחות לפי assignee.role."""
    noa = await _mk_user(db, UserRole.OWNER.value)
    assistant = await _mk_user(db, UserRole.ASSISTANT.value)
    lead = await _mk_lead(db)

    def task(user, when, status=TaskStatus.DONE.value):
        return Task(
            lead_id=lead.id,
            assigned_to=user.id,
            type=TaskType.FOLLOWUP.value,
            status=status,
            due_at=when,
            completed_at=when if status == TaskStatus.DONE.value else None,
        )

    db.add_all([
        task(noa, _IN_WINDOW),
        task(noa, _IN_WINDOW),
        task(assistant, _IN_WINDOW),
        task(noa, _BEFORE_WINDOW),  # מחוץ לחלון
        task(noa, _IN_WINDOW, status=TaskStatus.OPEN.value),  # לא DONE
    ])
    await db.flush()

    counts = await si._tasks_completed_by_role(db, _NOW - timedelta(hours=24), _NOW)
    assert counts["noa_tasks"] == 2
    assert counts["assistant_tasks"] == 1


async def test_lead_movement_segments_and_closures(db):
    """לידים חדשים בחלון, פילוח מקור/subtype, WON/LOST לפי closed_at."""
    await _mk_lead(
        db, created_at=_IN_WINDOW, source_channel=SourceChannel.INSTAGRAM.value,
        service_subtype="voice_rehab",
    )
    await _mk_lead(
        db, created_at=_IN_WINDOW, source_channel=SourceChannel.INSTAGRAM.value,
        service_subtype="voice_rehab",
    )
    await _mk_lead(
        db, created_at=_IN_WINDOW, source_channel=SourceChannel.REFERRAL.value,
        service_subtype="production_guidance",
    )
    # נסגר WON בחלון:
    await _mk_lead(
        db, created_at=_BEFORE_WINDOW, status=LeadStatus.WON.value, closed_at=_IN_WINDOW
    )
    # נסגר LOST מחוץ לחלון — לא נספר:
    await _mk_lead(
        db, created_at=_BEFORE_WINDOW, status=LeadStatus.LOST.value,
        closed_at=_BEFORE_WINDOW,
    )

    mv = await si._lead_movement(db, _NOW - timedelta(hours=24), _NOW)
    assert mv["new_leads_count"] == 3
    assert mv["new_leads_by_source_text"] == "2 מאינסטגרם, 1 מהמלצה"
    assert "2 שיקום קול" in mv["new_leads_by_category_text"]
    assert "1 ליווי הפקה אישית" in mv["new_leads_by_category_text"]
    assert mv["won_count"] == 1
    assert mv["lost_count"] == 0


async def test_open_state_counts(db):
    """open_total / stuck>7d / stale_proposal>4d / overdue tasks."""
    # ליד פתוח רגיל (לא תקוע):
    await _mk_lead(db)
    # ליד תקוע: task פעיל due לפני 10 ימים:
    stuck_lead = await _mk_lead(db)
    db.add(Task(
        lead_id=stuck_lead.id, type=TaskType.FOLLOWUP.value,
        status=TaskStatus.OPEN.value, due_at=_NOW - timedelta(days=10),
    ))
    # הצעה תקועה (נשלחה לפני 5 ימים):
    await _mk_lead(
        db, status=LeadStatus.PROPOSAL_SENT.value,
        proposal_sent_at=_NOW - timedelta(days=5),
    )
    await db.flush()

    state = await si._open_state(db, _NOW)
    assert state["open_leads_total"] >= 3
    assert state["stuck_leads_count"] >= 1
    assert state["stale_proposals_count"] >= 1
    assert state["overdue_tasks_count"] >= 1


async def test_highlighted_leads_block_silence_break(db):
    """ליד שענה אחרי 10 ימי שתיקה (outbound לפני 10 ימים → inbound בחלון)."""
    lead = await _mk_lead(db, full_name="מירב כהן", service_subtype="voice_rehab")
    db.add_all([
        Activity(lead_id=lead.id, type=ActivityType.OUTBOUND_MESSAGE_LOGGED.value,
                 created_at=_NOW - timedelta(days=10)),
        Activity(lead_id=lead.id, type=ActivityType.INBOUND_MESSAGE_LOGGED.value,
                 created_at=_IN_WINDOW),
    ])
    await db.flush()

    block = await si.compute_highlighted_leads_block(db, _NOW - timedelta(hours=24), _NOW)
    assert "מירב כהן" in block
    assert "ימי שתיקה" in block
    assert str(lead.id) not in block  # לא חושפים IDs


async def test_silence_break_survives_reply_in_same_window(db):
    """
    regression: גם אם נועה ענתה ללקוח *אחרי* ההודעה הנכנסת באותו חלון
    (outbound חדש), שבירת השתיקה עדיין מזוהה — כי מודדים מ-outbound שקדם
    ל-inbound, לא מ-last_outbound_at הדנורמלי.
    """
    lead = await _mk_lead(db, full_name="יעל")
    db.add_all([
        # outbound ישן (תחילת השתיקה):
        Activity(lead_id=lead.id, type=ActivityType.OUTBOUND_MESSAGE_LOGGED.value,
                 created_at=_NOW - timedelta(days=9)),
        # הלקוח שבר שתיקה:
        Activity(lead_id=lead.id, type=ActivityType.INBOUND_MESSAGE_LOGGED.value,
                 created_at=_NOW - timedelta(hours=3)),
        # נועה ענתה מיד אחרי — outbound חדש בתוך החלון:
        Activity(lead_id=lead.id, type=ActivityType.TEMPLATE_MARKED_SENT.value,
                 created_at=_NOW - timedelta(hours=1)),
    ])
    await db.flush()

    block = await si.compute_highlighted_leads_block(db, _NOW - timedelta(hours=24), _NOW)
    assert "יעל" in block
    assert "9 ימי שתיקה" in block


async def test_highlighted_leads_block_booked_via_meeting_approved(db):
    """
    מעבר ל-BOOKED נרשם כ-MEETING_APPROVED (לא STATUS_CHANGED). regression
    guard: ה-highlight של 'סטטוס עבר ל-BOOKED' חייב להופיע מ-MEETING_APPROVED.
    """
    noa = await _mk_user(db, UserRole.OWNER.value)
    lead = await _mk_lead(db, full_name="רוני", status=LeadStatus.BOOKED.value)
    db.add(Activity(
        lead_id=lead.id, performed_by=noa.id,
        type=ActivityType.MEETING_APPROVED.value, created_at=_IN_WINDOW,
        activity_metadata={"booking_id": "x"},
    ))
    await db.flush()

    block = await si.compute_highlighted_leads_block(db, _NOW - timedelta(hours=24), _NOW)
    assert "רוני" in block
    assert "BOOKED" in block
    assert 'בוצע ע"י: נועה' in block


async def test_attention_items_block_stale_proposal(db):
    """הצעה תקועה מופיעה ב-block עם מספר הימים."""
    await _mk_lead(
        db, full_name="דניאל", status=LeadStatus.PROPOSAL_SENT.value,
        proposal_sent_at=_NOW - timedelta(days=5),
    )
    block = await si.compute_attention_items_block(db, _NOW)
    assert "הצעה ללא מענה" in block
    assert "דניאל" in block


async def test_build_daily_user_prompt_renders(db):
    """ה-prompt המלא נבנה בלי KeyError ומכיל את הסקציות הקבועות."""
    await _mk_lead(db, created_at=_IN_WINDOW)
    prompt = await si.build_daily_user_prompt(db, now_utc=_NOW)
    assert "פעילות נועה היום:" in prompt
    assert "פגישות" not in prompt  # המטריקה הוסרה
    assert "מצב פתוחים בסוף היום:" in prompt
