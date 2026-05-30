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
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.constants import (
    CLOSED_LEAD_STATUSES,
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
from app.prompts.daily_summary import USER_TEMPLATE
from app.services.tasks import surfaceable_task_condition
from app.utils.labels import SERVICE_SUBTYPE_HE, SOURCE_CHANNEL_HE
from app.utils.work_hours import to_israel_tz

logger = logging.getLogger("services.summary_inputs")

# ===== קבועי מיפוי =====

# הודעות יוצאות — שלושת ה-ActivityType שמייצגים שליחה יוצאת של נועה/העוזרת.
_OUTBOUND_TYPES = (
    ActivityType.TEMPLATE_MARKED_SENT.value,
    ActivityType.MANUAL_MESSAGE_LOGGED.value,
    ActivityType.OUTBOUND_MESSAGE_LOGGED.value,
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

    # פילוח לפי שירות. הערה: השדה נקרא "קטגוריה" אך דוגמאות ה-few-shot
    # ב-§5.4/§5.8 מציגות granularity ברמת ה-*subtype* (שיקום קול, ליווי הפקה),
    # לכן הפילוח נעשה לפי service_subtype. ראה נקודה לאישור בסיכום הסבב.
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
    # נכנסות שתועדו (INBOUND_MESSAGE_LOGGED). ראה נקודה לאישור בסיכום הסבב.
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


# ===== מצב פתוחים (snapshot ל-now) =====

def _stuck_lead_condition(now_utc: datetime):
    """ליד פתוח עם task פעיל surfaceable שה-due_at שלו עבר ב-7+ ימים (כלל 10)."""
    threshold = now_utc - timedelta(days=_STUCK_DAYS)
    stuck_task_exists = (
        select(Task.id)
        .where(
            Task.lead_id == Lead.id,
            Task.status.in_([TaskStatus.OPEN.value, TaskStatus.SNOOZED.value]),
            Task.due_at <= threshold,
            surfaceable_task_condition(),
        )
        .correlate(Lead)
        .exists()
    )
    return (
        Lead.status.notin_([s.value for s in CLOSED_LEAD_STATUSES]),
        stuck_task_exists,
    )


async def _open_state(db: AsyncSession, now_utc: datetime) -> dict:
    """ספירות מצב נכון ל-now (לא תלוי חלון)."""
    closed = [s.value for s in CLOSED_LEAD_STATUSES]

    open_leads_total = (
        await db.execute(
            select(func.count()).select_from(Lead).where(Lead.status.notin_(closed))
        )
    ).scalar_one()

    stuck_leads_count = (
        await db.execute(
            select(func.count()).select_from(Lead).where(*_stuck_lead_condition(now_utc))
        )
    ).scalar_one()

    # הצעה תקועה: PROPOSAL_SENT שנשלח לפני 4+ ימים. proposal_sent_at הוא
    # השדה הייעודי; fallback ל-last_outbound_at ללידים ישנים (כמו get_open_proposals).
    stale_threshold = now_utc - timedelta(days=_STALE_PROPOSAL_DAYS)
    sent_at = func.coalesce(Lead.proposal_sent_at, Lead.last_outbound_at)
    stale_proposals_count = (
        await db.execute(
            select(func.count()).select_from(Lead).where(
                Lead.status == LeadStatus.PROPOSAL_SENT.value,
                sent_at.is_not(None),
                sent_at <= stale_threshold,
            )
        )
    ).scalar_one()

    # משימות שעברו את היעד ולא טופלו: task פעיל surfaceable עם due_at<=now.
    overdue_tasks_count = (
        await db.execute(
            select(func.count()).select_from(Task).where(
                Task.status.in_([TaskStatus.OPEN.value, TaskStatus.SNOOZED.value]),
                Task.due_at <= now_utc,
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

    # (1) שבירת שתיקה: last_inbound_at בחלון, ופער של 7+ ימים מ-outbound האחרון.
    # פעולת לקוח — בלי "בוצע ע"י".
    silence_rows = (
        await db.execute(
            select(Lead).where(
                Lead.last_inbound_at >= window_start,
                Lead.last_inbound_at < now_utc,
                Lead.last_outbound_at.is_not(None),
                Lead.last_inbound_at - Lead.last_outbound_at
                >= timedelta(days=_SILENCE_BREAK_DAYS),
            )
        )
    ).scalars().all()
    for lead in silence_rows:
        gap_days = (lead.last_inbound_at - lead.last_outbound_at).days
        if _add(lead, f"ענה אחרי {gap_days} ימי שתיקה", None):
            return "\n".join(lines)

    # (2) שינוי סטטוס משמעותי: LEAD_WON, או STATUS_CHANGED ל-BOOKED, בחלון.
    status_events = (
        await db.execute(
            select(Activity, Lead, User.role)
            .join(Lead, Activity.lead_id == Lead.id)
            .join(User, Activity.performed_by == User.id, isouter=True)
            .where(
                Activity.created_at >= window_start,
                Activity.created_at < now_utc,
                or_(
                    Activity.type == ActivityType.LEAD_WON.value,
                    (Activity.type == ActivityType.STATUS_CHANGED.value)
                    & (
                        Activity.activity_metadata["new_status"].astext
                        == LeadStatus.BOOKED.value
                    ),
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


async def compute_attention_items_block(db: AsyncSession, now_utc: datetime) -> str:
    """
    0-3 פריטים שדורשים תשומת לב (§6.3.2), בסדר עדיפות:
    1. הצעה ללא מענה מעל 4 ימים.
    2. ליד תקוע מעל 7 ימים.
    3. משימה פעילה שעברה את היעד.
    מחזיר מחרוזת בפורמט §4.1, או "(ריק)" אם אין.
    """
    lines: list[str] = []

    # (1) הצעות תקועות — הוותיקה ביותר ראשונה.
    sent_at = func.coalesce(Lead.proposal_sent_at, Lead.last_outbound_at)
    stale_threshold = now_utc - timedelta(days=_STALE_PROPOSAL_DAYS)
    stale = (
        await db.execute(
            select(Lead, sent_at.label("sent"))
            .where(
                Lead.status == LeadStatus.PROPOSAL_SENT.value,
                sent_at.is_not(None),
                sent_at <= stale_threshold,
            )
            .order_by(sent_at.asc())
            .limit(_BLOCK_LIMIT)
        )
    ).all()
    for lead, sent in stale:
        days = max(0, (now_utc - sent).days)
        lines.append(
            f"- סוג: הצעה ללא מענה | ליד: {_lead_display_name(lead)} | "
            f"ימים מאז שליחה: {days}"
        )
        if len(lines) >= _BLOCK_LIMIT:
            return "\n".join(lines)

    # (2) לידים תקועים — הוותיק ביותר (לפי due_at של ה-task התקוע) ראשון.
    # "ימים בסטטוס נוכחי" מקורב לימים שעברו מ-due_at של המשימה התקועה,
    # כי ל-Lead אין status_changed_at. ראה נקודה לאישור בסיכום הסבב.
    stuck = (
        await db.execute(
            select(Lead, func.min(Task.due_at).label("oldest_due"))
            .join(Task, Task.lead_id == Lead.id)
            .where(
                Lead.status.notin_([s.value for s in CLOSED_LEAD_STATUSES]),
                Task.status.in_([TaskStatus.OPEN.value, TaskStatus.SNOOZED.value]),
                Task.due_at <= now_utc - timedelta(days=_STUCK_DAYS),
                surfaceable_task_condition(),
            )
            .group_by(Lead.id)
            .order_by(func.min(Task.due_at).asc())
            .limit(_BLOCK_LIMIT)
        )
    ).all()
    for lead, oldest_due in stuck:
        days = max(0, (now_utc - oldest_due).days)
        lines.append(
            f"- סוג: ליד תקוע | ליד: {_lead_display_name(lead)} | "
            f"ימים בסטטוס נוכחי: {days}"
        )
        if len(lines) >= _BLOCK_LIMIT:
            return "\n".join(lines)

    # (3) משימות פעילות שעברו את היעד — הוותיקה ביותר ראשונה.
    overdue = (
        await db.execute(
            select(Task, Lead)
            .join(Lead, Task.lead_id == Lead.id)
            .where(
                Task.status.in_([TaskStatus.OPEN.value, TaskStatus.SNOOZED.value]),
                Task.due_at <= now_utc,
                surfaceable_task_condition(),
            )
            .order_by(Task.due_at.asc())
            .limit(_BLOCK_LIMIT)
        )
    ).all()
    for task, lead in overdue:
        desc = (task.task_metadata or {}).get("description") if task.task_metadata else None
        desc = desc or _task_type_label(task.type)
        lines.append(
            f"- סוג: משימה שלא בוצעה | ליד: {_lead_display_name(lead)} | "
            f"תיאור: {desc}"
        )
        if len(lines) >= _BLOCK_LIMIT:
            return "\n".join(lines)

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


def compute_tomorrow_focus_suggestion(open_state: dict, attention_block: str) -> str | None:
    """
    הצעת פוקוס אחת למחר (§6.3.3), מחושבת מראש — או None.
    היוריסטיקה (סבב ראשון): אם יש פריט "דורש תשומת לב", מצביעים על הפריט
    הראשון (הדחוף ביותר). אם אין — None. ראה נקודה לאישור בסיכום הסבב.
    """
    if attention_block == "(ריק)":
        return None
    first = attention_block.splitlines()[0]
    if "הצעה ללא מענה" in first:
        return "כדאי לפתוח את היום במעקב אחר ההצעה הוותיקה ביותר שטרם קיבלה מענה."
    if "ליד תקוע" in first:
        return "כדאי להתחיל מהליד התקוע הוותיק ביותר ולקבל לגביו החלטה."
    if "משימה שלא בוצעה" in first:
        return "כדאי לפתוח את היום בסגירת המשימה הוותיקה ביותר שעברה את היעד."
    return None


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
    attention = await compute_attention_items_block(db, now_utc)
    dormant_count = await _dormant_with_recommendation_count(db)
    tomorrow = compute_tomorrow_focus_suggestion(open_state, attention)

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
