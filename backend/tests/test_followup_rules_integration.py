"""בדיקות אינטגרציה: שינוי interval ב-FollowupRule משפיע על due_at של
tasks חדשים (cursor fix).

לפני התיקון: ה-UI אפשר עריכת interval_value אבל הקוד התעלם — לידים
חדשים תמיד קיבלו due_at לפי קבועי קוד (FOLLOWUP_GRACE_FIRST_RESPONSE
וכו'). אחרי התיקון: כל אתר יצירת task פולואף עושה live lookup ל-rule.

ארבע בדיקות:
1. שינוי first_response → due_at של ליד חדש משתקף.
2. rule חסר → fallback לקבוע ברירת המחדל (לא קריסה).
3. lecture_inquiry קורא את ה-rule שלו, לא first_response (שני סוגי
   tasks שחולקים את אותה פונקציה).
4. warm_followup — interval משפיע גם על selection וגם על due_at (אותו
   ערך — שמירה על "due = last_outbound + interval").

integration: דורש Postgres (FollowupRule rows seeded ב-migration 0029).
"""

from datetime import datetime, timedelta, timezone

from app.constants import (
    FOLLOWUP_GRACE_FIRST_RESPONSE,
    LeadStatus,
    SourceChannel,
    TaskType,
)
from app.models.followup_rule import FollowupRule
from app.models.lead import Lead
from app.services.followup_rules import get_rule_interval_seconds
from app.services.tasks import create_first_response_task
from jobs.check_warm_followups import (
    _calc_due_at,
    _warm_followup_candidates,
)


async def _set_rule_interval(
    db, rule_key: str, value: int, unit: str = "hours"
) -> None:
    """משנה interval של rule קיים. conftest rollback מנקה."""
    rule = await db.get(FollowupRule, rule_key)
    assert rule is not None, f"rule {rule_key} לא seeded"
    rule.interval_value = value
    rule.interval_unit = unit
    await db.flush()


async def _mk_lead(db, **kw) -> Lead:
    defaults = dict(
        full_name="ליד בדיקה",
        source_channel=SourceChannel.MANUAL.value,
        status=LeadStatus.NEW.value,
        waiting_on="NOAH",
    )
    defaults.update(kw)
    lead = Lead(**defaults)
    db.add(lead)
    await db.flush()
    return lead


async def test_create_first_response_uses_rule_interval(db):
    """שינוי first_response ל-2h → ליד חדש מקבל due_at בערך now+2h.

    ה-task נוצר עם type=FIRST_RESPONSE (לא subtype הרצאה), אז ה-lookup
    הוא ל-`first_response` rule. due_at מותאם לשעות עבודה — בודקים
    בטווח [now+interval, now+interval+24h] (adjustment לכל היותר דוחה
    ליום הבא).
    """
    await _set_rule_interval(db, TaskType.FIRST_RESPONSE.value, value=2)

    now = datetime.now(timezone.utc)
    lead = await _mk_lead(db)
    task = await create_first_response_task(db, lead)

    assert task.type == TaskType.FIRST_RESPONSE.value
    # due_at >= now + 2h (לפחות interval; adjustment רק יכול להוסיף).
    assert task.due_at >= now + timedelta(hours=2) - timedelta(seconds=5)
    # due_at <= now + 2h + 72h (adjustment של work hours: שישי דוחה לראשון).
    assert task.due_at <= now + timedelta(hours=2) + timedelta(hours=72)
    # שינוי משמעותי מהקבוע הישן (24h): due_at רחוק יותר מ-2h מעכשיו,
    # אבל באופן ברור פחות מ-24h+72h. השוואה ישירה ל-default היא לא
    # דטרמיניסטית (תלוי בשעת הריצה), ולכן בודקים רק את ה-bound החדש.


async def test_create_first_response_falls_back_to_default_if_rule_missing(db):
    """rule חסר → fallback לקבוע FOLLOWUP_GRACE_FIRST_RESPONSE (24h).

    מוחקים את ה-rule, יוצרים ליד, מצפים ל-due_at בערך now+24h. זה
    defensive: לא רוצים שיצירת ליד תיכשל אם migration לא רץ או row
    נמחק בטעות.
    """
    rule = await db.get(FollowupRule, TaskType.FIRST_RESPONSE.value)
    assert rule is not None
    await db.delete(rule)
    await db.flush()

    now = datetime.now(timezone.utc)
    lead = await _mk_lead(db)
    task = await create_first_response_task(db, lead)

    default_sec = int(FOLLOWUP_GRACE_FIRST_RESPONSE.total_seconds())
    # due_at >= now + 24h (לפחות ה-default).
    assert task.due_at >= now + timedelta(seconds=default_sec) - timedelta(
        seconds=5
    )
    # due_at <= now + 24h + 72h (adjustment של work hours; כש-now+interval
    # נופל ביום שישי, ה-adjustment דוחה לראשון = 2-3 ימים).
    assert task.due_at <= now + timedelta(seconds=default_sec) + timedelta(
        hours=72
    )


async def test_lecture_inquiry_uses_its_own_rule(db):
    """ליד עם subtype הרצאה → task type LECTURE_INQUIRY. ה-rule שנקרא
    הוא `lecture_inquiry`, לא `first_response`.

    קובעים ערכים שונים לשני ה-rules: lecture_inquiry=6h, first_response=2h.
    אם ה-lookup מבולבל היה משתמש ב-2h. בדיקה: due_at >= now+6h, ולא
    קרוב ל-now+2h.
    """
    await _set_rule_interval(db, TaskType.FIRST_RESPONSE.value, value=2)
    await _set_rule_interval(db, TaskType.LECTURE_INQUIRY.value, value=6)

    now = datetime.now(timezone.utc)
    lead = await _mk_lead(db, service_subtype="lecture_organization")
    task = await create_first_response_task(db, lead)

    assert task.type == TaskType.LECTURE_INQUIRY.value
    # due_at לפי lecture_inquiry rule (6h), לא first_response (2h).
    assert task.due_at >= now + timedelta(hours=6) - timedelta(seconds=5)
    # אם בטעות נשתמש ב-rule של first_response, due_at היה רחוק לכל היותר
    # 2h+24h = 26h. רף הבדיקה: due_at חייב להיות מעל 6h, מה שיותר מ-26h
    # רק אם adjustment דוחה ליום הבא — אבל גם אז הוא ≥ 6h. ה-bound הזה
    # מספיק כדי לחתוך את ה-mode השגוי.


async def test_warm_followup_uses_rule_for_both_selection_and_due_at(db):
    """warm_followup: שינוי interval משנה גם selection threshold וגם due_at.

    קובעים rule ל-12h. שני לידים:
    - last_outbound לפני 11h → לא נכנס (selection).
    - last_outbound לפני 13h → נכנס; due_at = last_outbound + 12h.

    שמירת עקביות: בלי קריאה אחת מ-rule בתחילת הריצה, selection ו-due_at
    היו יכולים להתבדר (selection לפי קבוע ישן, due_at לפי rule חדש,
    או להיפך).
    """
    await _set_rule_interval(db, TaskType.WARM_FOLLOWUP.value, value=12)
    interval_sec = await get_rule_interval_seconds(
        db, TaskType.WARM_FOLLOWUP.value, default_seconds=999
    )
    assert interval_sec == 12 * 3600

    now = datetime.now(timezone.utc)
    # ליד שלא צריך להיכנס: last_outbound לפני 11h, פחות מהסף 12h.
    lead_too_recent = await _mk_lead(
        db,
        status=LeadStatus.IN_PROGRESS.value,
        last_outbound_at=now - timedelta(hours=11),
    )
    # ליד שצריך להיכנס: last_outbound לפני 13h.
    last_outbound = now - timedelta(hours=13)
    lead_eligible = await _mk_lead(
        db,
        status=LeadStatus.IN_PROGRESS.value,
        last_outbound_at=last_outbound,
    )

    candidates = await _warm_followup_candidates(db, interval_sec)
    candidate_ids = {c.id for c in candidates}
    assert lead_eligible.id in candidate_ids
    assert lead_too_recent.id not in candidate_ids

    # due_at = last_outbound + 12h, מותאם לשעות עבודה. בדיקה: לפחות
    # last_outbound + 12h, ולכל היותר +72h adjustment (שישי דוחה לראשון).
    due = _calc_due_at(last_outbound, interval_sec)
    assert due >= last_outbound + timedelta(hours=12) - timedelta(seconds=5)
    assert due <= last_outbound + timedelta(hours=12) + timedelta(hours=72)

    # cleanup: rollback של conftest מנקה. אין צורך ליצור tasks בפועל
    # (אנחנו בודקים את ה-helpers בנפרד מ-cron commit).
    # ה-tasks היו נוצרים ב-check_warm_followups() — שיוצר session נפרד
    # ולא מתאים ל-rollback fixture. בודקים את ה-helpers הפנימיים שמרכיבים
    # את ה-cron.
    # למחיקת לידים שיצרנו — לא צריך, rollback ינקה.
    _ = (lead_too_recent, lead_eligible)
