"""
סכמות dashboard — תשובות לכל endpoints מסך הבית.
"""

from datetime import datetime
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
    service_category: str


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

    service_category: str
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


# ===== מסך הבית =====

class HomeDashboardResponse(BaseModel):
    """תמונת מצב מרוכזת — סדר הבלוקים תואם את האפיון."""

    today_actions: list[TodayActionItem]
    new_leads: list[LeadCard]
    pending: list[LeadCard]
    weekly_insights: WeeklyInsights


class PendingResponse(BaseModel):
    items: list[LeadCard]


class ProposalsResponse(BaseModel):
    items: list[ProposalCard]


class TodayResponse(BaseModel):
    items: list[TodayActionItem]
