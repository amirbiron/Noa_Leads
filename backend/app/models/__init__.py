"""
ייצוא מרכזי של כל המודלים — חשוב כדי ש-Alembic יזהה אותם דרך Base.metadata.
"""

from app.models.activity import Activity
from app.models.booking import Booking
from app.models.lead import Lead
from app.models.program import Program
from app.models.task import Task
from app.models.template import Template
from app.models.user import User

__all__ = [
    "Activity",
    "Booking",
    "Lead",
    "Program",
    "Task",
    "Template",
    "User",
]
