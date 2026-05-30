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
    PriorityLevel,
    SourceChannel,
    TaskStatus,
    TaskType,
    UserRole,
    WaitingOn,
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


# הערה: compute_tomorrow_focus_block ו-compute_attention_items_block הם DB-backed
# (תיקון #6: tomorrow כולל attention + לידי VIP/ארגון) — נבדקים ב-integration למטה.


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
    """open_total / stuck>7d / stale_proposal>4d / overdue tasks.

    הליד/task נוצרים עם `created_at` מפורש לפני `_NOW`, כי `_open_state`
    מסנן על `created_at <= as_of` (לא רק על current status) — בלי תאריך
    מפורש server-side default = NOW אמיתי, ש-> _NOW (קבוע הבדיקה),
    והלידים לא נספרים.
    """
    one_hour_ago = _NOW - timedelta(hours=1)
    # ליד פתוח רגיל (לא תקוע):
    await _mk_lead(db, created_at=one_hour_ago)
    # ליד תקוע: task פעיל due לפני 10 ימים:
    stuck_lead = await _mk_lead(db, created_at=one_hour_ago)
    db.add(Task(
        lead_id=stuck_lead.id, type=TaskType.FOLLOWUP.value,
        status=TaskStatus.OPEN.value,
        created_at=one_hour_ago,
        due_at=_NOW - timedelta(days=10),
    ))
    # הצעה תקועה (נשלחה לפני 5 ימים):
    await _mk_lead(
        db, created_at=one_hour_ago,
        status=LeadStatus.PROPOSAL_SENT.value,
        proposal_sent_at=_NOW - timedelta(days=5),
    )
    await db.flush()

    state = await si._open_state(db, _NOW)
    assert state["open_leads_total"] >= 3
    assert state["stuck_leads_count"] >= 1
    assert state["stale_proposals_count"] >= 1
    assert state["overdue_tasks_count"] >= 1


async def test_open_state_excludes_post_anchor_activity(db):
    """Regression cursor bot: snapshot ב-`as_of` נשען על שדות זמן ולא על
    current state — פעילות שקרתה אחרי `as_of` לא משויכת אליו.

    תרחיש: cron של weekly summary רץ ראשון בבוקר, כ-9 שעות אחרי week_end.
    שדה `open_leads_end_of_week` חייב לשקף את המצב ב-week_end (סוף שבת),
    לא ב-cron time — אחרת ליד שנוצר ראשון בבוקר נספר כפתוח-בסוף-שבוע, וליד
    שנסגר ראשון בבוקר נחסר אף-על-פי שהיה פתוח בסוף-השבוע.
    """
    as_of = _NOW
    before = as_of - timedelta(days=1)
    after = as_of + timedelta(hours=12)

    baseline = await si._open_state(db, as_of)

    # (א) ליד שנוצר *אחרי* as_of → לא היה קיים אז → לא נספר.
    await _mk_lead(db, created_at=after)
    # (ב) ליד שנוצר לפני as_of ונסגר *אחרי* → היה פתוח אז → נספר.
    await _mk_lead(
        db, created_at=before, status=LeadStatus.WON.value, closed_at=after
    )
    # (ג) ליד שנוצר ונסגר לפני as_of → לא נספר.
    await _mk_lead(
        db, created_at=before, status=LeadStatus.LOST.value, closed_at=before,
    )
    # (ד) ליד שנוצר לפני as_of ועדיין פתוח → נספר.
    open_lead = await _mk_lead(db, created_at=before)

    # (ה) task overdue ב-as_of שהושלם רק *אחרי* as_of → היה אקטיבי
    # ב-as_of, אז נחשב overdue ב-as_of (גם אם current status=DONE).
    db.add(Task(
        lead_id=open_lead.id, type=TaskType.FOLLOWUP.value,
        status=TaskStatus.DONE.value,
        created_at=before,
        due_at=as_of - timedelta(days=1),
        completed_at=after,
    ))
    # (ו) task שנוצר *אחרי* as_of → לא היה קיים אז → לא overdue ב-as_of.
    db.add(Task(
        lead_id=open_lead.id, type=TaskType.FOLLOWUP.value,
        status=TaskStatus.OPEN.value,
        created_at=after,
        due_at=after + timedelta(hours=1),
    ))
    await db.flush()

    state = await si._open_state(db, as_of)
    # פתוחים ב-as_of: (ב) ו-(ד). (א) טרם נוצר, (ג) כבר נסגר.
    assert state["open_leads_total"] - baseline["open_leads_total"] == 2
    # overdue ב-as_of: (ה) בלבד. (ו) טרם נוצר.
    assert state["overdue_tasks_count"] - baseline["overdue_tasks_count"] == 1

    # ודא שב-future (אחרי `after`) הספירות זזות: (א) מצטרף ל-open;
    # (ב) יוצא; (ה) יוצא מ-overdue (completed_at <= future).
    state_future = await si._open_state(db, after + timedelta(hours=1))
    open_delta_future = (
        state_future["open_leads_total"] - baseline["open_leads_total"]
    )
    assert open_delta_future == 2  # (א) ו-(ד); (ב) נסגר, (ג) נסגר.


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
    # 9 ימים פחות 3 שעות — gap.days מעגל כלפי מטה ל-8 (תיעוד "שמרני, לא
    # מנפח את 'ימי השתיקה'" בקוד). העיקר: הערך נמדד מה-outbound *הקודם*
    # לפני ה-inbound, לא מ-last_outbound_at (שהוא לפני שעה).
    assert "8 ימי שתיקה" in block


async def test_silence_break_anchors_on_proposal_sent(db):
    """
    regression: אם ה-outbound האחרון לפני תגובת הלקוח היה *שליחת הצעה*
    (PROPOSAL_SENT), הוא ה-anchor לחישוב השתיקה — לא מסר/שיחה ישנים יותר.
    PROPOSAL_SENT כלול ב-_OUTBOUND_CONTACT_TYPES (עקבי עם set_last_outbound
    של mark_proposal_sent ועם backfill של first_outbound_at).
    """
    lead = await _mk_lead(db, full_name="רינה")
    db.add_all([
        # מסר ישן (לא ה-anchor הנכון):
        Activity(lead_id=lead.id, type=ActivityType.OUTBOUND_MESSAGE_LOGGED.value,
                 created_at=_NOW - timedelta(days=20)),
        # הצעה נשלחה לפני 8 ימים — זה ה-anchor הנכון:
        Activity(lead_id=lead.id, type=ActivityType.PROPOSAL_SENT.value,
                 created_at=_NOW - timedelta(days=8)),
        # הלקוח שבר שתיקה:
        Activity(lead_id=lead.id, type=ActivityType.INBOUND_MESSAGE_LOGGED.value,
                 created_at=_NOW - timedelta(hours=2)),
    ])
    await db.flush()

    block = await si.compute_highlighted_leads_block(db, _NOW - timedelta(hours=24), _NOW)
    assert "רינה" in block
    # 8 ימים פחות 2 שעות → 7 (מעוגל מטה). נמדד מההצעה (8 ימים), לא מהמסר (20).
    assert "7 ימי שתיקה" in block


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


async def test_silence_break_reset_by_recent_call(db):
    """
    שיחה עדכנית (CALL_COMPLETED לפני יומיים) מאפסת את שעון השתיקה — גם אם
    ההודעה האחרונה הייתה לפני 20 יום. הליד לא יוצג כ"שבר שתיקה ארוכה".
    """
    lead = await _mk_lead(db, full_name="אבי")
    db.add_all([
        Activity(lead_id=lead.id, type=ActivityType.OUTBOUND_MESSAGE_LOGGED.value,
                 created_at=_NOW - timedelta(days=20)),
        Activity(lead_id=lead.id, type=ActivityType.CALL_COMPLETED.value,
                 created_at=_NOW - timedelta(days=2)),
        Activity(lead_id=lead.id, type=ActivityType.INBOUND_MESSAGE_LOGGED.value,
                 created_at=_IN_WINDOW),
    ])
    await db.flush()

    block = await si.compute_highlighted_leads_block(db, _NOW - timedelta(hours=24), _NOW)
    assert "אבי" not in block  # הפער מהשיחה = יומיים < 7 → לא highlight


async def test_attention_block_dedups_same_lead(db):
    """ליד שהוא גם הצעה תקועה וגם תקוע → מופיע פעם אחת בלבד."""
    lead = await _mk_lead(
        db, full_name="כפול", status=LeadStatus.PROPOSAL_SENT.value,
        proposal_sent_at=_NOW - timedelta(days=5),
    )
    db.add(Task(
        lead_id=lead.id, type=TaskType.PROPOSAL_FOLLOWUP.value,
        status=TaskStatus.OPEN.value, due_at=_NOW - timedelta(days=10),
    ))
    await db.flush()

    block = await si.compute_attention_items_block(db, _NOW)
    assert block.count("כפול") == 1  # לא כפילות
    # מופיע לפי הקריטריון בעל העדיפות הגבוהה (הצעה תקועה).
    assert "הצעה ללא מענה" in block


async def test_attention_items_block_stale_proposal(db):
    """הצעה תקועה מופיעה ב-block עם מספר הימים."""
    await _mk_lead(
        db, full_name="דניאל", status=LeadStatus.PROPOSAL_SENT.value,
        proposal_sent_at=_NOW - timedelta(days=5),
    )
    block = await si.compute_attention_items_block(db, _NOW)
    assert "הצעה ללא מענה" in block
    assert "דניאל" in block


async def test_attention_stuck_days_from_status_changed_at(db):
    """תיקון #3: 'ימים בסטטוס נוכחי' מחושב מ-status_changed_at (לא מ-due_at)."""
    lead = await _mk_lead(
        db, full_name="תקוע", status_changed_at=_NOW - timedelta(days=9),
    )
    # task תקוע (due לפני 10 ימים) — מזהה את הליד כתקוע:
    db.add(Task(
        lead_id=lead.id, type=TaskType.FOLLOWUP.value,
        status=TaskStatus.OPEN.value, due_at=_NOW - timedelta(days=10),
    ))
    await db.flush()

    block = await si.compute_attention_items_block(db, _NOW)
    assert "ליד תקוע" in block
    # 9 ימים מ-status_changed_at — לא 10 (שזה due_at של ה-task):
    assert "ימים בסטטוס נוכחי: 9" in block


async def test_tomorrow_focus_vip_plus_attention_pointer(db):
    """
    תיקון #6 (מזוקק): tomorrow_focus כולל ליד VIP/ארגון שהכדור אצלנו +
    שורת מצביע לעומס ה-attention, *בלי* לשכפל את שורות ה-attention עצמן.
    """
    # ליד עם הצעה תקועה → ייכנס ל-attention (לא ל-tomorrow verbatim):
    await _mk_lead(
        db, full_name="דניאל", status=LeadStatus.PROPOSAL_SENT.value,
        proposal_sent_at=_NOW - timedelta(days=5), waiting_on=WaitingOn.NOAH.value,
    )
    # ליד VIP פתוח שהכדור אצל נועה (לא ב-attention) → תוספת ב-tomorrow:
    await _mk_lead(
        db, full_name="שרון", priority_level=PriorityLevel.VIP.value,
        waiting_on=WaitingOn.NOAH.value,
    )
    lines, seen = await si._collect_attention_items(db, _NOW)
    tomorrow = await si.compute_tomorrow_focus_block(db, _NOW, lines, seen)

    assert tomorrow is not None
    assert "שרון" in tomorrow             # תוספת ה-VIP
    assert "(VIP)" in tomorrow
    assert "דניאל" not in tomorrow        # לא משוכפל — הוא בסקציית attention
    assert "דורש מעקב" in tomorrow        # שורת המצביע לעומס ה-attention


async def test_tomorrow_focus_none_when_only_attention(db):
    """
    אין ליד VIP/ארגון — גם אם יש פריט attention, tomorrow מושמט (None).
    (משחזר את תקפות few-shot דוגמה 2: tomorrow=null למרות attention קיים.)
    """
    # הצעה תקועה (attention) אך הליד אינו VIP ואינו ארגוני:
    await _mk_lead(
        db, full_name="רגיל", status=LeadStatus.PROPOSAL_SENT.value,
        proposal_sent_at=_NOW - timedelta(days=5), waiting_on=WaitingOn.NOAH.value,
    )
    lines, seen = await si._collect_attention_items(db, _NOW)
    assert lines  # יש פריט attention
    tomorrow = await si.compute_tomorrow_focus_block(db, _NOW, lines, seen)
    assert tomorrow is None


async def test_tomorrow_focus_none_when_empty(db):
    """אין attention ואין VIP/ארגון שממתין לנו → tomorrow מושמט (None)."""
    # ליד פתוח רגיל שהכדור אצל הלקוח — לא עומד בקריטריון:
    await _mk_lead(db, full_name="רגיל", waiting_on=WaitingOn.CLIENT.value)
    lines, seen = await si._collect_attention_items(db, _NOW)
    tomorrow = await si.compute_tomorrow_focus_block(db, _NOW, lines, seen)
    assert tomorrow is None


async def test_status_changed_at_trigger(db):
    """
    ה-DB trigger מקדם status_changed_at רק בשינוי status בפועל, לא בכל UPDATE.
    """
    from sqlalchemy import update

    lead = await _mk_lead(
        db, status=LeadStatus.IN_PROGRESS.value,
        status_changed_at=_NOW - timedelta(days=30),
    )
    await db.flush()

    # UPDATE בלי שינוי status — status_changed_at לא אמור לזוז:
    await db.execute(
        update(Lead).where(Lead.id == lead.id).values(full_name="שם חדש")
    )
    await db.flush()
    await db.refresh(lead)
    before = lead.status_changed_at

    # UPDATE עם שינוי status — status_changed_at אמור להתעדכן ל-now():
    await db.execute(
        update(Lead).where(Lead.id == lead.id).values(status=LeadStatus.PROPOSAL_SENT.value)
    )
    await db.flush()
    await db.refresh(lead)

    assert before == _NOW - timedelta(days=30)   # לא זז ב-UPDATE ללא שינוי status
    assert lead.status_changed_at > before       # זז בשינוי status


async def test_build_daily_user_prompt_renders(db):
    """ה-prompt המלא נבנה בלי KeyError ומכיל את הסקציות הקבועות."""
    await _mk_lead(db, created_at=_IN_WINDOW)
    prompt = await si.build_daily_user_prompt(db, now_utc=_NOW)
    assert "פעילות נועה היום:" in prompt
    assert "פגישות" not in prompt  # המטריקה הוסרה
    assert "מצב פתוחים בסוף היום:" in prompt


# ===================== בדיקות שבועיות — pure =====================

# יום ראשון בבוקר — מועד ריצת הסיכום השבועי (מסכם את השבוע שהסתיים אתמול).
_SUNDAY_NOW = datetime(2026, 5, 31, 5, 0, tzinfo=timezone.utc)


def test_trend_direction_normal():
    """כיוון רגיל: עלייה/ירידה/יציב."""
    assert si._trend_direction(12, 7) == "עלייה"
    assert si._trend_direction(2, 12) == "ירידה"
    assert si._trend_direction(5, 5) == "יציב"


def test_trend_direction_lower_is_better():
    """זמן תגובה — נמוך עדיף: שיפור/הרעה/יציב (אומת מול §5.8)."""
    assert si._trend_direction(2, 4, lower_is_better=True) == "שיפור"
    assert si._trend_direction(6, 2, lower_is_better=True) == "הרעה"
    assert si._trend_direction(3, 3, lower_is_better=True) == "יציב"


def test_trend_direction_none_is_stable():
    """ערך None בצד כלשהו → 'יציב' (לא ממציאים כיוון)."""
    assert si._trend_direction(None, 5) == "יציב"
    assert si._trend_direction(5, None) == "יציב"
    assert si._trend_direction(None, None, lower_is_better=True) == "יציב"


def test_compute_weeks_in_system_and_comparison_boundary(monkeypatch):
    """weeks_in_system: שבוע ראשון=1; has_comparison_data בגבול 4 שבועות."""

    class _S:
        system_start_date = date(2026, 5, 3)  # יום ראשון

    monkeypatch.setattr(si, "get_settings", lambda: _S())
    # אותו שבוע → 1
    assert si.compute_weeks_in_system(date(2026, 5, 3)) == 1
    # שבוע 3 (start + 14 ימים) → <4 → אין השוואה
    assert si.compute_weeks_in_system(date(2026, 5, 17)) == 3
    assert si.has_comparison_data(si.compute_weeks_in_system(date(2026, 5, 17))) is False
    # שבוע 4 (start + 21 ימים) → השוואה
    assert si.compute_weeks_in_system(date(2026, 5, 24)) == 4
    assert si.has_comparison_data(si.compute_weeks_in_system(date(2026, 5, 24))) is True
    # תאריך לפני start → רצפה 1
    assert si.compute_weeks_in_system(date(2026, 1, 1)) == 1


async def test_trends_block_no_comparison_when_young(db, monkeypatch):
    """פחות מ-4 שבועות → trends_block = 'NO_COMPARISON' (בלי שאילתות השוואה)."""
    block = await si.compute_trends_block(
        db,
        _SUNDAY_NOW - timedelta(days=7),
        _SUNDAY_NOW,
        weeks_in_system=2,
        curr_new_leads=5,
        curr_won=1,
    )
    assert block == "NO_COMPARISON"


def test_next_week_focus_heuristic():
    """היוריסטיקת פוקוס: תקועים → הצעות תקועות → None."""
    assert si.compute_next_week_focus_suggestion(
        None, _NOW, {"stuck_leads_count": 2, "stale_proposals_count": 0}
    ).startswith("לעבור על הלידים התקועים")
    assert "פולואפ" in si.compute_next_week_focus_suggestion(
        None, _NOW, {"stuck_leads_count": 0, "stale_proposals_count": 1}
    )
    assert si.compute_next_week_focus_suggestion(
        None, _NOW, {"stuck_leads_count": 0, "stale_proposals_count": 0}
    ) is None


async def test_build_weekly_user_prompt_renders(db):
    """ה-prompt השבועי נבנה בלי KeyError וכל 24 ה-placeholders מולאו."""
    import string

    await _mk_lead(db, created_at=_SUNDAY_NOW - timedelta(days=3))
    prompt = await si.build_weekly_user_prompt(db, now_utc=_SUNDAY_NOW)

    # אין placeholder שנותר לא-ממולא ({...}).
    placeholders = {
        fn for _, fn, _, _ in string.Formatter().parse(si.WEEKLY_USER_TEMPLATE) if fn
    }
    assert len(placeholders) == 24
    assert "{" not in prompt.replace("{{", "").replace("}}", "")

    # עוגני סקציה קבועים:
    assert "פעילות נועה השבוע:" in prompt
    assert "מצב שבועי כללי:" in prompt
    assert "תובנות אסטרטגיות שחושבו מראש:" in prompt


# ===================== בדיקות שבועיות — integration (DB) =====================

# מקבע system_start_date מוקדם מספיק כך ש-has_comparison_data=true בבדיקות.
class _EarlyStart:
    system_start_date = date(2026, 1, 1)


def _patch_early_start(monkeypatch):
    monkeypatch.setattr(si, "get_settings", lambda: _EarlyStart())


async def test_last_week_bounds_sunday_to_sunday(db):
    """גבולות השבוע הקודם: ראשון 00:00 → ראשון הבא 00:00 (זמן ישראל)."""
    start, end = si._last_week_bounds(_SUNDAY_NOW)
    from app.utils.work_hours import to_israel_tz

    start_local = to_israel_tz(start)
    end_local = to_israel_tz(end)
    # שני הגבולות הם חצות מקומי, יום ראשון, בהפרש 7 ימים:
    assert start_local.weekday() == 6  # ראשון
    assert end_local.weekday() == 6
    assert start_local.hour == 0 and start_local.minute == 0
    assert (end_local.date() - start_local.date()).days == 7
    # _SUNDAY_NOW הוא 2026-05-31 (ראשון) → שבוע שעבר 2026-05-24..2026-05-31.
    assert start_local.date() == date(2026, 5, 24)
    assert end_local.date() == date(2026, 5, 31)


async def test_avg_first_response_hours(db):
    """AVG(first_outbound_at - created_at) בשעות, על לידים שנוצרו בחלון."""
    window_start = _SUNDAY_NOW - timedelta(days=7)
    window_end = _SUNDAY_NOW
    created = window_start + timedelta(days=1)
    # ליד עם תגובה אחרי שעתיים:
    await _mk_lead(
        db, created_at=created, first_outbound_at=created + timedelta(hours=2)
    )
    # ליד עם תגובה אחרי 4 שעות:
    await _mk_lead(
        db, created_at=created, first_outbound_at=created + timedelta(hours=4)
    )
    # ליד בלי first_outbound_at — לא נספר:
    await _mk_lead(db, created_at=created, first_outbound_at=None)
    await db.flush()

    avg = await si._avg_first_response_hours(db, window_start, window_end)
    assert avg == 3  # ממוצע (2+4)/2


async def test_avg_first_response_hours_none_when_empty(db):
    """אין לידים מתאימים → None."""
    avg = await si._avg_first_response_hours(
        db, _SUNDAY_NOW - timedelta(days=7), _SUNDAY_NOW
    )
    assert avg is None


async def test_newly_dormant_count(db):
    """סופר משימות DORMANT_SUGGESTION שנוצרו בחלון."""
    window_start = _SUNDAY_NOW - timedelta(days=7)
    window_end = _SUNDAY_NOW
    lead = await _mk_lead(db)
    db.add_all([
        Task(
            lead_id=lead.id, type=TaskType.DORMANT_SUGGESTION.value,
            status=TaskStatus.OPEN.value, due_at=window_start,
            created_at=window_start + timedelta(days=1),
        ),
        # מחוץ לחלון — לא נספר:
        Task(
            lead_id=lead.id, type=TaskType.DORMANT_SUGGESTION.value,
            status=TaskStatus.OPEN.value, due_at=window_start,
            created_at=window_start - timedelta(days=2),
        ),
        # סוג אחר — לא נספר:
        Task(
            lead_id=lead.id, type=TaskType.FOLLOWUP.value,
            status=TaskStatus.OPEN.value, due_at=window_start,
            created_at=window_start + timedelta(days=1),
        ),
    ])
    await db.flush()

    count = await si._newly_dormant_count(db, window_start, window_end)
    assert count == 1


async def test_conversion_by_category_30d(db):
    """יחס המרה לפי service_category ב-30 יום, top-3 לפי מכנה."""
    closed = _SUNDAY_NOW - timedelta(days=5)
    # קליניקה: 1 WON, 1 LOST → 50%
    await _mk_lead(db, service_category="clinic", status=LeadStatus.WON.value, closed_at=closed)
    await _mk_lead(db, service_category="clinic", status=LeadStatus.LOST.value, closed_at=closed)
    # סדנאות: 1 WON, 0 LOST → 100%
    await _mk_lead(
        db, service_category="workshops", status=LeadStatus.WON.value, closed_at=closed
    )
    await db.flush()

    lines = await si._conversion_by_category_30d(db, _SUNDAY_NOW)
    joined = "\n".join(lines)
    assert "conversion rate בקליניקה: 50% ב-30 הימים האחרונים" in joined
    assert "conversion rate בסדנאות והרצאות: 100% ב-30 הימים האחרונים" in joined


async def test_avg_days_to_won_by_category_30d(db):
    """זמן ממוצע מליד ל-WON בקטגוריה עם הכי הרבה WON."""
    closed = _SUNDAY_NOW - timedelta(days=2)
    # קליניקה: 2 WON (10 ו-20 ימים → ממוצע 15)
    await _mk_lead(
        db, service_category="clinic", status=LeadStatus.WON.value,
        created_at=closed - timedelta(days=10), closed_at=closed,
    )
    await _mk_lead(
        db, service_category="clinic", status=LeadStatus.WON.value,
        created_at=closed - timedelta(days=20), closed_at=closed,
    )
    await db.flush()

    line = await si._avg_days_to_won_by_category_30d(db, _SUNDAY_NOW)
    assert line is not None
    assert "זמן ממוצע מליד ל-WON בקליניקה: 15 ימים" in line


async def test_avg_days_to_won_none_when_no_won(db):
    """אין WON בחלון → None."""
    line = await si._avg_days_to_won_by_category_30d(db, _SUNDAY_NOW)
    assert line is None


async def test_top_source_by_won_30d(db):
    """מקור עם הכי הרבה WON ב-30 יום."""
    closed = _SUNDAY_NOW - timedelta(days=3)
    await _mk_lead(
        db, source_channel=SourceChannel.FACEBOOK.value,
        status=LeadStatus.WON.value, closed_at=closed,
    )
    await _mk_lead(
        db, source_channel=SourceChannel.FACEBOOK.value,
        status=LeadStatus.WON.value, closed_at=closed,
    )
    await _mk_lead(
        db, source_channel=SourceChannel.INSTAGRAM.value,
        status=LeadStatus.WON.value, closed_at=closed,
    )
    await db.flush()

    line = await si._top_source_by_won_30d(db, _SUNDAY_NOW)
    assert line == "- מקור עם הכי הרבה סגירות ב-30 הימים האחרונים: פייסבוק"


async def test_precomputed_insights_empty(db):
    """אין נתונים → '(ריק - לא מספיק נתונים)'."""
    block = await si.compute_precomputed_insights_block(db, _SUNDAY_NOW)
    assert block == "(ריק - לא מספיק נתונים)"


async def test_trends_block_vs_previous_week(db, monkeypatch):
    """trends_block: השוואת לידים/WON/זמן-תגובה/מקור מול השבוע הקודם."""
    _patch_early_start(monkeypatch)
    week_start, week_end = si._last_week_bounds(_SUNDAY_NOW)
    prev_start, prev_end = si._prev_week_bounds(week_start)

    # שבוע נוכחי: 2 לידים חדשים, מקור instagram, תגובה 2 שעות, 1 WON.
    c1 = week_start + timedelta(days=1)
    await _mk_lead(
        db, created_at=c1, source_channel=SourceChannel.INSTAGRAM.value,
        first_outbound_at=c1 + timedelta(hours=2),
    )
    await _mk_lead(
        db, created_at=c1, source_channel=SourceChannel.INSTAGRAM.value,
        first_outbound_at=c1 + timedelta(hours=2),
    )
    await _mk_lead(
        db, created_at=week_start - timedelta(days=40),
        status=LeadStatus.WON.value, closed_at=c1,
    )
    # שבוע קודם: 1 ליד חדש, מקור facebook, תגובה 4 שעות, 0 WON.
    p1 = prev_start + timedelta(days=1)
    await _mk_lead(
        db, created_at=p1, source_channel=SourceChannel.FACEBOOK.value,
        first_outbound_at=p1 + timedelta(hours=4),
    )
    await db.flush()

    movement = await si._lead_movement(db, week_start, week_end)
    block = await si.compute_trends_block(
        db, week_start, week_end, weeks_in_system=20,
        curr_new_leads=movement["new_leads_count"],
        curr_won=movement["won_count"],
    )
    assert "לידים חדשים: 2 השבוע מול 1 שבוע קודם. כיוון: עלייה." in block
    assert "זמן תגובה ראשון ממוצע: 2 שעות השבוע מול 4 שעות שבוע קודם. כיוון: שיפור." in block
    assert "מקור מוביל השבוע: אינסטגרם. שבוע קודם: פייסבוק." in block
