"""
summary_inputs — שכבת החישוב לסיכום היומי של C.1 (§6.3 ב-c1-c2-summaries-spec).

עיקרון מנחה: **"AI מפרש, לא מחשב"**. כל הספירות, הפילוחים, וה-blocks
מחושבים כאן בקוד; ה-AI מקבל מחרוזות מבושלות בלבד ורק מנסח אותן.
הפלט של build_daily_user_prompt מוזן ל-generate_daily_summary_text (ai.py)
שמשתמש ב-USER_TEMPLATE מ-app/prompts/daily_summary.py.

מודל החלון (תואם jobs/daily_summary.py הקיים, Spec §5.12):
מטריקות רטרוספקטיביות (פעילות, תנועת לידים) נספרות בחלון 24 שעות אחורה
מרגע הריצה (now-24h → now), *לא* לפי גבולות חצות — כדי שליד/פעולה
שנכנס אחרי שעת הריצה ייכנס לסיכום של מחר ולא ייפול בין הכיסאות.
מטריקות מצב (פתוחים/תקועים/הצעות תקועות) הן snapshot ל-now.

מיפוי ActivityType→מטריקה (מאושר ע"י המוצר):
- שיחות שבוצעו   → CALL_COMPLETED
- הודעות יוצאות  → TEMPLATE_MARKED_SENT + MANUAL_MESSAGE_LOGGED + OUTBOUND_MESSAGE_LOGGED
- משימות שהושלמו → Task.status=DONE (לפי assigned_to→role; ל-Task אין performed_by)
מטריקת "פגישות שהתקיימו" הוסרה לחלוטין — אין ActivityType אמין ל"התקיימה
בפועל", ולפי עקרון הסבילות-הנמוכה-להזיות מטריקה לא אמינה לא נכללת.
"""

import logging
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.config import get_settings
from app.constants import (
    CLOSED_LEAD_STATUSES,
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
from app.prompts.daily_summary import USER_TEMPLATE
from app.prompts.weekly_summary import USER_TEMPLATE as WEEKLY_USER_TEMPLATE
from app.services.tasks import surfaceable_task_condition
from app.utils.labels import (
    SERVICE_CATEGORY_HE,
    SERVICE_SUBTYPE_HE,
    SOURCE_CHANNEL_HE,
)
from app.utils.work_hours import ISRAEL_TZ, to_israel_tz

logger = logging.getLogger("services.summary_inputs")

# ===== קבועי מיפוי =====

# הודעות יוצאות — שלושת ה-ActivityType שמייצגים שליחת *מסר* יוצא (לספירת
# מטריקת "הודעות יוצאות"; שיחות נספרות בנפרד כ-CALL_COMPLETED).
_OUTBOUND_TYPES = (
    ActivityType.TEMPLATE_MARKED_SENT.value,
    ActivityType.MANUAL_MESSAGE_LOGGED.value,
    ActivityType.OUTBOUND_MESSAGE_LOGGED.value,
)

# "מגע יוצא" לצורך מדידת *שתיקה* — כל פנייה יזומה של נועה/העוזרת ללקוח:
# מסרים + שיחות (כולל ניסיון ללא מענה) + שליחת הצעה. רחב מ-_OUTBOUND_TYPES
# בכוונה — שיחה/הצעה שבוצעה אתמול מאפסת את שעון השתיקה, גם אם ההודעה האחרונה
# הייתה מזמן. בלי זה היינו מנפחים את מספר "ימי השתיקה" ושוברים את האמון
# בסיכום (סבילות נמוכה). PROPOSAL_SENT כלול — mark_proposal_sent מסומן
# set_last_outbound=True (state_machine.py), עקבי עם backfill של first_outbound_at
# (migration 0026) שכולל אף הוא proposal_sent.
_OUTBOUND_CONTACT_TYPES = (
    *_OUTBOUND_TYPES,
    ActivityType.CALL_COMPLETED.value,
    ActivityType.CALL_NO_ANSWER.value,
    ActivityType.PROPOSAL_SENT.value,
)

# ימי השבוע בעברית — date.weekday(): שני=0 .. ראשון=6.
_HEBREW_WEEKDAYS = {
    6: "יום ראשון",
    0: "יום שני",
    1: "יום שלישי",
    2: "יום רביעי",
    3: "יום חמישי",
    4: "יום שישי",
    5: "יום שבת",
}

# ספים (תואמים את ההגדרות הקנוניות ב-services/dashboard.py — כלל 10, בלי drift):
# - תקוע: ליד פתוח עם task פעיל surfaceable שה-due_at שלו עבר ב-7+ ימים.
# - הצעה תקועה: PROPOSAL_SENT שנשלח לפני 4+ ימים בלי מענה.
_STUCK_DAYS = 7
_STALE_PROPOSAL_DAYS = 4

# כמה ימי שתיקה מצדיקים highlight "שבר שתיקה" (§6.3.1).
_SILENCE_BREAK_DAYS = 7

# תקרת פריטים לכל block (§3.4 + §6.3).
_BLOCK_LIMIT = 3


# ===== עזרי זמן/קונטקסט =====

def _window_bounds(now_utc: datetime) -> tuple[datetime, datetime]:
    """חלון רטרוספקטיבי של 24 שעות אחורה (now-24h → now)."""
    return now_utc - timedelta(hours=24), now_utc


def compute_days_in_system(today: date) -> int:
    """
    מספר הימים מאז תחילת המערכת (SYSTEM_START_DATE קבוע ב-config).
    פרשנות: ימי-לוח שחלפו, +1 כך שיום ההתחלה עצמו = 1 (ולא 0).
    אם today קודם ל-start (תצורה שגויה) — מוחזר 1 כרצפה.
    """
    start = get_settings().system_start_date
    return max(1, (today - start).days + 1)


def _hebrew_weekday(d: date) -> str:
    return _HEBREW_WEEKDAYS[d.weekday()]


# ===== פעילות לפי תפקיד =====

async def _activity_counts_by_role(
    db: AsyncSession, window_start: datetime, now_utc: datetime
) -> dict[str, int]:
    """
    סופר activities בחלון, מפולח לפי תפקיד המבצע (performer.role) וסוג.
    activities בלי performer (performed_by=NULL → role לא ידוע) אינם
    משויכים לנועה/לעוזרת ולכן לא נספרים בשני הדליים האלה.

    מחזיר dict עם: noa_calls / assistant_calls / noa_outbound / assistant_outbound.
    """
    tracked = (ActivityType.CALL_COMPLETED.value, *_OUTBOUND_TYPES)
    stmt = (
        select(User.role, Activity.type, func.count())
        .select_from(Activity)
        .join(User, Activity.performed_by == User.id)
        .where(
            Activity.created_at >= window_start,
            Activity.created_at < now_utc,
            Activity.type.in_(tracked),
        )
        .group_by(User.role, Activity.type)
    )
    counts = {
        "noa_calls": 0,
        "assistant_calls": 0,
        "noa_outbound": 0,
        "assistant_outbound": 0,
    }
    for role, atype, count in (await db.execute(stmt)).all():
        if role == UserRole.OWNER.value:
            prefix = "noa"
        elif role == UserRole.ASSISTANT.value:
            prefix = "assistant"
        else:
            continue
        if atype == ActivityType.CALL_COMPLETED.value:
            counts[f"{prefix}_calls"] += count
        else:  # אחד מ-_OUTBOUND_TYPES
            counts[f"{prefix}_outbound"] += count
    return counts


async def _tasks_completed_by_role(
    db: AsyncSession, window_start: datetime, now_utc: datetime
) -> dict[str, int]:
    """
    סופר משימות שהושלמו בחלון, מפולח לפי תפקיד ה-assignee. ל-Task אין
    performed_by — מי שטיפל מיוצג ע"י assigned_to (כלל 12: assigned_to=owner).
    משימות בלי assignee לא נספרות בדליים.
    """
    stmt = (
        select(User.role, func.count())
        .select_from(Task)
        .join(User, Task.assigned_to == User.id)
        .where(
            Task.status == TaskStatus.DONE.value,
            Task.completed_at >= window_start,
            Task.completed_at < now_utc,
        )
        .group_by(User.role)
    )
    counts = {"noa_tasks": 0, "assistant_tasks": 0}
    for role, count in (await db.execute(stmt)).all():
        if role == UserRole.OWNER.value:
            counts["noa_tasks"] = count
        elif role == UserRole.ASSISTANT.value:
            counts["assistant_tasks"] = count
    return counts


# ===== תנועת לידים =====

def _format_breakdown(rows: list[tuple[str | None, int]], label_map: dict[str, str],
                      *, prefix: str = "") -> str:
    """
    בונה מחרוזת פילוח מבושלת: "2 מאינסטגרם, 1 מפייסבוק" (מסודר יורד לפי כמות).
    ערכים לא ממופים מוצגים כ-"אחר". ריק → "-".
    prefix מאפשר תחילית כמו "מ" (מקור) או "" (קטגוריה).
    """
    parts = []
    for value, count in rows:
        if not count:
            continue
        label = label_map.get(value or "", "אחר")
        parts.append(f"{count} {prefix}{label}")
    return ", ".join(parts) if parts else "-"


async def _lead_movement(
    db: AsyncSession, window_start: datetime, now_utc: datetime
) -> dict:
    """תנועת לידים בחלון: חדשים + פילוחים, WON/LOST, פעולות נכנסות."""
    in_window = (Lead.created_at >= window_start, Lead.created_at < now_utc)

    new_leads_count = (
        await db.execute(select(func.count()).select_from(Lead).where(*in_window))
    ).scalar_one()

    # פילוח לפי מקור (source_channel) — תחילית "מ".
    source_rows = (
        await db.execute(
            select(Lead.source_channel, func.count())
            .where(*in_window)
            .group_by(Lead.source_channel)
            .order_by(func.count().desc())
        )
    ).all()

    # פילוח לפי שירות ברמת service_subtype (שיקום קול, ליווי הפקה...) — אושר
    # מול הדוגמאות ב-§5.4/§5.8 שמציגות granularity ברמת subtype. התווית במסמך
    # ובפרומפט עודכנה ל"פילוח לפי שירות (subtype)" בהתאם (תיקון #1).
    category_rows = (
        await db.execute(
            select(Lead.service_subtype, func.count())
            .where(*in_window)
            .group_by(Lead.service_subtype)
            .order_by(func.count().desc())
        )
    ).all()

    closed_in_window = (Lead.closed_at >= window_start, Lead.closed_at < now_utc)
    won_count = (
        await db.execute(
            select(func.count()).select_from(Lead).where(
                Lead.status == LeadStatus.WON.value, *closed_in_window
            )
        )
    ).scalar_one()
    lost_count = (
        await db.execute(
            select(func.count()).select_from(Lead).where(
                Lead.status == LeadStatus.LOST.value, *closed_in_window
            )
        )
    ).scalar_one()

    # פעולות נכנסות מלקוחות. הערה: ל"החזרי טלפון" אין ActivityType ייעודי
    # (CALL_NO_ANSWER הוא שיחה *יוצאת* ללא מענה), לכן נספרות רק הודעות
    # נכנסות שתועדו (INBOUND_MESSAGE_LOGGED) — אושר (תיקון #2).
    inbound_actions_count = (
        await db.execute(
            select(func.count()).select_from(Activity).where(
                Activity.created_at >= window_start,
                Activity.created_at < now_utc,
                Activity.type == ActivityType.INBOUND_MESSAGE_LOGGED.value,
            )
        )
    ).scalar_one()

    return {
        "new_leads_count": new_leads_count,
        "new_leads_by_source_text": _format_breakdown(
            source_rows, SOURCE_CHANNEL_HE, prefix="מ"
        ),
        "new_leads_by_category_text": _format_breakdown(
            category_rows, SERVICE_SUBTYPE_HE
        ),
        "won_count": won_count,
        "lost_count": lost_count,
        "inbound_actions_count": inbound_actions_count,
    }


# ===== מצב פתוחים (snapshot ל-as_of) =====

# ה-helpers מתחתינו הם **המקור היחיד** להגדרת "פתוח / תקוע / הצעה תקועה
# ב-as_of". כל ספירה (`_open_state`) או רשימה (`_collect_attention_items`)
# חייבת לקרוא אליהם — אסור לכתוב logic מקבילה. אי-עקביות בין count
# לrשימה באותו סיכום נראית למשתמש כסתירה ("המספר אומר 5, ראיתי 3").
#
# כל ה-predicates נשענים על שדות זמן write-once (Lead: created_at,
# closed_at, status_changed_at; Task: created_at, completed_at) במקום
# על שדות mutable (status נוכחי, due_at — snooze דורס אותו). מגבלות
# מתועדות בדוקסטרינג של כל helper.


def _lead_open_at_predicate(as_of: datetime):
    """Lead-level WHERE: הליד היה קיים ולא סגור ב-`as_of`."""
    return and_(
        Lead.created_at <= as_of,
        or_(Lead.closed_at.is_(None), Lead.closed_at > as_of),
    )


def _task_active_at_predicate(as_of: datetime):
    """Task-level WHERE: ה-task היה אקטיבי (לא DONE, לא CANCELED) ב-`as_of`.

    DONE: `completed_at` מסומן כש-status עובר ל-DONE — write-once de facto.
    CANCELED: close_lead (`leads.py:340`) ו-chip apply
    (`quick_action_chips.py:303`) מציבים canceled **בלי** `completed_at` →
    שדה זמן ייעודי לא קיים, ולכן best-effort: מחריגים tasks ש-status נוכחי
    הוא CANCELED. tradeoff: task שהיה אקטיבי ב-as_of ובוטל בפער as_of→now
    יוחרג בטעות. הפער ב-weekly הוא 9h ליל שבת — ביטולים שם נדירים.
    """
    return and_(
        Task.created_at <= as_of,
        Task.status != TaskStatus.CANCELED.value,
        or_(Task.completed_at.is_(None), Task.completed_at > as_of),
    )


def _task_stuck_at_predicate(as_of: datetime):
    """Task-level WHERE: surfaceable task אקטיבי ב-`as_of` שנוצר 7+ ימים
    לפני `as_of`.

    `created_at` (לא `due_at`) — `due_at` נדרס ע"י snooze (`tasks.py:242`),
    אז due_at הנוכחי לא מייצג את due_at ב-`as_of`. הפרוקסי החדש: "task
    במערכת 7+ ימים בלי טיפול" במקום "due_at עבר 7+ ימים". לרוב ה-types
    כמעט זהה (FIRST_RESPONSE due_at = created_at+24h).
    """
    return and_(
        _task_active_at_predicate(as_of),
        Task.created_at <= as_of - timedelta(days=_STUCK_DAYS),
        surfaceable_task_condition(),
    )


def _lead_was_proposal_sent_at_predicate(as_of: datetime):
    """Lead-level WHERE: הליד היה ב-status=PROPOSAL_SENT ב-`as_of` (best-effort).

    אין status-history → 2 branches:
    1. **definite:** currently PROPOSAL_SENT AND `status_changed_at<=as_of`
       (אין שינוי מאז `as_of`).
    2. **inferred:** `status_changed_at>as_of` (transition אחרי `as_of`)
       AND `proposal_sent_at<=as_of` (היה כבר PROPOSAL_SENT לפני).
       מגבלה: לא מבחין בתרחיש של PROPOSAL_SENT→other→other שכולן לפני
       `as_of` — נדיר, אין דרך לדעת בלי history מלא.
    """
    return or_(
        and_(
            Lead.status == LeadStatus.PROPOSAL_SENT.value,
            or_(
                Lead.status_changed_at.is_(None),
                Lead.status_changed_at <= as_of,
            ),
        ),
        and_(
            Lead.status_changed_at > as_of,
            Lead.proposal_sent_at.is_not(None),
            Lead.proposal_sent_at <= as_of,
        ),
    )


async def _open_state(db: AsyncSession, as_of: datetime) -> dict:
    """ספירות מצב נכון לרגע `as_of` (לא תלוי חלון).

    `as_of` הוא ה-anchor של ה-snapshot: ב-daily נקרא עם `now_utc`, ב-weekly
    עם `week_end` (סוף שבת / תחילת ראשון 00:00 ישראל). כך פעילות בפער
    שבין סוף-השבוע לרגע ה-cron (ראשון בבוקר) לא משויכת בטעות לסיכום
    השבועי.

    כל ספירה משתמשת ב-predicates המשותפים (`_lead_open_at_predicate` וכו')
    שמוגדרים מעלה. זה מבטיח עקביות מול הרשימות ב-`_collect_attention_items`.
    """
    sent_at = func.coalesce(Lead.proposal_sent_at, Lead.last_outbound_at)
    stale_threshold = as_of - timedelta(days=_STALE_PROPOSAL_DAYS)

    open_leads_total = (
        await db.execute(
            select(func.count())
            .select_from(Lead)
            .where(_lead_open_at_predicate(as_of))
        )
    ).scalar_one()

    # ליד תקוע ב-`as_of`: היה פתוח אז + EXISTS task stuck ב-`as_of`.
    stuck_task_exists = (
        select(Task.id)
        .where(
            Task.lead_id == Lead.id,
            _task_stuck_at_predicate(as_of),
        )
        .correlate(Lead)
        .exists()
    )
    stuck_leads_count = (
        await db.execute(
            select(func.count())
            .select_from(Lead)
            .where(
                _lead_open_at_predicate(as_of),
                stuck_task_exists,
            )
        )
    ).scalar_one()

    # הצעה תקועה ב-`as_of`: ליד שהיה פתוח אז + היה ב-PROPOSAL_SENT ב-`as_of`
    # (כולל לידים שעברו סטטוס אחרי `as_of` — Finding 1 של cursor bugbot)
    # + sent_at <= as_of - 4d.
    stale_proposals_count = (
        await db.execute(
            select(func.count())
            .select_from(Lead)
            .where(
                _lead_open_at_predicate(as_of),
                _lead_was_proposal_sent_at_predicate(as_of),
                sent_at.is_not(None),
                sent_at <= stale_threshold,
            )
        )
    ).scalar_one()

    # משימות overdue ב-`as_of`: היו אקטיביות באותו רגע ושעברו את ה-due_at אז.
    # `due_at <= as_of` משתמש ב-due_at הנוכחי (mutable ע"י snooze, ראה הערה
    # ב-`_task_stuck_at_predicate`) — מובן רק כש-`as_of ≈ now` (קריאת daily).
    # ב-`_open_state(db, week_end)` הערך מחושב אך *לא מוצג* ב-weekly prompt
    # (`prompts/weekly_summary.py` מציג 3 שדות, ללא overdue_tasks_count) →
    # drift שם לא נראה למשתמש.
    overdue_tasks_count = (
        await db.execute(
            select(func.count())
            .select_from(Task)
            .where(
                _task_active_at_predicate(as_of),
                Task.due_at <= as_of,
                surfaceable_task_condition(),
            )
        )
    ).scalar_one()

    return {
        "open_leads_total": open_leads_total,
        "stuck_leads_count": stuck_leads_count,
        "stale_proposals_count": stale_proposals_count,
        "overdue_tasks_count": overdue_tasks_count,
    }


async def _dormant_with_recommendation_count(db: AsyncSession) -> int:
    """מספר לידים פתוחים עם משימת DORMANT_SUGGESTION פעילה (D.1, §3.6)."""
    has_suggestion = (
        select(Task.id)
        .where(
            Task.lead_id == Lead.id,
            Task.type == TaskType.DORMANT_SUGGESTION.value,
            Task.status.in_([TaskStatus.OPEN.value, TaskStatus.SNOOZED.value]),
        )
        .correlate(Lead)
        .exists()
    )
    return (
        await db.execute(
            select(func.count()).select_from(Lead).where(
                Lead.status.notin_([s.value for s in CLOSED_LEAD_STATUSES]),
                has_suggestion,
            )
        )
    ).scalar_one()


# ===== עזרי תצוגת ליד ל-blocks =====

def _lead_display_name(lead: Lead) -> str:
    """
    שם להצגה ב-block, לפי כללי השמות (§4.1): שם פרטי + ארגון אם שניהם,
    ארגון בלבד אם אין שם, "ללא" אם אין כלום.
    """
    name = (lead.full_name or "").strip()
    org = (lead.organization_name or "").strip()
    if name and org:
        return f"{name} מ{org}"
    if name:
        return name
    if org:
        return org
    return "ללא"


def _role_label(role: str | None) -> str:
    """תווית 'בוצע ע"י' — נועה / העוזרת / '-' אם לא ידוע."""
    if role == UserRole.OWNER.value:
        return "נועה"
    if role == UserRole.ASSISTANT.value:
        return "העוזרת"
    return "-"


def _subtype_label(lead: Lead) -> str:
    return SERVICE_SUBTYPE_HE.get(lead.service_subtype or "", "ללא קטגוריה")


# ===== blocks =====

async def compute_highlighted_leads_block(
    db: AsyncSession, window_start: datetime, now_utc: datetime
) -> str:
    """
    0-3 לידים בולטים (§6.3.1), בסדר עדיפות הקריטריונים:
    1. שבירת שתיקה — לקוח ענה אחרי 7+ ימי שתיקה.
    2. שינוי סטטוס משמעותי — נסגר WON / עבר ל-BOOKED.
    3. ליד ארגוני חדש.
    4. ליד מהמלצה.
    מחזיר מחרוזת בפורמט §4.1, או "(ריק)" אם אין.

    הערה: כל הקריטריונים נגזרים מ-signals קיימים (שדות Lead + activities
    בחלון). ראה הערות פר-קריטריון.
    """
    lines: list[str] = []
    seen: set = set()

    def _add(lead: Lead, event: str, role: str | None) -> bool:
        """מוסיף שורה אם הליד טרם נכלל. מחזיר True אם הגענו לתקרה."""
        if lead.id in seen:
            return len(lines) >= _BLOCK_LIMIT
        seen.add(lead.id)
        org = (lead.organization_name or "").strip()
        org_part = f"ארגון: {org} | " if org else ""
        name = (lead.full_name or "").strip() or "ללא"
        lines.append(
            f"- שם: {name} | {org_part}קטגוריה: {_subtype_label(lead)} | "
            f"אירוע: {event} | בוצע ע\"י: {_role_label(role)}"
        )
        return len(lines) >= _BLOCK_LIMIT

    # (1) שבירת שתיקה: לקוח שלח הודעה נכנסת בחלון, וה-outbound *שקדם לה*
    # היה לפני 7+ ימים. מחושב מלוג הפעילות (לא מ-last_outbound_at הדנורמלי):
    # אם נועה תענה ללקוח *אחרי* ההודעה הנכנסת באותו יום, last_outbound_at
    # יקפוץ קדימה — אבל כאן אנחנו מסתכלים רק על outbound עם created_at קטן
    # מזמן ה-inbound, כך שהזיהוי יציב גם אחרי מענה. פעולת לקוח — בלי "בוצע ע"י".
    prev_out = aliased(Activity)
    prev_outbound_at = (
        select(func.max(prev_out.created_at))
        .where(
            prev_out.lead_id == Activity.lead_id,
            # כל מגע יוצא (מסר/שיחה) מאפס את שעון השתיקה — לא רק מסרים.
            prev_out.type.in_(_OUTBOUND_CONTACT_TYPES),
            prev_out.created_at < Activity.created_at,
        )
        .correlate(Activity)
        .scalar_subquery()
    )
    silence_rows = (
        await db.execute(
            select(Lead, Activity.created_at, prev_outbound_at.label("prev_out"))
            .join(Lead, Activity.lead_id == Lead.id)
            .where(
                Activity.type == ActivityType.INBOUND_MESSAGE_LOGGED.value,
                Activity.created_at >= window_start,
                Activity.created_at < now_utc,
            )
            .order_by(Activity.created_at.desc())
        )
    ).all()
    for lead, inbound_at, prev_outbound in silence_rows:
        if prev_outbound is None:
            continue  # אין outbound קודם — לא "שתיקה שנשברה", פשוט ליד צעיר.
        gap = inbound_at - prev_outbound
        # סף timedelta מפורש — אותו ניסוח כמו stuck/stale (כלל 10), בלי
        # להישען על truncation של .days. ה-.days משמש רק לערך התצוגה
        # (מעוגל כלפי מטה — שמרני, לא מנפח את "ימי השתיקה").
        if gap < timedelta(days=_SILENCE_BREAK_DAYS):
            continue
        if _add(lead, f"ענה אחרי {gap.days} ימי שתיקה", None):
            return "\n".join(lines)

    # (2) שינוי סטטוס משמעותי בחלון: נסגר WON (LEAD_WON), או עבר ל-BOOKED.
    # מעבר ל-BOOKED נרשם כ-MEETING_APPROVED (booking.py: אישור הזמנה →
    # status=BOOKED), *לא* כ-STATUS_CHANGED — זה ה-signal הקנוני למעבר
    # BOOKING_PENDING→BOOKED. (ההבחנה כאן היא על *שינוי הסטטוס*, לא על
    # השאלה אם פגישה פיזית התקיימה — אותה מטריקה הוסרה במכוון.)
    status_events = (
        await db.execute(
            select(Activity, Lead, User.role)
            .join(Lead, Activity.lead_id == Lead.id)
            .join(User, Activity.performed_by == User.id, isouter=True)
            .where(
                Activity.created_at >= window_start,
                Activity.created_at < now_utc,
                Activity.type.in_(
                    [
                        ActivityType.LEAD_WON.value,
                        ActivityType.MEETING_APPROVED.value,
                    ]
                ),
            )
            .order_by(Activity.created_at.desc())
        )
    ).all()
    for activity, lead, role in status_events:
        event = (
            "נסגר כ-WON"
            if activity.type == ActivityType.LEAD_WON.value
            else "סטטוס עבר ל-BOOKED"
        )
        if _add(lead, event, role):
            return "\n".join(lines)

    # (3) ליד ארגוני חדש: נוצר בחלון עם organization_name.
    org_rows = (
        await db.execute(
            select(Lead).where(
                Lead.created_at >= window_start,
                Lead.created_at < now_utc,
                Lead.organization_name.is_not(None),
                func.length(func.trim(Lead.organization_name)) > 0,
            )
        )
    ).scalars().all()
    for lead in org_rows:
        if _add(lead, "ליד ארגוני חדש", None):
            return "\n".join(lines)

    # (4) ליד מהמלצה: נוצר בחלון עם source_channel=referral.
    referral_rows = (
        await db.execute(
            select(Lead).where(
                Lead.created_at >= window_start,
                Lead.created_at < now_utc,
                Lead.source_channel == SourceChannel.REFERRAL.value,
            )
        )
    ).scalars().all()
    for lead in referral_rows:
        if _add(lead, "ליד חדש מהמלצה", None):
            return "\n".join(lines)

    return "\n".join(lines) if lines else "(ריק)"


async def _collect_attention_items(
    db: AsyncSession, now_utc: datetime
) -> tuple[list[str], set]:
    """
    אוסף 0-3 פריטים שדורשים תשומת לב (§6.3.2), בסדר עדיפות:
    1. הצעה ללא מענה מעל 4 ימים.
    2. ליד תקוע מעל 7 ימים.
    3. משימה פעילה שעברה את היעד.

    dedup גלובלי לפי lead: ליד שגם הצעתו תקועה וגם יש לו task תקוע יופיע
    *פעם אחת* בלבד, לפי הקריטריון בעל העדיפות הגבוהה ביותר (סדר הסעיפים).

    מחזיר (lines, seen_ids) — ה-seen מאפשר ל-tomorrow_focus להוסיף לידים
    בלי לכפול את מי שכבר כאן.
    """
    lines: list[str] = []
    seen: set = set()

    def _add(lead: Lead, text: str) -> bool:
        """מוסיף שורה אם הליד טרם נכלל. מחזיר True כשהגענו לתקרה."""
        if lead.id in seen:
            return len(lines) >= _BLOCK_LIMIT
        seen.add(lead.id)
        lines.append(text)
        return len(lines) >= _BLOCK_LIMIT

    # כל הקריטריונים משתמשים ב-predicates המשותפים עם `_open_state` —
    # כך המספר ב-`stuck_leads_count` והרשימה כאן לעולם לא יסתרו זה את זה
    # (Finding 2 של cursor bugbot על da8b9c8).

    # (1) הצעות תקועות — הוותיקה ביותר ראשונה. אותו predicate כמו
    # `stale_proposals_count` (כולל ה-OR-branch של "transition אחרי as_of").
    sent_at = func.coalesce(Lead.proposal_sent_at, Lead.last_outbound_at)
    stale_threshold = now_utc - timedelta(days=_STALE_PROPOSAL_DAYS)
    stale = (
        await db.execute(
            select(Lead, sent_at.label("sent"))
            .where(
                _lead_open_at_predicate(now_utc),
                _lead_was_proposal_sent_at_predicate(now_utc),
                sent_at.is_not(None),
                sent_at <= stale_threshold,
            )
            .order_by(sent_at.asc())
            .limit(_BLOCK_LIMIT)
        )
    ).all()
    for lead, sent in stale:
        days = max(0, (now_utc - sent).days)
        if _add(
            lead,
            f"- סוג: הצעה ללא מענה | ליד: {_lead_display_name(lead)} | "
            f"ימים מאז שליחה: {days}",
        ):
            return lines, seen

    # (2) לידים תקועים — הוותיק ביותר (לפי status_changed_at) ראשון.
    # "ימים בסטטוס נוכחי" מחושב מ-status_changed_at האמיתי (DB trigger,
    # migration 0025), fallback ל-created_at אם NULL (לידים לפני ה-backfill).
    # אותו predicate כמו `stuck_leads_count` (`created_at` במקום `due_at`,
    # החרגת CANCELED).
    stuck = (
        await db.execute(
            select(Lead)
            .join(Task, Task.lead_id == Lead.id)
            .where(
                _lead_open_at_predicate(now_utc),
                _task_stuck_at_predicate(now_utc),
            )
            .group_by(Lead.id)
            .order_by(Lead.status_changed_at.asc())
            .limit(_BLOCK_LIMIT)
        )
    ).scalars().all()
    for lead in stuck:
        anchor = lead.status_changed_at or lead.created_at
        days = max(0, (now_utc - anchor).days)
        if _add(
            lead,
            f"- סוג: ליד תקוע | ליד: {_lead_display_name(lead)} | "
            f"ימים בסטטוס נוכחי: {days}",
        ):
            return lines, seen

    # (3) משימות פעילות שעברו את היעד — הוותיקה ביותר ראשונה. headroom של
    # פי-3 בשליפה כי כמה tasks יכולים להיות לאותו ליד (dedup מסנן אותם).
    # אותו predicate כמו `overdue_tasks_count`.
    overdue = (
        await db.execute(
            select(Task, Lead)
            .join(Lead, Task.lead_id == Lead.id)
            .where(
                _task_active_at_predicate(now_utc),
                Task.due_at <= now_utc,
                surfaceable_task_condition(),
            )
            .order_by(Task.due_at.asc())
            .limit(_BLOCK_LIMIT * 3)
        )
    ).all()
    for task, lead in overdue:
        desc = (task.task_metadata or {}).get("description") if task.task_metadata else None
        desc = desc or _task_type_label(task.type)
        if _add(
            lead,
            f"- סוג: משימה שלא בוצעה | ליד: {_lead_display_name(lead)} | "
            f"תיאור: {desc}",
        ):
            return lines, seen

    return lines, seen


async def compute_attention_items_block(db: AsyncSession, now_utc: datetime) -> str:
    """0-3 פריטי תשומת-לב (§6.3.2) כמחרוזת §4.1, או '(ריק)'. ראה _collect_attention_items."""
    lines, _seen = await _collect_attention_items(db, now_utc)
    return "\n".join(lines) if lines else "(ריק)"


def _task_type_label(task_type: str) -> str:
    """תיאור עברי קצר לסוג משימה — fallback כשאין description ב-metadata."""
    labels = {
        TaskType.FIRST_RESPONSE.value: "מענה ראשוני לליד חדש",
        TaskType.WARM_FOLLOWUP.value: "פולואפ ללקוח חם",
        TaskType.PROPOSAL_FOLLOWUP.value: "פולואפ על הצעת מחיר",
        TaskType.DORMANT_CHECK.value: "בדיקת ליד רדום",
        TaskType.LECTURE_INQUIRY.value: "מענה לפניית הרצאה",
        TaskType.FOLLOWUP.value: "פולואפ",
        TaskType.RETRY_CALL.value: "ניסיון שיחה חוזר",
        TaskType.SEND_PROPOSAL.value: "שליחת הצעת מחיר",
        TaskType.POST_MEETING_UPDATE.value: "עדכון אחרי פגישה",
        TaskType.AFTER_HOURS_REPLY.value: "החזרה אחרי שעות עבודה",
    }
    return labels.get(task_type, "משימה פתוחה")


async def compute_tomorrow_focus_block(
    db: AsyncSession,
    now_utc: datetime,
    attention_lines: list[str],
    attention_seen: set,
) -> str | None:
    """
    פוקוס למחר (§6.3.3, מזוקק) — מחזיר block או None ("מחר" מושמט):
    - לידים שדורשים פוקוס: סטטוס פתוח, הכדור אצלנו (waiting_on ∈
      NOAH/ASSISTANT/ASSISTANT_PENDING_NOAH), VIP או ארגוני, ושלא כבר
      מופיעים ב-attention (dedup לפי lead.id).
    - אם יש כאלה *וגם* יש פריטי attention — שורת מצביע קצרה לכמותם, **בלי**
      לשכפל את שורות ה-attention עצמן (הן כבר בסקציית "דורש תשומת לב").
    - אם אין לידי VIP/ארגון → None, גם אם יש פריטי attention (הם מוצגים
      בסקציה שלהם; "מחר" נשאר אופציונלי, תואם few-shot דוגמה 2).
    """
    lines: list[str] = []
    rows = (
        await db.execute(
            select(Lead)
            .where(
                Lead.status.notin_([s.value for s in CLOSED_LEAD_STATUSES]),
                Lead.waiting_on.in_(
                    [
                        WaitingOn.NOAH.value,
                        WaitingOn.ASSISTANT.value,
                        WaitingOn.ASSISTANT_PENDING_NOAH.value,
                    ]
                ),
                or_(
                    Lead.priority_level == PriorityLevel.VIP.value,
                    and_(
                        Lead.organization_name.is_not(None),
                        func.length(func.trim(Lead.organization_name)) > 0,
                    ),
                ),
            )
            .order_by(Lead.status_changed_at.asc())
            .limit(_BLOCK_LIMIT * 3)
        )
    ).scalars().all()

    for lead in rows:
        if lead.id in attention_seen:
            continue  # כבר מופיע ב-attention — לא לכפול.
        kind = "VIP" if lead.priority_level == PriorityLevel.VIP.value else "ארגוני"
        lines.append(f"- ליד שדורש פוקוס: {_lead_display_name(lead)} ({kind})")
        if len(lines) >= _BLOCK_LIMIT:
            break

    if not lines:
        return None  # אין מה להבליט ספציפית למחר → הסקציה מושמטת.

    # מצביע קצר לעומס ה-attention — בלי לשכפל את הפריטים (הם בסקציה נפרדת).
    n = len(attention_lines)
    if n == 1:
        lines.append("- בנוסף, פריט אחד דורש מעקב (ראה 'דורש תשומת לב')")
    elif n > 1:
        lines.append(f"- בנוסף, {n} פריטים דורשים מעקב (ראה 'דורש תשומת לב')")

    return "\n".join(lines)


# ===== assembly =====

async def build_daily_user_prompt(
    db: AsyncSession, now_utc: datetime | None = None
) -> str:
    """
    אוסף את כל הקלט המבושל לסיכום היומי ומרכיב אותו לתוך USER_TEMPLATE.
    מחזיר את ה-user prompt המוכן ל-generate_daily_summary_text.
    """
    now_utc = now_utc or datetime.now(timezone.utc)
    window_start, _ = _window_bounds(now_utc)
    # תאריך הסיכום = יום-הלוח בישראל (כמו jobs/daily_summary.py), לא UTC.
    today = to_israel_tz(now_utc).date()

    activity = await _activity_counts_by_role(db, window_start, now_utc)
    tasks = await _tasks_completed_by_role(db, window_start, now_utc)
    movement = await _lead_movement(db, window_start, now_utc)
    open_state = await _open_state(db, now_utc)
    highlighted = await compute_highlighted_leads_block(db, window_start, now_utc)
    # אוספים את פריטי ה-attention פעם אחת — משמשים גם לבלוק "דורש תשומת לב"
    # וגם כבסיס ל-tomorrow_focus (עם dedup לפי seen-ids).
    attention_lines, attention_seen = await _collect_attention_items(db, now_utc)
    attention = "\n".join(attention_lines) if attention_lines else "(ריק)"
    dormant_count = await _dormant_with_recommendation_count(db)
    tomorrow = await compute_tomorrow_focus_block(
        db, now_utc, attention_lines, attention_seen
    )

    return USER_TEMPLATE.format(
        date=today.isoformat(),
        day_of_week=_hebrew_weekday(today),
        days_in_system=compute_days_in_system(today),
        noa_calls_count=activity["noa_calls"],
        noa_outbound_messages_count=activity["noa_outbound"],
        noa_tasks_completed=tasks["noa_tasks"],
        assistant_calls_count=activity["assistant_calls"],
        assistant_outbound_messages_count=activity["assistant_outbound"],
        assistant_tasks_completed=tasks["assistant_tasks"],
        new_leads_count=movement["new_leads_count"],
        new_leads_by_source_text=movement["new_leads_by_source_text"],
        new_leads_by_category_text=movement["new_leads_by_category_text"],
        won_count=movement["won_count"],
        lost_count=movement["lost_count"],
        inbound_actions_count=movement["inbound_actions_count"],
        open_leads_total=open_state["open_leads_total"],
        stuck_leads_count=open_state["stuck_leads_count"],
        stale_proposals_count=open_state["stale_proposals_count"],
        overdue_tasks_count=open_state["overdue_tasks_count"],
        highlighted_leads_block=highlighted,
        attention_items_block=attention,
        dormant_with_recommendation_count=dormant_count,
        tomorrow_focus_suggestion_or_null=(
            tomorrow if tomorrow is not None else "null"
        ),
    )


# ============================================================================
# ===== שכבת החישוב לסיכום השבועי — C.2 (§4.2 + §5.5–§5.8) =====
# ============================================================================
#
# עיקרון זהה ליומי: "AI מפרש, לא מחשב". כל מספר/השוואה/תובנה מחושב כאן
# מ-DB ומוזן ל-WEEKLY_USER_TEMPLATE כמחרוזת מבושלת. ה-AI רק מנסח.
#
# מודל החלון השבועי (§4.2): החלון הוא **השבוע הקודם המלא** (ראשון 00:00 →
# ראשון הבא 00:00, סוף לא-כולל), בזמן ישראל. הריצה היא בבוקר יום ראשון
# ומסכמת את השבוע שהסתיים אתמול (שבת). מטריקות מצב (פתוחים/תקועים/הצעות
# תקועות) הן snapshot ל-now (כמו ביומי).

# חלון 30 יום לתובנות אסטרטגיות מבוססות-היסטוריה (§4.2 precomputed_insights).
_INSIGHTS_WINDOW_DAYS = 30

# סף שבועות-במערכת שמעליו מציגים נתוני השוואה (§4.2: "פחות מ-4 שבועות → אין
# מספיק היסטוריה"). מתחת לסף — trends_block = "NO_COMPARISON".
_COMPARISON_MIN_WEEKS = 4

# מספר התובנות המקסימלי בכל סוג (top-N לפי denominator) — תואם _BLOCK_LIMIT.
_INSIGHTS_TOP_N = _BLOCK_LIMIT


# ===== גבולות שבוע (DST-safe, ממראה את dashboard._current_week_bounds) =====

def _last_week_bounds(now_utc: datetime) -> tuple[datetime, datetime]:
    """
    גבולות (start, end) של **השבוע הקודם המלא** בזמן ישראל — ראשון 00:00 עד
    ראשון הבא 00:00 (end לא-כולל). מורץ בבוקר יום ראשון: "שבוע שעבר" = השבוע
    שמתחיל ראשון-שעבר ומסתיים ראשון-הנוכחי.

    שני ה-bounds נבנים כ-midnight מקומי **באופן עצמאי** (לא start+7days) כדי
    להימנע מ-DST drift בשבוע של מעבר שעון (כמו ב-dashboard._current_week_bounds).
    """
    local = to_israel_tz(now_utc)
    today = local.date()
    # weekday: שני=0 .. שבת=5 .. ראשון=6. מספר ימים אחורה ליום ראשון הנוכחי:
    days_since_sunday = (today.weekday() + 1) % 7
    current_sunday = today - timedelta(days=days_since_sunday)
    last_sunday = current_sunday - timedelta(days=7)
    start_local = datetime.combine(last_sunday, time(0, 0, tzinfo=ISRAEL_TZ))
    end_local = datetime.combine(current_sunday, time(0, 0, tzinfo=ISRAEL_TZ))
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def _prev_week_bounds(week_start_utc: datetime) -> tuple[datetime, datetime]:
    """
    גבולות השבוע שקדם מיד ל-week_start נתון (לצורך השוואת מגמות) — אותו
    מבנה midnight-עצמאי כדי להימנע מ-DST drift.
    """
    start_local = to_israel_tz(week_start_utc).date()
    prev_sunday = start_local - timedelta(days=7)
    start = datetime.combine(prev_sunday, time(0, 0, tzinfo=ISRAEL_TZ))
    end = datetime.combine(start_local, time(0, 0, tzinfo=ISRAEL_TZ))
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


# ===== מטריקות בסיסיות שבועיות =====

def compute_weeks_in_system(week_start_date: date) -> int:
    """
    מספר השבוע במערכת לשבוע שמתחיל ב-week_start_date.
    חלוקה ב-7 + 1 כך שהשבוע הראשון = 1 (ולא 0). רצפה 1 (תצורה שגויה).
    """
    start = get_settings().system_start_date
    return max(1, (week_start_date - start).days // 7 + 1)


def has_comparison_data(weeks_in_system: int) -> bool:
    """האם יש מספיק היסטוריה (4+ שבועות) להצגת נתוני השוואה (§4.2)."""
    return weeks_in_system >= _COMPARISON_MIN_WEEKS


async def _newly_dormant_count(
    db: AsyncSession, window_start: datetime, window_end: datetime
) -> int:
    """
    "לידים רדומים שזוהו השבוע" — קירוב. אין שדה timestamp ייעודי ל"מתי הליד
    סומן רדום", לכן סופרים משימות DORMANT_SUGGESTION שנוצרו בחלון (כל זיהוי
    רדום מייצר משימה כזו, D.1 §3.6). קירוב שמרני ושקוף — לא המצאה.
    """
    return (
        await db.execute(
            select(func.count()).select_from(Task).where(
                Task.type == TaskType.DORMANT_SUGGESTION.value,
                Task.created_at >= window_start,
                Task.created_at < window_end,
            )
        )
    ).scalar_one()


# ===== מגמות מול שבוע קודם (trends_block, §4.2) =====

def _trend_direction(curr, prev, *, lower_is_better: bool = False) -> str:
    """
    כיוון מגמה מילולי בין שני ערכים.
    - רגיל: עלייה (curr>prev) / ירידה (curr<prev) / יציב (שווה).
    - lower_is_better (זמן תגובה — נמוך עדיף): שיפור (curr<prev) /
      הרעה (curr>prev) / יציב (שווה). אומת מול §5.8: 4→2 שעות = שיפור,
      2→6 = הרעה.
    - אם אחד מהצדדים None (אין נתון) — "יציב" (הבחירה הכי פחות-מפתיעה,
      בלי להמציא כיוון).
    """
    if curr is None or prev is None:
        return "יציב"
    if curr == prev:
        return "יציב"
    if lower_is_better:
        return "שיפור" if curr < prev else "הרעה"
    return "עלייה" if curr > prev else "ירידה"


async def _avg_first_response_hours(
    db: AsyncSession, window_start: datetime, window_end: datetime
) -> int | None:
    """
    "זמן תגובה ראשון ממוצע" (שעות) — AVG(first_outbound_at - created_at) על
    לידים שנוצרו בחלון ושכבר קיבלו outbound ראשון. תנאי first_outbound_at >=
    created_at שומר מפני נתונים פגומים (outbound לפני יצירה). מעוגל לשלם
    הקרוב. None אם אין לידים מתאימים.
    """
    delta_seconds = func.extract(
        "epoch", Lead.first_outbound_at - Lead.created_at
    )
    avg_hours = (
        await db.execute(
            select(func.avg(delta_seconds / 3600.0)).where(
                Lead.created_at >= window_start,
                Lead.created_at < window_end,
                Lead.first_outbound_at.is_not(None),
                Lead.first_outbound_at >= Lead.created_at,
            )
        )
    ).scalar_one()
    return round(avg_hours) if avg_hours is not None else None


async def _top_source_by_new_leads(
    db: AsyncSession, window_start: datetime, window_end: datetime
) -> str | None:
    """תווית המקור (SOURCE_CHANNEL_HE) עם הכי הרבה לידים חדשים בחלון. None אם אין."""
    row = (
        await db.execute(
            select(Lead.source_channel, func.count().label("c"))
            .where(
                Lead.created_at >= window_start,
                Lead.created_at < window_end,
            )
            .group_by(Lead.source_channel)
            .order_by(func.count().desc())
            .limit(1)
        )
    ).first()
    if row is None or not row.c:
        return None
    return SOURCE_CHANNEL_HE.get(row[0] or "", "אחר")


async def compute_trends_block(
    db: AsyncSession,
    week_start: datetime,
    week_end: datetime,
    weeks_in_system: int,
    *,
    curr_new_leads: int,
    curr_won: int,
) -> str:
    """
    בונה את trends_block (§4.2): 4 שורות השוואה מול השבוע הקודם, או
    "NO_COMPARISON" אם פחות מ-4 שבועות במערכת. הפורמט verbatim מ-§4.2 +
    few-shot (כל שורה מתחילה ב-"- ").

    curr_new_leads / curr_won מתקבלים מבחוץ (כבר חושבו ב-_lead_movement של
    השבוע הנוכחי) כדי לא לשאול פעמיים.
    """
    if weeks_in_system < _COMPARISON_MIN_WEEKS:
        return "NO_COMPARISON"

    prev_start, prev_end = _prev_week_bounds(week_start)
    prev_movement = await _lead_movement(db, prev_start, prev_end)
    prev_new_leads = prev_movement["new_leads_count"]
    prev_won = prev_movement["won_count"]

    curr_hours = await _avg_first_response_hours(db, week_start, week_end)
    prev_hours = await _avg_first_response_hours(db, prev_start, prev_end)

    curr_src = await _top_source_by_new_leads(db, week_start, week_end)
    prev_src = await _top_source_by_new_leads(db, prev_start, prev_end)

    leads_dir = _trend_direction(curr_new_leads, prev_new_leads)
    won_dir = _trend_direction(curr_won, prev_won)
    # זמן תגובה — נמוך יותר עדיף (שיפור/הרעה).
    hours_dir = _trend_direction(curr_hours, prev_hours, lower_is_better=True)

    # ערכי תצוגה לזמן תגובה: אם אין נתון מציגים "אין נתון" (לא ממציאים 0).
    curr_hours_text = curr_hours if curr_hours is not None else "אין נתון"
    prev_hours_text = prev_hours if prev_hours is not None else "אין נתון"
    curr_src_text = curr_src if curr_src is not None else "-"
    prev_src_text = prev_src if prev_src is not None else "-"

    return "\n".join(
        [
            f"- לידים חדשים: {curr_new_leads} השבוע מול {prev_new_leads} "
            f"שבוע קודם. כיוון: {leads_dir}.",
            f"- סגירות WON: {curr_won} השבוע מול {prev_won} "
            f"שבוע קודם. כיוון: {won_dir}.",
            f"- זמן תגובה ראשון ממוצע: {curr_hours_text} שעות השבוע מול "
            f"{prev_hours_text} שעות שבוע קודם. כיוון: {hours_dir}.",
            f"- מקור מוביל השבוע: {curr_src_text}. שבוע קודם: {prev_src_text}.",
        ]
    )


# ===== תובנות אסטרטגיות שחושבו מראש (precomputed_insights_block, §4.2) =====
#
# החלטות מוצר מאושרות (סבב 2b):
# 1. conversion-rate + זמן-ממוצע-ל-WON מקובצים לפי service_category (לא subtype),
#    עם תוויות SERVICE_CATEGORY_HE. (פילוח הלידים-החדשים נשאר subtype.)
# 2. שורת stuck-ratio הושמטה — לא נמצאת בפורמט §4.2 ולא ב-few-shot.

async def _conversion_by_category_30d(
    db: AsyncSession, now_utc: datetime
) -> list[str]:
    """
    יחס המרה (WON / (WON+LOST)) לכל service_category, על לידים שנסגרו
    ב-30 הימים האחרונים. כולל קטגוריות עם מכנה >= 1, top-3 לפי גודל המכנה.
    פורמט verbatim: "conversion rate ב{תווית}: {אחוז}% ב-30 הימים האחרונים".
    """
    window_start = now_utc - timedelta(days=_INSIGHTS_WINDOW_DAYS)
    won_count = func.count(
        case((Lead.status == LeadStatus.WON.value, 1))
    )
    rows = (
        await db.execute(
            select(
                Lead.service_category,
                won_count.label("won"),
                func.count().label("denom"),
            )
            .where(
                Lead.closed_at >= window_start,
                Lead.closed_at < now_utc,
                Lead.status.in_(
                    [LeadStatus.WON.value, LeadStatus.LOST.value]
                ),
            )
            .group_by(Lead.service_category)
            .order_by(func.count().desc())
            .limit(_INSIGHTS_TOP_N)
        )
    ).all()
    lines: list[str] = []
    for category, won, denom in rows:
        if not denom:
            continue
        pct = round(won / denom * 100)
        label = SERVICE_CATEGORY_HE.get(category or "", "אחר")
        lines.append(
            f"- conversion rate ב{label}: {pct}% ב-30 הימים האחרונים"
        )
    return lines


async def _avg_days_to_won_by_category_30d(
    db: AsyncSession, now_utc: datetime
) -> str | None:
    """
    זמן ממוצע מליד ל-WON (ימים) עבור הקטגוריה עם הכי הרבה WON ב-30 הימים
    האחרונים. שורה אחת: "זמן ממוצע מליד ל-WON ב{תווית}: {ימים} ימים".
    None אם אין WON בחלון.
    """
    window_start = now_utc - timedelta(days=_INSIGHTS_WINDOW_DAYS)
    # קודם בוחרים את הקטגוריה עם הכי הרבה WON:
    top = (
        await db.execute(
            select(Lead.service_category, func.count().label("c"))
            .where(
                Lead.status == LeadStatus.WON.value,
                Lead.closed_at >= window_start,
                Lead.closed_at < now_utc,
            )
            .group_by(Lead.service_category)
            .order_by(func.count().desc())
            .limit(1)
        )
    ).first()
    if top is None or not top.c:
        return None
    category = top[0]
    # התאמת קטגוריה: None דורש IS NULL (השוואת == ל-NULL תמיד שקרית ב-SQL).
    category_match = (
        Lead.service_category.is_(None)
        if category is None
        else Lead.service_category == category
    )
    days_seconds = func.extract("epoch", Lead.closed_at - Lead.created_at)
    avg_days = (
        await db.execute(
            select(func.avg(days_seconds / 86400.0)).where(
                Lead.status == LeadStatus.WON.value,
                Lead.closed_at >= window_start,
                Lead.closed_at < now_utc,
                category_match,
            )
        )
    ).scalar_one()
    if avg_days is None:
        return None
    label = SERVICE_CATEGORY_HE.get(category or "", "אחר")
    return f"- זמן ממוצע מליד ל-WON ב{label}: {round(avg_days)} ימים"


async def _top_source_by_won_30d(db: AsyncSession, now_utc: datetime) -> str | None:
    """
    מקור (source_channel) עם הכי הרבה סגירות WON ב-30 הימים האחרונים.
    שורה אחת. None אם אין WON בחלון.
    """
    window_start = now_utc - timedelta(days=_INSIGHTS_WINDOW_DAYS)
    row = (
        await db.execute(
            select(Lead.source_channel, func.count().label("c"))
            .where(
                Lead.status == LeadStatus.WON.value,
                Lead.closed_at >= window_start,
                Lead.closed_at < now_utc,
            )
            .group_by(Lead.source_channel)
            .order_by(func.count().desc())
            .limit(1)
        )
    ).first()
    if row is None or not row.c:
        return None
    label = SOURCE_CHANNEL_HE.get(row[0] or "", "אחר")
    return f"- מקור עם הכי הרבה סגירות ב-30 הימים האחרונים: {label}"


async def compute_precomputed_insights_block(
    db: AsyncSession, now_utc: datetime
) -> str:
    """
    בונה את precomputed_insights_block (§4.2) — תובנות מבוססות 30 יום.
    סדר השורות: conversion-rate (עד 3), אז מקור-מוביל-WON, אז זמן-ממוצע-ל-WON.
    כל שורה נכללת רק אם יש לה נתון. אם הבלוק כולו ריק → "(ריק - לא מספיק נתונים)".
    """
    lines: list[str] = []
    lines.extend(await _conversion_by_category_30d(db, now_utc))

    top_source = await _top_source_by_won_30d(db, now_utc)
    if top_source:
        lines.append(top_source)

    avg_days = await _avg_days_to_won_by_category_30d(db, now_utc)
    if avg_days:
        lines.append(avg_days)

    return "\n".join(lines) if lines else "(ריק - לא מספיק נתונים)"


# ===== פוקוס מוצע לשבוע הבא (heuristic, §4.2) =====

def compute_next_week_focus_suggestion(
    db: AsyncSession, now_utc: datetime, open_state: dict
) -> str | None:
    """
    המלצת פוקוס מבוססת-נתון לשבוע הבא — היוריסטיקה אופציונלית (None אם אין
    בסיס). מבוססת על snapshot המצב (open_state), בלי המצאות. סדר עדיפות:
    (א) יש לידים תקועים → להמליץ לעבור עליהם ולקבל החלטה.
    (ב) אחרת יש הצעות תקועות → להמליץ לעשות פולואפ להצעות ישנות.
    (ג) אחרת None.

    הערה: זו היוריסטיקה — ה-AI רשאי לנסח/לדלג בהתאם ל-system prompt.
    db מתקבל לעקביות חתימה עם שאר ה-compute_* (לא נדרש כאן — open_state כבר חושב).
    """
    stuck = open_state.get("stuck_leads_count", 0)
    stale = open_state.get("stale_proposals_count", 0)
    if stuck > 0:
        return "לעבור על הלידים התקועים ולקבל החלטה לגבי כל אחד מהם"
    if stale > 0:
        return "לעשות פולואפ להצעות שנשלחו ולא קיבלו מענה"
    return None


# ===== assembly שבועי =====


async def _resolve_weekly_open_state(
    db: AsyncSession,
    week_end_utc: datetime,
    week_end_date: date,
) -> tuple[dict, int]:
    """שולף את "מצב פתוח בסוף השבוע" מ-snapshot קבוע, או fallback ל-live.

    דרך-המלך: row ב-`weekly_open_state_snapshots` נכתב ע"י cron בראשון 00:00
    שעון ישראל (`jobs/capture_weekly_open_state`). שחזור מתוך שדות mutable
    אינו אמין (7 ממצאי cursor bugbot); הצילום פותר את הבעיה בשורש.

    fallback ל-`_open_state(db, week_end)` + `_dormant_with_recommendation_count`
    כש-snapshot חסר — לפני שה-cron הראשון רץ, או אם נכשל. logged בכל פעם
    שה-fallback מופעל כדי שיהיה visible ב-monitoring.

    מחזיר (open_state_dict, dormant_count) כדי לשמר את החתימה של ה-callers.
    """
    from app.models.weekly_open_state_snapshot import WeeklyOpenStateSnapshot

    snapshot = (
        await db.execute(
            select(WeeklyOpenStateSnapshot).where(
                WeeklyOpenStateSnapshot.week_end_date == week_end_date
            )
        )
    ).scalar_one_or_none()

    if snapshot is not None:
        return (
            {
                "open_leads_total": snapshot.open_leads_total,
                "stuck_leads_count": snapshot.stuck_leads_count,
                "stale_proposals_count": snapshot.stale_proposals_count,
                "overdue_tasks_count": snapshot.overdue_tasks_count,
            },
            snapshot.dormant_with_recommendation_count,
        )

    logger.warning(
        "weekly open-state snapshot missing for week ending %s — "
        "falling back to live _open_state. cron capture_weekly_open_state "
        "may have failed or not yet run.",
        week_end_date,
    )
    open_state = await _open_state(db, week_end_utc)
    dormant = await _dormant_with_recommendation_count(db)
    return open_state, dormant


async def build_weekly_user_prompt(
    db: AsyncSession, now_utc: datetime | None = None
) -> str:
    """
    אוסף את כל הקלט המבושל לסיכום השבועי ומרכיב אותו לתוך WEEKLY_USER_TEMPLATE.
    החלון הוא השבוע הקודם המלא (ראשון→ראשון); מטריקות מצב (`open_state`) הן
    snapshot **לסוף השבוע** (week_end), לא ל-now — כך פעילות שקרתה בפער שבין
    סוף-השבוע לרגע ה-cron (ראשון בבוקר) לא משויכת בטעות לסיכום השבועי
    (תיקון cursor bot: counts may not match the stated range).
    מחזיר את ה-user prompt המוכן ל-generate_weekly_summary_text.
    """
    now_utc = now_utc or datetime.now(timezone.utc)
    week_start, week_end = _last_week_bounds(now_utc)

    # תאריכי תצוגה: התחלה = ראשון; סוף = שבת (יום אחד לפני ה-end הלא-כולל).
    week_start_date = to_israel_tz(week_start).date()
    week_end_date = to_israel_tz(week_end).date() - timedelta(days=1)
    weeks_in_system = compute_weeks_in_system(week_start_date)
    comparison = has_comparison_data(weeks_in_system)

    # מטריקות חלון-שבועי (שימוש חוזר בעוזרי היומי עם החלון השבועי).
    activity = await _activity_counts_by_role(db, week_start, week_end)
    tasks = await _tasks_completed_by_role(db, week_start, week_end)
    movement = await _lead_movement(db, week_start, week_end)
    newly_dormant = await _newly_dormant_count(db, week_start, week_end)

    # snapshot מצב נכון לסוף השבוע — נשלף מ-row קבוע ב-weekly_open_state_snapshots
    # שנכתב ע"י cron ב-ראשון 00:00 שעון ישראל (`jobs/capture_weekly_open_state`).
    # זה ה-source-of-truth: שחזור מתוך שדות mutable (status נוכחי, due_at שנדרס
    # ב-snooze, closed_at שמתאפס ב-reopen) הוכח כלא אמין (7 ממצאי cursor bugbot).
    # fallback ל-live `_open_state(db, week_end)` אם אין snapshot — לפני שה-cron
    # הראשון רץ או אם נכשל. ה-live מבוסס על temporal predicates עם best-effort
    # ידוע ומתועד.
    open_state, dormant_count = await _resolve_weekly_open_state(
        db, week_end, week_end_date
    )

    trends = await compute_trends_block(
        db,
        week_start,
        week_end,
        weeks_in_system,
        curr_new_leads=movement["new_leads_count"],
        curr_won=movement["won_count"],
    )
    insights = await compute_precomputed_insights_block(db, now_utc)
    next_week_focus = compute_next_week_focus_suggestion(db, now_utc, open_state)

    return WEEKLY_USER_TEMPLATE.format(
        week_start=week_start_date.isoformat(),
        week_end=week_end_date.isoformat(),
        week_number_in_system=weeks_in_system,
        has_comparison_data="true" if comparison else "false",
        noa_calls_week=activity["noa_calls"],
        noa_outbound_week=activity["noa_outbound"],
        noa_tasks_week=tasks["noa_tasks"],
        assistant_calls_week=activity["assistant_calls"],
        assistant_outbound_week=activity["assistant_outbound"],
        assistant_tasks_week=tasks["assistant_tasks"],
        new_leads_week=movement["new_leads_count"],
        new_leads_by_source_text=movement["new_leads_by_source_text"],
        # פילוח לפי שירות נשאר ברמת subtype (מה-_lead_movement) — רק התובנות
        # האסטרטגיות מקובצות לפי category.
        new_leads_by_category_text=movement["new_leads_by_category_text"],
        won_week=movement["won_count"],
        lost_week=movement["lost_count"],
        inbound_week=movement["inbound_actions_count"],
        open_leads_end_of_week=open_state["open_leads_total"],
        stuck_leads_count=open_state["stuck_leads_count"],
        stale_proposals_count=open_state["stale_proposals_count"],
        newly_dormant_count=newly_dormant,
        total_dormant_with_recommendation=dormant_count,
        trends_block_or_no_comparison=trends,
        precomputed_insights_block=insights,
        next_week_focus_suggestion_or_null=(
            next_week_focus if next_week_focus is not None else "null"
        ),
    )
