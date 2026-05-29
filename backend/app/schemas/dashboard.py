"""
סכמות dashboard — תשובות לכל endpoints מסך הבית.
"""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


# ===== כרטיס ליד דחוס לתצוגה ברשימות הדשבורד =====

class LeadCard(BaseModel):
    """ייצוג מצומצם לליד בכרטיס דשבורד — מספיק להחלטה ולכפתור 'מה עכשיו?'."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    full_name: str
    organization_name: str | None
    service_category: str | None  # אופציונלי (F-04)
    service_subtype: str | None
    status: str
    waiting_on: str
    priority_level: str
    preferred_contact: str
    # צבע מצב מחושב: red / orange / green / gray
    state_color: str
    needs_attention: bool
    last_inbound_at: datetime | None
    last_outbound_at: datetime | None
    next_action_due_at: datetime | None
    # האם נכנסה תגובה חדשה לאחרונה (reply boost עדיין פעיל)
    has_recent_reply: bool
    # המקור של ה-boost — מאפשר ל-frontend להבחין בין "בקשת תור חדשה"
    # (meeting_requested) לבין "תגובה חדשה" (inbound_message_logged וכו').
    last_activity_type: str | None
    # ל-badge "גיל" (§12.1) — frontend מחשב last_activity_at→created_at.
    last_activity_at: datetime | None
    created_at: datetime


# ===== Item ב-"פעולות היום" =====

class TodayActionItem(BaseModel):
    """משימה שצריך לבצע היום — task + פרטי הליד שלה."""

    model_config = ConfigDict(from_attributes=True)

    task_id: UUID
    lead_id: UUID
    lead_name: str
    lead_organization: str | None
    task_type: str
    due_at: datetime
    is_overdue: bool
    state_color: str
    priority_level: str
    preferred_contact: str
    service_category: str | None  # אופציונלי לפי Spec §7.1 (F-04)
    # F-20: כפתור פעולה ישיר ב-/today לפי preferred_contact. nullable כי
    # לא כל ליד חייב טלפון/מייל (Spec §7.1 — רק שם+מקור+אחד מהשניים חובה).
    lead_phone: str | None
    lead_email: str | None
    last_outbound_at: datetime | None
    # ל-badge "גיל" (§12.1) — מקור: last_activity_at→created_at של הליד.
    last_activity_at: datetime | None
    created_at: datetime


# ===== הצעות פתוחות =====

class ProposalCard(LeadCard):
    """ליד בסטטוס PROPOSAL_SENT עם חישוב כמה ימים עברו."""

    proposal_sent_at: datetime | None
    days_since_proposal: int | None


# ===== תובנות שבועיות =====

class ProfitableServiceInsight(BaseModel):
    """
    "השעה הרווחית שלך השבוע" — הקטגוריה שהניבה את התעריף השעתי האפקטיבי
    הגבוה ביותר השבוע (לפי עסקאות WON שנסגרו).
    """

    service_category: str | None  # אופציונלי לפי Spec §7.1 (F-04)
    hourly_rate: Decimal
    total_revenue: Decimal
    total_hours: Decimal
    deals_count: int


class WeeklyInsights(BaseModel):
    """3 התובנות מהאפיון: כניסות / מענה בזמן / נתקעו ללא צעד הבא.

    בנוסף: most_profitable_service — אם היו עסקאות WON השבוע עם נתוני
    רווחיות מספיקים (closed_value + actual_hours > 0).
    """

    week_start: datetime
    week_end: datetime
    new_leads_count: int
    responded_in_time_count: int
    stuck_count: int
    total_open: int
    most_profitable_service: ProfitableServiceInsight | None = None


# ===== סיכום יומי (F-07) =====

class DailySummaryRead(BaseModel):
    """ה-row האחרון מ-daily_summaries — מוצג כbubble בדשבורד.
    null אם cron עדיין לא רץ או הטבלה ריקה."""

    model_config = ConfigDict(from_attributes=True)

    summary_date: date
    new_leads_today: int
    tasks_done_today: int
    tasks_for_tomorrow: int
    urgent_open: int
    generated_at: datetime


# ===== מסך הבית =====

class HomeDashboardResponse(BaseModel):
    """תמונת מצב מרוכזת — סדר הבלוקים תואם את האפיון."""

    today_actions: list[TodayActionItem]
    new_leads: list[LeadCard]
    pending: list[LeadCard]
    weekly_insights: WeeklyInsights
    daily_summary: DailySummaryRead | None = None  # F-07: bubble בדשבורד


class PendingResponse(BaseModel):
    items: list[LeadCard]


class ProposalsResponse(BaseModel):
    items: list[ProposalCard]


class TodayResponse(BaseModel):
    items: list[TodayActionItem]


# ===== Polling (auto-refresh) =====

class DashboardPollResponse(BaseModel):
    """Delta מאז `since` שה-client העביר ל-GET /dashboard/poll.

    שתי רשימות נפרדות (לא איחוד) כדי שה-frontend יבחין בין toast של
    "ליד חדש" ל-toast של "תגובה חדשה". `server_time` הוא ה-anchor
    ל-poll הבא (מבדיל clock skew של ה-client).
    """

    new_leads: list[LeadCard]
    leads_with_inbound_replies: list[LeadCard]
    server_time: datetime
