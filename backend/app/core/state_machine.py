"""
State machine ללידים — לפי tech-spec סעיף 5.

עיקרון מרכזי: כל מעבר סטטוס חייב להיות אטומי (כלל 2 ב-CLAUDE.md).
מימוש: UPDATE ... WHERE status IN (allowed_from) + בדיקת rowcount.

הקובץ הזה רק *מגדיר* את חוקי המעבר. הביצוע נעשה ב-services/lead_actions.py.
"""

from dataclasses import dataclass, field

from app.constants import (
    CLOSED_LEAD_STATUSES,
    OPEN_LEAD_STATUSES,
    ActivityType,
    LeadStatus,
)


@dataclass(frozen=True)
class ActionDefinition:
    """הגדרת פעולה דינמית על ליד."""

    # סוג ה-activity שיירשם ב-audit log
    activity_type: ActivityType

    # רשימת סטטוסים שמהם מותר לבצע את הפעולה. None = מכל סטטוס פתוח.
    allowed_from: frozenset[LeadStatus] | None = None

    # סטטוס יעד — אם None, הסטטוס לא משתנה (פרט ל-NEW → IN_PROGRESS אם מסומן)
    transition_to: LeadStatus | None = None

    # האם פעולה outbound (פוגעת ב-NEW לידים): NEW → IN_PROGRESS אוטומטי
    auto_progress_from_new: bool = False

    # שדות מטא-דאטה ב-leads שצריך לעדכן כשהפעולה רצה
    set_last_outbound: bool = False
    set_last_inbound: bool = False
    set_reply_boost: bool = False
    # תאריך שליחת ההצעה — נשמר נפרד מ-last_outbound_at כדי שפולואפ לא יאפס
    # את ספירת הימים בכרטיס "הצעות פתוחות".
    set_proposal_sent_at: bool = False
    # אצל מי הכדור אחרי הפעולה (None = לא משנים)
    set_waiting_on: str | None = None
    # תיוג קצר של סוג הפעולה ב-last_activity_type
    last_activity_tag: str | None = None
    # תיאור קריא בעברית — לשימוש בהודעות שגיאה
    description: str = ""


# ===== מילון הפעולות הנתמכות =====
# המפתח הוא ה-action_type שמגיע ב-URL: POST /leads/{id}/actions/{action_type}

ACTIONS: dict[str, ActionDefinition] = {
    # שליחת תבנית — מסומנת ידנית אחרי שנועה לחצה "שלח" בוואטסאפ
    "mark_template_sent": ActionDefinition(
        activity_type=ActivityType.TEMPLATE_MARKED_SENT,
        allowed_from=frozenset(OPEN_LEAD_STATUSES),
        auto_progress_from_new=True,
        set_last_outbound=True,
        set_waiting_on="CLIENT",
        last_activity_tag="template_sent",
        description="שליחת תבנית",
    ),

    # סיכום שיחה — שיחה הסתיימה
    "log_call_completed": ActionDefinition(
        activity_type=ActivityType.CALL_COMPLETED,
        allowed_from=frozenset(OPEN_LEAD_STATUSES),
        auto_progress_from_new=True,
        set_last_outbound=True,
        last_activity_tag="call_completed",
        description="תיעוד שיחה",
    ),

    # אין מענה — שיחה לא נענתה
    "log_call_no_answer": ActionDefinition(
        activity_type=ActivityType.CALL_NO_ANSWER,
        allowed_from=frozenset(OPEN_LEAD_STATUSES),
        auto_progress_from_new=True,
        set_last_outbound=True,
        last_activity_tag="call_no_answer",
        description="ניסיון טלפוני ללא מענה",
    ),

    # שליחת הצעת מחיר — IN_PROGRESS → PROPOSAL_SENT
    "mark_proposal_sent": ActionDefinition(
        activity_type=ActivityType.PROPOSAL_SENT,
        allowed_from=frozenset(
            {LeadStatus.IN_PROGRESS, LeadStatus.BOOKED, LeadStatus.NEW}
        ),
        transition_to=LeadStatus.PROPOSAL_SENT,
        set_last_outbound=True,
        set_proposal_sent_at=True,
        set_waiting_on="CLIENT",
        last_activity_tag="proposal_sent",
        description="שליחת הצעת מחיר",
    ),

    # בקשת תור (מדף קביעת תורים) — IN_PROGRESS/NEW → BOOKING_PENDING
    "request_meeting": ActionDefinition(
        activity_type=ActivityType.MEETING_REQUESTED,
        allowed_from=frozenset({LeadStatus.NEW, LeadStatus.IN_PROGRESS}),
        transition_to=LeadStatus.BOOKING_PENDING,
        set_last_inbound=True,
        set_reply_boost=True,
        set_waiting_on="NOAH",
        last_activity_tag="meeting_requested",
        description="בקשת תור",
    ),

    # אישור פגישה — BOOKING_PENDING → BOOKED
    "approve_meeting": ActionDefinition(
        activity_type=ActivityType.MEETING_APPROVED,
        allowed_from=frozenset({LeadStatus.BOOKING_PENDING}),
        transition_to=LeadStatus.BOOKED,
        set_waiting_on="CLIENT",
        last_activity_tag="meeting_approved",
        description="אישור פגישה",
    ),

    # דחיית פגישה והחזרה לטיפול — BOOKING_PENDING → IN_PROGRESS
    "reject_meeting": ActionDefinition(
        activity_type=ActivityType.MEETING_REJECTED,
        allowed_from=frozenset({LeadStatus.BOOKING_PENDING}),
        transition_to=LeadStatus.IN_PROGRESS,
        set_waiting_on="CLIENT",
        last_activity_tag="meeting_rejected",
        description="דחיית פגישה",
    ),

    # הערה פנימית — לא משנה סטטוס ולא מעדכן last_*.
    # חשוב לא לדרוס last_activity_type — שמירת הפעולה העסקית האחרונה
    # ("call_completed" / "proposal_sent" וכו') חיונית למיון הדשבורד.
    "add_internal_note": ActionDefinition(
        activity_type=ActivityType.INTERNAL_NOTE_ADDED,
        allowed_from=None,  # מותר מכל סטטוס, כולל סגורים
        description="הוספת הערה פנימית",
    ),

    # רישום הודעה נכנסת — קופץ לראש (reply_boost)
    "log_inbound_message": ActionDefinition(
        activity_type=ActivityType.INBOUND_MESSAGE_LOGGED,
        allowed_from=frozenset(OPEN_LEAD_STATUSES),
        auto_progress_from_new=True,
        set_last_inbound=True,
        set_reply_boost=True,
        set_waiting_on="NOAH",
        last_activity_tag="inbound_message",
        description="הודעה נכנסת מהלקוח",
    ),

    # רישום הודעה יוצאת ידנית (לא דרך תבנית)
    "log_outbound_message": ActionDefinition(
        activity_type=ActivityType.OUTBOUND_MESSAGE_LOGGED,
        allowed_from=frozenset(OPEN_LEAD_STATUSES),
        auto_progress_from_new=True,
        set_last_outbound=True,
        set_waiting_on="CLIENT",
        last_activity_tag="outbound_message",
        description="הודעה יוצאת",
    ),
}


# ===== מעברי סגירה ופתיחה מחדש =====

# ARCHIVED לא מאפשר סגירה חוזרת אליו
CLOSE_ALLOWED_FROM = frozenset(OPEN_LEAD_STATUSES | CLOSED_LEAD_STATUSES) - {
    LeadStatus.ARCHIVED
}

# פתיחה מחדש: WON / LOST → IN_PROGRESS
REOPEN_ALLOWED_FROM = frozenset({LeadStatus.WON, LeadStatus.LOST, LeadStatus.ARCHIVED})
