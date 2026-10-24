"""
ייצוא מרכזי של כל המודלים — חשוב כדי ש-Alembic יזהה אותם דרך Base.metadata.
"""

from app.models.activity import Activity
from app.models.ai_summary import AiSummary
from app.models.booking import Booking
from app.models.daily_summary import DailySummary
from app.models.email_message import EmailMessage
from app.models.followup_rule import FollowupRule
from app.models.gmail_credentials import GmailCredentials
from app.models.google_credentials import GoogleCalendarCredentials
from app.models.lead import Lead
from app.models.program import Program
from app.models.quick_action_chip import QuickActionChip
from app.models.service_rate import ServiceRate
from app.models.task import Task
from app.models.template import Template
from app.models.user import User
from app.models.weekly_open_state_snapshot import WeeklyOpenStateSnapshot

__all__ = [
    "Activity",
    "AiSummary",
    "Booking",
    "DailySummary",
    "EmailMessage",
    "FollowupRule",
    "GmailCredentials",
    "GoogleCalendarCredentials",
    "Lead",
    "Program",
    "QuickActionChip",
    "ServiceRate",
    "Task",
    "Template",
    "User",
    "WeeklyOpenStateSnapshot",
]
