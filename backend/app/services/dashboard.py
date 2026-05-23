"""
שירות dashboard — שאילתות וחישובים למסך הבית ולכל ה-views הקבועים.

עקרון מרכזי: כל הלוגיקה של "מה דחוף", "איך ממיינים", ו"מה הצבע"
מרוכזת כאן. ה-routes רק שולפים ומגישים לפי הסכמות.
"""

from datetime import datetime, time, timedelta, timezone
from uuid import UUID

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import CLOSED_LEAD_STATUSES, LeadStatus, TaskStatus
from app.models.lead import Lead
from app.models.task import Task
from app.schemas.dashboard import (
    LeadCard,
    ProposalCard,
    TodayActionItem,
    WeeklyInsights,
)
from app.utils.work_hours import ISRAEL_TZ, to_israel_tz

# ===== קבועי תצוגה =====
# כמה ימים קדימה נחשב "פולואפ קרוב" — מצביע על כתום
ORANGE_LOOKAHEAD = timedelta(hours=48)
# 5-7 פעולות היום לפי האפיון. נשמור up to 20 כדי לא לחתוך אם יש עומס
TODAY_ACTIONS_LIMIT = 20
DEFAULT_DASHBOARD_LIMIT = 50


# ===================== חישוב צבע מצב =====================

def derive_state_color(lead: Lead, now_utc: datetime) -> str:
    """
    מחשב את צבע המצב של ליד לפי 4 קטגוריות מהאפיון:
    - gray: סגור / בארכיב
    - red: דורש טיפול היום (needs_attention או פולואפ שעבר)
    - orange: פולואפ קרוב (בתוך ORANGE_LOOKAHEAD)
    - green: בתהליך תקין
    """
    if lead.status in CLOSED_LEAD_STATUSES:
        return "gray"

    if lead.needs_attention:
        return "red"

    if lead.next_action_due_at is not None:
        if lead.next_action_due_at <= now_utc:
            return "red"  # פולואפ עבר את מועדו
        if lead.next_action_due_at <= now_utc + ORANGE_LOOKAHEAD:
            return "orange"

    return "green"


def _has_recent_reply(lead: Lead, now_utc: datetime) -> bool:
    return lead.reply_boost_until is not None and lead.reply_boost_until > now_utc


def _lead_to_card(lead: Lead, now_utc: datetime) -> LeadCard:
    return LeadCard(
        id=lead.id,
        full_name=lead.full_name,
        organization_name=lead.organization_name,
        service_category=lead.service_category,
        service_subtype=lead.service_subtype,
        status=lead.status,
        waiting_on=lead.waiting_on,
        priority_level=lead.priority_level,
        preferred_contact=lead.preferred_contact,
        state_color=derive_state_color(lead, now_utc),
        needs_attention=lead.needs_attention,
        last_inbound_at=lead.last_inbound_at,
        last_outbound_at=lead.last_outbound_at,
        next_action_due_at=lead.next_action_due_at,
        has_recent_reply=_has_recent_reply(lead, now_utc),
    )


# ===================== ORDER BY של הדשבורד =====================

def _dashboard_order(now_utc: datetime) -> list:
    """
    מיישם את 6 שלבי המיון מסעיף 3 ב"תוספות לאפיון":
    1. דחיפות (needs_attention או פולואפ שעבר)
    2. ליד NEW שלא נגעו בו (אין last_outbound_at)
    3. תגובה לאחרונה (reply_boost_until בתוקף)
    4. VIP / hot
    5. תאריך פולואפ קרוב
    6. עדכון אחרון (חדש קודם)
    """
    return [
        case(
            (
                or_(
                    Lead.needs_attention.is_(True),
                    and_(
                        Lead.next_action_due_at.is_not(None),
                        Lead.next_action_due_at <= now_utc,
                    ),
                ),
                0,
            ),
            else_=1,
        ),
        case(
            (
                and_(
                    Lead.status == LeadStatus.NEW.value,
                    Lead.last_outbound_at.is_(None),
                ),
                0,
            ),
            else_=1,
        ),
        case(
            (Lead.reply_boost_until > now_utc, 0),
            else_=1,
        ),
        case(
            (Lead.priority_level.in_(["hot", "vip"]), 0),
            else_=1,
        ),
        Lead.next_action_due_at.asc().nulls_last(),
        Lead.updated_at.desc(),
    ]


# ===================== חלונות זמן =====================

def _end_of_today_israel(now_utc: datetime) -> datetime:
    """סוף יום נוכחי בזמן Asia/Jerusalem — מוחזר ב-UTC לשימוש ב-DB."""
    local = to_israel_tz(now_utc)
    end_local = datetime.combine(local.date(), time(23, 59, 59, tzinfo=ISRAEL_TZ))
    return end_local.astimezone(timezone.utc)


def _current_week_bounds(now_utc: datetime) -> tuple[datetime, datetime]:
    """
    מחזיר (start, end) של השבוע הנוכחי בזמן ישראל.
    בישראל השבוע מתחיל ביום ראשון.
    """
    local = to_israel_tz(now_utc)
    today = local.date()
    # weekday: שני=0, ..., שישי=4, שבת=5, ראשון=6.
    # מספר ימים אחורה כדי להגיע ליום ראשון:
    days_since_sunday = (today.weekday() + 1) % 7
    sunday = today - timedelta(days=days_since_sunday)
    start_local = datetime.combine(sunday, time(0, 0, tzinfo=ISRAEL_TZ))
    end_local = start_local + timedelta(days=7)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


# ===================== Today's Actions =====================

async def get_today_actions(db: AsyncSession) -> list[TodayActionItem]:
    """
    משימות פתוחות + snoozed שעבר מועדן, שה-due_at שלהן <= סוף היום בישראל.
    כולל overdue (משימות מאתמול שלא הושלמו).
    """
    now_utc = datetime.now(timezone.utc)
    end_today = _end_of_today_israel(now_utc)

    stmt = (
        select(Task, Lead)
        .join(Lead, Task.lead_id == Lead.id)
        .where(
            or_(
                Task.status == TaskStatus.OPEN.value,
                and_(
                    Task.status == TaskStatus.SNOOZED.value,
                    Task.due_at <= now_utc,
                ),
            ),
            Task.due_at <= end_today,
        )
        # מיון: overdue קודם, אדום קודם, ואז לפי due_at
        .order_by(
            (Task.due_at <= now_utc).desc(),
            Lead.needs_attention.desc(),
            case(
                (Lead.priority_level.in_(["hot", "vip"]), 0),
                else_=1,
            ),
            Task.due_at.asc(),
        )
        .limit(TODAY_ACTIONS_LIMIT)
    )

    result = await db.execute(stmt)
    items: list[TodayActionItem] = []
    for task, lead in result.all():
        items.append(
            TodayActionItem(
                task_id=task.id,
                lead_id=lead.id,
                lead_name=lead.full_name,
                lead_organization=lead.organization_name,
                task_type=task.type,
                due_at=task.due_at,
                is_overdue=task.due_at <= now_utc,
                state_color=derive_state_color(lead, now_utc),
                priority_level=lead.priority_level,
                preferred_contact=lead.preferred_contact,
                service_category=lead.service_category,
            )
        )
    return items


# ===================== פניות חדשות =====================

async def get_new_leads(
    db: AsyncSession, *, limit: int = DEFAULT_DASHBOARD_LIMIT
) -> list[LeadCard]:
    """לידים בסטטוס NEW שעוד לא קיבלו פעולת outbound."""
    now_utc = datetime.now(timezone.utc)
    stmt = (
        select(Lead)
        .where(
            Lead.status == LeadStatus.NEW.value,
            Lead.last_outbound_at.is_(None),
        )
        .order_by(*_dashboard_order(now_utc))
        .limit(limit)
    )
    result = await db.execute(stmt)
    return [_lead_to_card(lead, now_utc) for lead in result.scalars().all()]


# ===================== ממתין לטיפול =====================

async def get_pending(
    db: AsyncSession, *, limit: int = DEFAULT_DASHBOARD_LIMIT
) -> list[LeadCard]:
    """
    לידים פתוחים שדורשים תשומת לב:
    - needs_attention=True (התראה שלא טופלה),
    - או פולואפ שעבר מועדו ועוד לא נסגר.
    """
    now_utc = datetime.now(timezone.utc)
    stmt = (
        select(Lead)
        .where(
            Lead.status.notin_([s.value for s in CLOSED_LEAD_STATUSES]),
            or_(
                Lead.needs_attention.is_(True),
                and_(
                    Lead.next_action_due_at.is_not(None),
                    Lead.next_action_due_at <= now_utc,
                ),
            ),
        )
        .order_by(*_dashboard_order(now_utc))
        .limit(limit)
    )
    result = await db.execute(stmt)
    return [_lead_to_card(lead, now_utc) for lead in result.scalars().all()]


# ===================== הצעות פתוחות =====================

async def get_open_proposals(
    db: AsyncSession, *, limit: int = DEFAULT_DASHBOARD_LIMIT
) -> list[ProposalCard]:
    """לידים בסטטוס PROPOSAL_SENT עם חישוב כמה ימים עברו מהשליחה."""
    now_utc = datetime.now(timezone.utc)
    stmt = (
        select(Lead)
        .where(Lead.status == LeadStatus.PROPOSAL_SENT.value)
        .order_by(*_dashboard_order(now_utc))
        .limit(limit)
    )
    result = await db.execute(stmt)
    cards: list[ProposalCard] = []
    for lead in result.scalars().all():
        base = _lead_to_card(lead, now_utc).model_dump()
        days = None
        if lead.last_outbound_at is not None:
            delta = now_utc - lead.last_outbound_at
            days = max(0, delta.days)
        cards.append(
            ProposalCard(
                **base,
                proposal_sent_at=lead.last_outbound_at,
                days_since_proposal=days,
            )
        )
    return cards


# ===================== תובנות שבועיות =====================

async def get_weekly_insights(db: AsyncSession) -> WeeklyInsights:
    """
    3 התובנות לפי האפיון:
    - new_leads_count: כמה לידים נכנסו השבוע
    - responded_in_time_count: כמה קיבלו מענה outbound באותו יום העבודה
    - stuck_count: כמה לידים פתוחים בלי next_action_due_at מוגדר

    בנוסף total_open לקונטקסט.
    """
    now_utc = datetime.now(timezone.utc)
    week_start_utc, week_end_utc = _current_week_bounds(now_utc)

    # כמה לידים נכנסו השבוע
    new_count_stmt = (
        select(func.count())
        .select_from(Lead)
        .where(Lead.created_at >= week_start_utc, Lead.created_at < week_end_utc)
    )
    new_leads_count = (await db.execute(new_count_stmt)).scalar_one()

    # מענה בזמן: ליד שיצרנו לו outbound תוך 24 שעות מהיצירה.
    # זה proxy טוב ל"באותו יום העבודה" בלי לחשב חגים.
    responded_stmt = (
        select(func.count())
        .select_from(Lead)
        .where(
            Lead.created_at >= week_start_utc,
            Lead.created_at < week_end_utc,
            Lead.last_outbound_at.is_not(None),
            Lead.last_outbound_at <= Lead.created_at + timedelta(hours=24),
        )
    )
    responded_in_time_count = (await db.execute(responded_stmt)).scalar_one()

    # נתקעו: ליד פתוח בלי next_action_due_at (אין מה לעשות מוגדר)
    stuck_stmt = (
        select(func.count())
        .select_from(Lead)
        .where(
            Lead.status.notin_([s.value for s in CLOSED_LEAD_STATUSES]),
            Lead.next_action_due_at.is_(None),
        )
    )
    stuck_count = (await db.execute(stuck_stmt)).scalar_one()

    # סה"כ פתוחים
    open_stmt = (
        select(func.count())
        .select_from(Lead)
        .where(Lead.status.notin_([s.value for s in CLOSED_LEAD_STATUSES]))
    )
    total_open = (await db.execute(open_stmt)).scalar_one()

    return WeeklyInsights(
        week_start=week_start_utc,
        week_end=week_end_utc,
        new_leads_count=new_leads_count,
        responded_in_time_count=responded_in_time_count,
        stuck_count=stuck_count,
        total_open=total_open,
    )
