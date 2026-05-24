"""
שירות dashboard — שאילתות וחישובים למסך הבית ולכל ה-views הקבועים.

עקרון מרכזי: כל הלוגיקה של "מה דחוף", "איך ממיינים", ו"מה הצבע"
מרוכזת כאן. ה-routes רק שולפים ומגישים לפי הסכמות.
"""

from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import CLOSED_LEAD_STATUSES, LeadStatus, TaskStatus, TaskType
from app.models.lead import Lead
from app.models.task import Task
from app.schemas.dashboard import (
    LeadCard,
    ProfitableServiceInsight,
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

# grace period per-type ל-is_overdue. לפי האפיון יב סעיף 482 — 5 כללים
# שונים. החלטה §7.4 ב-phase-2.5-plan.md: hardcoded, בלי UI ל-settings.
#
# הערות:
# - FIRST_RESPONSE: 24h. ה-task מופיע מיד ב-/today, badge רק אחרי יום.
# - FOLLOWUP (כללי): 60h = ממוצע 48-72h (לקוח שהתעניין ולא סגר).
# - PROPOSAL_FOLLOWUP: 4 ימים = ממוצע 3-5 ימי עסקים (הצעה לארגון).
# - DORMANT_REACHOUT: 75 יום = ממוצע 60-90 יום (חידוש קשר).
# - AFTER_HOURS_REPLY: 24h (כמו FIRST_RESPONSE).
#
# POST_MEETING_UPDATE ו-PROGRAM_END לא ברשימה — משתמשים ב-due_at ישיר.
# מקור יחיד לטובת SQL CASE ול-Python helper גם יחד.
from app.constants import (
    FOLLOWUP_GRACE_DORMANT,
    FOLLOWUP_GRACE_FIRST_RESPONSE,
    FOLLOWUP_GRACE_PROPOSAL_ORG,
    FOLLOWUP_GRACE_WARM,
)

_OVERDUE_GRACE: dict[str, timedelta] = {
    TaskType.FIRST_RESPONSE.value: FOLLOWUP_GRACE_FIRST_RESPONSE,
    TaskType.FOLLOWUP.value: FOLLOWUP_GRACE_WARM,
    TaskType.PROPOSAL_FOLLOWUP.value: FOLLOWUP_GRACE_PROPOSAL_ORG,
    TaskType.DORMANT_REACHOUT.value: FOLLOWUP_GRACE_DORMANT,
    TaskType.AFTER_HOURS_REPLY.value: FOLLOWUP_GRACE_FIRST_RESPONSE,
}


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

def _start_of_tomorrow_israel(now_utc: datetime) -> datetime:
    """
    תחילת יום המחר בזמן Asia/Jerusalem (00:00) — מוחזר ב-UTC.
    משמש כגבול exclusive: due_at < _start_of_tomorrow. כך לא מפספסים
    משימות שנמצאות בשנייה האחרונה של היום.
    """
    local = to_israel_tz(now_utc)
    tomorrow = local.date() + timedelta(days=1)
    start_local = datetime.combine(tomorrow, time(0, 0, tzinfo=ISRAEL_TZ))
    return start_local.astimezone(timezone.utc)


def _current_week_bounds(now_utc: datetime) -> tuple[datetime, datetime]:
    """
    מחזיר (start, end) של השבוע הנוכחי בזמן ישראל.
    בישראל השבוע מתחיל ביום ראשון.

    שני ה-bounds נבנים כ-midnight מקומי באופן עצמאי (לא start+7days)
    כי datetime+timedelta מוסיף שעות אבסולוטיות — בשבוע של מעבר שעון
    (אביב/סתיו) end_local היה נופל ב-01:00 או 23:00 במקום חצות.
    """
    local = to_israel_tz(now_utc)
    today = local.date()
    # weekday: שני=0, ..., שישי=4, שבת=5, ראשון=6.
    # מספר ימים אחורה כדי להגיע ליום ראשון:
    days_since_sunday = (today.weekday() + 1) % 7
    sunday = today - timedelta(days=days_since_sunday)
    next_sunday = sunday + timedelta(days=7)
    start_local = datetime.combine(sunday, time(0, 0, tzinfo=ISRAEL_TZ))
    end_local = datetime.combine(next_sunday, time(0, 0, tzinfo=ISRAEL_TZ))
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


# ===================== Today's Actions =====================

async def get_today_actions(db: AsyncSession) -> list[TodayActionItem]:
    """
    משימות פתוחות + snoozed שעבר מועדן, שה-due_at שלהן <= סוף היום בישראל.
    כולל overdue (משימות מאתמול שלא הושלמו).
    """
    now_utc = datetime.now(timezone.utc)
    end_today_exclusive = _start_of_tomorrow_israel(now_utc)
    closed = [s.value for s in CLOSED_LEAD_STATUSES]

    # ביטוי is_overdue per-type — אותה לוגיקה כמו _calc_is_overdue ב-Python
    # אבל ב-SQL כדי שגם המיון יכבד את ה-grace. אחרת FIRST_RESPONSE עם
    # due_at=now היה קופץ לראש מיד, גם כשה-badge עוד לא דולק. ה-grace
    # נשאב מ-_OVERDUE_GRACE — מקור יחיד שמשמש גם את _calc_is_overdue.
    is_overdue_expr = case(
        *[
            (Task.type == task_type, Task.created_at + grace <= now_utc)
            for task_type, grace in _OVERDUE_GRACE.items()
        ],
        else_=Task.due_at <= now_utc,
    )

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
            Task.due_at < end_today_exclusive,
            # סינון לידים סגורים — defense in depth. close_lead מבטל
            # tasks פתוחים שלהם, אבל אם משהו פספס (race / cron) זה תופס.
            Lead.status.notin_(closed),
        )
        # מיון: overdue קודם (לפי הביטוי per-type), אדום קודם, ואז לפי due_at
        .order_by(
            is_overdue_expr.desc(),
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
                is_overdue=_calc_is_overdue(task, now_utc),
                state_color=derive_state_color(lead, now_utc),
                priority_level=lead.priority_level,
                preferred_contact=lead.preferred_contact,
                service_category=lead.service_category,
            )
        )
    return items


def _calc_is_overdue(task, now_utc: datetime) -> bool:
    """
    מחשב is_overdue עם grace per-type. ל-FIRST_RESPONSE: 24h מ-task.created_at
    (לפי האפיון). לשאר ה-types: due_at <= now כרגיל.

    הלוגיקה הזו משוכפלת ב-SQL ב-get_today_actions (is_overdue_expr) כדי
    שגם המיון יכבד את ה-grace — אחרת המשימה תקפוץ לראש לפני שה-badge דולק.
    """
    grace = _OVERDUE_GRACE.get(task.type)
    if grace is not None:
        return task.created_at + grace <= now_utc
    return task.due_at <= now_utc


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
        # proposal_sent_at שדה ייעודי שלא מתאפס בפולואפ outbound.
        # fallback ל-last_outbound_at לטובת לידים ישנים שנוצרו לפני המיגרציה.
        sent_at = lead.proposal_sent_at or lead.last_outbound_at
        days = None
        if sent_at is not None:
            delta = now_utc - sent_at
            days = max(0, delta.days)
        cards.append(
            ProposalCard(
                **base,
                proposal_sent_at=sent_at,
                days_since_proposal=days,
            )
        )
    return cards


# ===================== תובנות שבועיות =====================

async def _get_most_profitable_service_this_week(
    db: AsyncSession,
    week_start_utc: datetime,
    week_end_utc: datetime,
) -> ProfitableServiceInsight | None:
    """
    מחשב את "השעה הרווחית שלך השבוע": לכל קטגוריית שירות, סוכם הכנסה
    ושעות מעסקאות שנסגרו השבוע כ-WON, ומחזיר את הקטגוריה עם התעריף
    השעתי האפקטיבי הגבוה ביותר.

    דורש closed_value + actual_hours > 0; ליד WON בלי נתונים אלה לא נספר
    (פשוט לא מספיק מידע — לא דחיפה לנועה להמציא ערכים).
    """
    stmt = (
        select(
            Lead.service_category,
            func.sum(Lead.closed_value).label("total_revenue"),
            func.sum(Lead.actual_hours).label("total_hours"),
            func.count().label("deals_count"),
        )
        .where(
            Lead.status == LeadStatus.WON.value,
            Lead.closed_at >= week_start_utc,
            Lead.closed_at < week_end_utc,
            Lead.closed_value.is_not(None),
            Lead.actual_hours.is_not(None),
            Lead.actual_hours > 0,
        )
        .group_by(Lead.service_category)
    )
    result = await db.execute(stmt)
    best: ProfitableServiceInsight | None = None
    for row in result.all():
        rate = Decimal(row.total_revenue) / Decimal(row.total_hours)
        if best is None or rate > best.hourly_rate:
            best = ProfitableServiceInsight(
                service_category=row.service_category,
                hourly_rate=rate.quantize(Decimal("0.01")),
                total_revenue=Decimal(row.total_revenue),
                total_hours=Decimal(row.total_hours),
                deals_count=int(row.deals_count),
            )
    return best


async def get_weekly_insights(db: AsyncSession) -> WeeklyInsights:
    """
    3 התובנות לפי האפיון:
    - new_leads_count: כמה לידים נכנסו השבוע
    - responded_in_time_count: כמה קיבלו מענה outbound באותו יום העבודה
    - stuck_count: "לא טופלו בזמן" — לידים פתוחים שיש להם task פעיל
      שעבר זמן הטיפול שלו (לפי per-type grace).
    - most_profitable_service: השעה הרווחית של השבוע (אם יש נתונים)

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

    # "לא טופלו בזמן": ליד פתוח עם task פעיל שעבר זמן הטיפול. ה-grace
    # per-type נשאב מ-_OVERDUE_GRACE (5 כללים מהאפיון יב סעיף 482):
    # FIRST_RESPONSE/AFTER_HOURS_REPLY=24h, FOLLOWUP=60h, PROPOSAL_FOLLOWUP=4d,
    # DORMANT_REACHOUT=75d. שאר ה-types: due_at <= now (בלי grace).
    #
    # ליד חדש שזה עתה נוצר *לא* נספר כי ה-grace של 24h עוד לא חלף.
    # ליד פתוח בלי tasks פעילים *לא* נספר (זה bug אחר — לטפל בו דרך
    # יצירה אוטומטית של tasks, לא דרך הספירה הזו).
    typed_overdue_conditions = [
        and_(
            Task.type == task_type,
            Task.created_at + grace <= now_utc,
        )
        for task_type, grace in _OVERDUE_GRACE.items()
    ]
    overdue_task_condition = or_(
        *typed_overdue_conditions,
        and_(
            Task.type.notin_(list(_OVERDUE_GRACE.keys())),
            Task.due_at <= now_utc,
        ),
    )
    overdue_task_exists = (
        select(Task.id)
        .where(
            Task.lead_id == Lead.id,
            Task.status.in_(
                [TaskStatus.OPEN.value, TaskStatus.SNOOZED.value]
            ),
            overdue_task_condition,
        )
        .correlate(Lead)
        .exists()
    )
    stuck_stmt = (
        select(func.count())
        .select_from(Lead)
        .where(
            Lead.status.notin_([s.value for s in CLOSED_LEAD_STATUSES]),
            overdue_task_exists,
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

    profitable = await _get_most_profitable_service_this_week(
        db, week_start_utc, week_end_utc
    )

    return WeeklyInsights(
        week_start=week_start_utc,
        week_end=week_end_utc,
        new_leads_count=new_leads_count,
        responded_in_time_count=responded_in_time_count,
        stuck_count=stuck_count,
        total_open=total_open,
        most_profitable_service=profitable,
    )
