"""
ייצוא מרכזי של כל המודלים — חשוב כדי ש-Alembic יזהה אותם דרך Base.metadata.
"""

from app.models.activity import Activity
from app.models.booking import Booking
from app.models.daily_summary import DailySummary
from app.models.google_credentials import GoogleCalendarCredentials
from app.models.lead import Lead
from app.models.program import Program
from app.models.quick_action_chip import QuickActionChip
from app.models.service_rate import ServiceRate
from app.models.task import Task
from app.models.template import Template
from app.models.user import User

__all__ = [
    "Activity",
    "Booking",
    "DailySummary",
    "GoogleCalendarCredentials",
    "Lead",
    "Program",
    "QuickActionChip",
    "ServiceRate",
    "Task",
    "Template",
    "User",
]
