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
from app.services.tasks import surfaceable_task_condition
from app.schemas.dashboard import (
    LeadCard,
    ProfitableServiceInsight,
    ProposalCard,
    TodayActionItem,
    WeeklyInsights,
)
from app.utils.work_hours import ISRAEL_TZ, to_israel_tz

# ===== קבועי תצוגה =====
# 5-7 פעולות היום לפי האפיון. נשמור up to 20 כדי לא לחתוך אם יש עומס
TODAY_ACTIONS_LIMIT = 20
DEFAULT_DASHBOARD_LIMIT = 50

# הערה על overdue: בעבר היה כאן _OVERDUE_GRACE dict שחישב alert מ-
# created_at + grace per-type. זה יצר בעיות:
# - PROPOSAL_FOLLOWUP שנוצר באיחור ע"י check_stuck_proposals קיבל
#   clock-reset (4 ימים מ-task.created_at במקום מ-proposal_sent).
# - snooze לא השפיע על הצביעה (created_at לא משתנה).
# - דורש CASE מורכב ב-SQL.
#
# המודל החדש: כל task נוצר עם due_at = alert time. is_overdue פשוט
# due_at <= now. ה-grace הספציפי per-type מקודד ב-due_at של ה-task
# בעת יצירתו (FIRST_RESPONSE = now+24h, PROPOSAL_FOLLOWUP = next
# workday כשcheck_stuck_proposals מאתר 3+ ימים מ-proposal_sent, וכו').


# ===================== חישוב צבע מצב =====================

def derive_state_color(lead: Lead, now_utc: datetime) -> str:
    """
    מחשב את צבע המצב של ליד — לוגיקה פשוטה (Spec §12.9):

    - gray: סטטוס סופי (WON/LOST/ARCHIVED).
    - orange: יש task שעבר את ה-due_at שלו
      (lead.next_action_due_at <= now).
    - green: ברירת מחדל — אין task overdue, או אין task בכלל.

    אדום שמור לתרחישים קריטיים עתידיים (פגישה מאושרת תוך שעה ולא
    אושרה וכו'). שום branch כאן לא מחזיר "red" כעת. ה-StateColor type
    מאפשר את הערך לתאימות עתידית — כשהתרחיש יוגדר, יתווסף branch.

    real-time check על due_at (לא מסתמך על lead.needs_attention שמתעדכן
    ע"י cron mark_overdue כל 15 דק' — היה latency של עד 15 דק' מהפיכה
    ל-overdue ועד הצבעה). הטור `needs_attention` נשאר ב-DB למקרים אחרים
    (filters עתידיים), אבל הצבע לא תלוי בו.

    הוסר ORANGE_LOOKAHEAD (48h "פולואפ קרוב") — יצר false-positives
    (ליד עם 7 שעות עד due_at הופיע כתום ללא טעם). פולואפ הוא תזכורת,
    לא דדליין — סימן ויזואלי רק כשעבר.
    """
    if lead.status in CLOSED_LEAD_STATUSES:
        return "gray"
    if lead.next_action_due_at is not None and lead.next_action_due_at <= now_utc:
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
        last_activity_type=lead.last_activity_type,
        last_activity_at=lead.last_activity_at,
        created_at=lead.created_at,
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
    משימות פתוחות + snoozed שעבר מועדן, שה-due_at שלהן בחלון (now-7d, סוף-היום
    בישראל). כולל overdue קצר (משימות מאתמול). משימות תקועות 7+ ימים *מוחרגות*
    כאן ומוצגות ב"ממתין לטיפול" (get_pending) — אקסקלוסיביות לפי §16.2.
    """
    now_utc = datetime.now(timezone.utc)
    end_today_exclusive = _start_of_tomorrow_israel(now_utc)
    # אותו סף כמו list_stuck_tasks ו-get_pending — אין drift (כלל 10).
    stuck_threshold = now_utc - timedelta(days=7)
    closed = [s.value for s in CLOSED_LEAD_STATUSES]

    # is_overdue — פשוט: due_at <= now. snooze מעדכן due_at ישירות
    # אז גם snoozed-expired נתפס. אין יותר grace per-type — המידע מקודד
    # ב-due_at בעת יצירת ה-task.
    is_overdue_expr = Task.due_at <= now_utc

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
            # guard §16.2: task תקוע 7+ ימים שייך ל"ממתין לטיפול", לא ל"היום".
            Task.due_at > stuck_threshold,
            # סינון לידים סגורים — defense in depth. close_lead מבטל
            # tasks פתוחים שלהם, אבל אם משהו פספס (race / cron) זה תופס.
            Lead.status.notin_(closed),
            # §19 D.1: dormant_suggestion פסיבי (archive/no_action) לא מוקפץ
            # ל-/today — נשמר בכרטיס בלבד.
            surfaceable_task_condition(),
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
        meta = task.task_metadata or {}
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
                lead_phone=lead.phone,
                lead_email=lead.email,
                last_outbound_at=lead.last_outbound_at,
                last_activity_at=lead.last_activity_at,
                created_at=lead.created_at,
                # §19 D.1 — רלוונטי רק ל-dormant_suggestion (אקטיבי, כי פסיבי
                # סונן למעלה). None לשאר.
                ai_action=meta.get("ai_action"),
                ai_reasoning=meta.get("ai_reasoning"),
            )
        )
    return items


def _calc_is_overdue(task, now_utc: datetime) -> bool:
    """is_overdue פשוט — due_at <= now. snooze מעדכן due_at אז גם snoozed-
    expired נתפס נכון. ה-grace per-type מקודד ב-due_at של ה-task בעת
    יצירתו (FIRST_RESPONSE = now+24h, PROPOSAL_FOLLOWUP = next workday
    כשcheck_stuck_proposals זיהה stale הצעה, וכו')."""
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


# ===================== Polling (auto-refresh) =====================

# cap על תוצאות poll להגנה מ-spike נדיר (Bulk import וכו'). לרוב 0-3
# שינויים ב-poll, ה-limit לא מופעל בפועל.
_POLL_DELTA_LIMIT = 20


async def poll_dashboard_delta(
    db: AsyncSession, *, since: datetime
) -> tuple[list[LeadCard], list[LeadCard], datetime]:
    """Delta מאז `since`: לידים חדשים + לידים שקיבלו תגובה. מחזיר גם
    את ה-server_time anchor ל-poll הבא.

    שני queries נפרדים:
    - new_leads: `created_at > since`.
    - replies: `last_inbound_at > since` AND `last_inbound_at > created_at`
      (התנאי השני מונע כפילות — ליד שהומר ממייל נכנס יופיע ב-new,
      לא ב-replies). סינון לסגורים — אין טעם להציג toast על תגובה
      לליד WON/LOST/ARCHIVED.

    **server_time anchor — תיקון bugbot:** captured *לפני* הqueries,
    לא אחרי. אם נחזיר datetime.now() אחרי הqueries, rows שעמדו ב-commit
    במהלך חלון הqueries יהיו עם created_at < הערך המוחזר, אבל
    uncommitted בתחילת הquery → לא ב-result set. ה-client היה משדר
    since=server_time בפול הבא ומפספס אותם. capture לפני = anchor
    מוקדם מספיק שכל commit שיקרה במהלך הqueries יקבל created_at >
    anchor → poll הבא יתפוס. trade-off: edge case של duplicate
    בpoll הבא (overlap window ~ms), זניח.

    **sequential ולא asyncio.gather — תיקון bugbot:** AsyncSession של
    SQLAlchemy לא בטוח ל-overlapping operations על אותו connection.
    asyncio.gather גרם ל-asyncpg "another operation is in progress"
    אקראית. ההפרש ~10-30ms ל-poll — זניח לחווית UI.
    """
    server_time = datetime.now(timezone.utc)

    new_q = (
        select(Lead)
        .where(Lead.created_at > since)
        .order_by(Lead.created_at.desc())
        .limit(_POLL_DELTA_LIMIT)
    )
    replies_q = (
        select(Lead)
        .where(
            Lead.last_inbound_at > since,
            Lead.last_inbound_at > Lead.created_at,
            ~Lead.status.in_(CLOSED_LEAD_STATUSES),
        )
        .order_by(Lead.last_inbound_at.desc())
        .limit(_POLL_DELTA_LIMIT)
    )
    new_res = await db.execute(new_q)
    replies_res = await db.execute(replies_q)

    new_cards = [_lead_to_card(l, server_time) for l in new_res.scalars().all()]
    reply_cards = [
        _lead_to_card(l, server_time) for l in replies_res.scalars().all()
    ]
    return new_cards, reply_cards, server_time


# ===================== ממתין לטיפול =====================

async def get_pending(
    db: AsyncSession, *, limit: int = DEFAULT_DASHBOARD_LIMIT
) -> list[LeadCard]:
    """
    "ממתין לטיפול" — לידים פתוחים שדורשים פעולה (§16.2):
    - תקועים 7+ ימים (task פתוח/snoozed עם due_at <= now-7d) — לא overdue זמני,
    - או בקשת תור שמחכה לאישור (BOOKING_PENDING — F-06): אחרי שהסרנו את
      ה-Telegram על בקשת תור (לפי Spec §16.3), הדשבורד הוא הערוץ היחיד
      שבו נועה רואה את הבקשה. כל ליד ב-BOOKING_PENDING ממתין לפעולה שלה.

    אקסקלוסיבי מ"משימות היום" (get_today_actions): overdue קצר (<7 ימים) מוצג
    שם בלבד; 7+ ימים כאן בלבד. needs_attention נשאר דגל תצוגה (צבע כתום §12.9)
    אבל אינו תנאי סינון כאן — הוא מסומן לכל overdue ולכן היה משחזר את החפיפה.
    """
    now_utc = datetime.now(timezone.utc)
    # אותו סף כמו list_stuck_tasks ו-get_today_actions — אין drift (כלל 10).
    stuck_threshold = now_utc - timedelta(days=7)
    stuck_task_exists = (
        select(Task.id)
        .where(
            Task.lead_id == Lead.id,
            Task.status.in_(
                [TaskStatus.OPEN.value, TaskStatus.SNOOZED.value]
            ),
            Task.due_at <= stuck_threshold,
            # §19 D.1: ליד שמומלץ לארכב/no_action לא נחשב "תקוע" — לא מוקפץ.
            surfaceable_task_condition(),
        )
        .correlate(Lead)
        .exists()
    )
    stmt = (
        select(Lead)
        .where(
            Lead.status.notin_([s.value for s in CLOSED_LEAD_STATUSES]),
            or_(
                stuck_task_exists,
                Lead.status == LeadStatus.BOOKING_PENDING.value,
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

    # "לא טופלו בזמן": ליד פתוח עם task פעיל שעבר ה-due_at שלו.
    # ה-grace per-type מקודד ב-due_at של ה-task בעת יצירתו, אז
    # is_overdue פשוט = due_at <= now. ראה הערה למעלה (אחרי TODAY_ACTIONS_LIMIT).
    #
    # ליד חדש שזה עתה נוצר *לא* נספר כי FIRST_RESPONSE due_at=+24h.
    # ליד פתוח בלי tasks פעילים *לא* נספר (לפי תכנון).
    # snooze מעדכן due_at — מטופל אוטומטית.
    overdue_task_exists = (
        select(Task.id)
        .where(
            Task.lead_id == Lead.id,
            Task.status.in_(
                [TaskStatus.OPEN.value, TaskStatus.SNOOZED.value]
            ),
            Task.due_at <= now_utc,
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


async def get_latest_daily_summary(db: AsyncSession):
    """
    מחזיר את ה-DailySummary העדכני ביותר (לפי summary_date desc), או None
    אם הטבלה ריקה. F-07: מוצג כ-bubble בדשבורד.

    אין סינון לפי "סיכום של היום" — אם cron של 19:00 עוד לא רץ היום,
    מציגים את של אתמול. הfrontend מציג generated_at כדי שנועה תדע מתי.
    """
    from app.models.daily_summary import DailySummary

    result = await db.execute(
        select(DailySummary).order_by(DailySummary.summary_date.desc()).limit(1)
    )
    return result.scalar_one_or_none()
