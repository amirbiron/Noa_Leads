"""
קבועים מרכזיים — Enums המתאימים לסכמת ה-DB.
מקור: tech-spec.md סעיף 4.2.
"""

from enum import StrEnum


# ===== סטטוס ליד =====
class LeadStatus(StrEnum):
    NEW = "NEW"
    IN_PROGRESS = "IN_PROGRESS"
    PROPOSAL_SENT = "PROPOSAL_SENT"
    BOOKING_PENDING = "BOOKING_PENDING"
    BOOKED = "BOOKED"
    WON = "WON"
    LOST = "LOST"
    ARCHIVED = "ARCHIVED"


OPEN_LEAD_STATUSES = {
    LeadStatus.NEW,
    LeadStatus.IN_PROGRESS,
    LeadStatus.PROPOSAL_SENT,
    LeadStatus.BOOKING_PENDING,
    LeadStatus.BOOKED,
}

CLOSED_LEAD_STATUSES = {
    LeadStatus.WON,
    LeadStatus.LOST,
    LeadStatus.ARCHIVED,
}


# ===== "אצל מי הכדור" =====
class WaitingOn(StrEnum):
    NOAH = "NOAH"            # אצל נועה (הבעלים)
    CLIENT = "CLIENT"        # אצל הלקוח
    ASSISTANT = "ASSISTANT"  # אצל העוזרת
    SYSTEM = "SYSTEM"        # ממתין לפעולה אוטומטית
    NONE = "NONE"            # סגור / לא רלוונטי


# ===== קטגוריות שירות וסאב-טייפים =====
class ServiceCategory(StrEnum):
    CLINIC = "clinic"
    WORKSHOPS = "workshops"
    PRODUCTION = "production"
    DIGITAL_COURSE = "digital_course"


# מיפוי קטגוריה → סאב-טייפים מורשים (לשימוש ולידציה בשירותים)
SERVICE_SUBTYPES: dict[ServiceCategory, list[str]] = {
    ServiceCategory.CLINIC: [
        "voice_development",   # פיתוח קול
        "public_speaking",     # עמידה מול קהל
        "voice_rehab",         # שיקום קול
    ],
    ServiceCategory.WORKSHOPS: [
        "workshop_speaking",   # סדנת דיבור/הופעה/שפת גוף
        "stage_arts",          # אומניות הבמה
        "lecture_organization",  # הרצאה לארגון
        "lecture_academic",    # הרצאה אקדמית
    ],
    ServiceCategory.PRODUCTION: [
        "production_guidance",  # ליווי הפקה אישית
        "production_directing",  # בימוי הפקה
    ],
    ServiceCategory.DIGITAL_COURSE: [
        "digital_course",
    ],
}


# ===== עדיפות =====
class PriorityLevel(StrEnum):
    NORMAL = "normal"
    HOT = "hot"
    VIP = "vip"


# ===== ערוץ תקשורת מועדף =====
class PreferredContact(StrEnum):
    PHONE = "phone"
    WHATSAPP = "whatsapp"
    EMAIL = "email"


# ===== מקור פנייה =====
class SourceChannel(StrEnum):
    FORM = "form"
    EMAIL = "email"
    MANUAL = "manual"
    REFERRAL = "referral"
    FACEBOOK = "facebook"
    INSTAGRAM = "instagram"
    WHATSAPP = "whatsapp"
    OTHER = "other"


# ===== סיבות סגירה (LOST) =====
class ClosureReason(StrEnum):
    NO_RESPONSE = "no_response"
    NOT_RELEVANT = "not_relevant"
    PRICE = "price"
    TIMING = "timing"
    WENT_WITH_OTHER = "went_with_other"
    DUPLICATE = "duplicate"
    OTHER = "other"


# ===== סוגי activities (audit log) =====
class ActivityType(StrEnum):
    LEAD_CREATED = "lead_created"
    LEAD_UPDATED = "lead_updated"
    TEMPLATE_MARKED_SENT = "template_marked_sent"
    MANUAL_MESSAGE_LOGGED = "manual_message_logged"
    CALL_COMPLETED = "call_completed"
    CALL_NO_ANSWER = "call_no_answer"
    MEETING_REQUESTED = "meeting_requested"
    MEETING_APPROVED = "meeting_approved"
    MEETING_REJECTED = "meeting_rejected"
    MEETING_RESCHEDULED = "meeting_rescheduled"
    MEETING_CANCELED = "meeting_canceled"
    PROPOSAL_SENT = "proposal_sent"
    FOLLOWUP_SCHEDULED = "followup_scheduled"
    OWNER_CHANGED = "owner_changed"
    INTERNAL_NOTE_ADDED = "internal_note_added"
    STATUS_CHANGED = "status_changed"
    LEAD_WON = "lead_won"
    LEAD_LOST = "lead_lost"
    LEAD_ARCHIVED = "lead_archived"
    LEAD_REOPENED = "lead_reopened"
    INBOUND_MESSAGE_LOGGED = "inbound_message_logged"
    OUTBOUND_MESSAGE_LOGGED = "outbound_message_logged"
    # === Chips (Spec v2.1 §16.4) ===
    CHIP_APPLIED = "chip_applied"
    # === Programs (תוכניות מתמשכות) ===
    PROGRAM_CREATED = "program_created"
    PROGRAM_SESSION_DONE = "program_session_done"
    PROGRAM_COMPLETED = "program_completed"
    PROGRAM_CANCELED = "program_canceled"


# ===== סוגי משימות (tasks) =====
class TaskType(StrEnum):
    # 5 כללי הפולואפ של §17.1 + §27.6
    FIRST_RESPONSE = "first_response"            # ליד חדש שלא טופל — 24h
    WARM_FOLLOWUP = "warm_followup"              # לקוח חם שלא סגר — 48h (§17.1)
    PROPOSAL_FOLLOWUP = "proposal_followup"      # פולואפ אחרי הצעת מחיר — 3 ימי עסקים
    DORMANT_CHECK = "dormant_check"              # ליד שלא חזר — 60d (§17.1; היה dormant_reachout)
    LECTURE_INQUIRY = "lecture_inquiry"          # ארגון התעניין בהרצאה — 24h (§17.1)

    # סוגים נוספים שמופיעים ב-§16.4 (chips) ובגזירות מערכת
    FOLLOWUP = "followup"                        # פולואפ כללי (chip "רוצה פרטים"/"מעוניין בשיחה"/"לחזור בעוד חודש")
    RETRY_CALL = "retry_call"                    # ניסיון שיחה חוזר אחרי אין מענה (chip "אין מענה")
    SEND_PROPOSAL = "send_proposal"              # יש לשלוח הצעת מחיר ללקוח (chip "רוצה הצעה")
    POST_MEETING_UPDATE = "post_meeting_update"  # עדכון אחרי פגישה
    PROGRAM_END = "program_end"                  # סיום תוכנית מתמשכת
    AFTER_HOURS_REPLY = "after_hours_reply"      # החזרה אחרי שעות עבודה


class TaskStatus(StrEnum):
    OPEN = "open"
    DONE = "done"
    CANCELED = "canceled"
    SNOOZED = "snoozed"


# ===== תפקידי משתמש =====
class UserRole(StrEnum):
    OWNER = "owner"          # נועה
    ASSISTANT = "assistant"  # עוזרת


# ===== ערוצי תבניות =====
class TemplateChannel(StrEnum):
    WHATSAPP = "whatsapp"
    EMAIL = "email"


# ===== קהל יעד לתבניות =====
class TemplateTargetAudience(StrEnum):
    PRIVATE = "private"            # ליד פרטי
    ORGANIZATION = "organization"  # ארגון
    DORMANT = "dormant"            # ליד רדום


# ===== סטטוס bookings =====
class BookingStatus(StrEnum):
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELED = "canceled"


# ===== סטטוס תוכנית מתמשכת =====
class ProgramStatus(StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELED = "canceled"


# ===== סוגי תוכניות מתמשכות (לפי האפיון) =====
class ProgramType(StrEnum):
    VOICE_REHAB_8 = "voice_rehab_8"            # שיקום קול - 8 מפגשים
    PUBLIC_SPEAKING_8 = "public_speaking_8"    # עמידה מול קהל - 8 מפגשים
    STAGE_ARTS_4 = "stage_arts_4"              # אומניות הבמה - 3-4 מפגשים
    PRODUCTION_3MONTHS = "production_3months"  # ליווי הפקה - 3-4 חודשים
    DIGITAL_COURSE_12 = "digital_course_12"    # קורס דיגיטלי - 12 מפגשים


# ===== כללי פולואפ =====
# לפי האפיון יב סעיף 482, ה-spec מגדיר 5 סוגי פולואפ. כרגע 2 בשימוש
# (FIRST_RESPONSE, PROPOSAL_ORG). ה-3 הנוספים (WARM, DORMANT,
# LECTURE_INQUIRY) יוגדרו כשנשתמש בהם בפועל — כדי לא להחזיק קבועים
# לא-בשימוש שמתבדרים מהspec.
#
# הקבועים האלה משמשים ביצירת tasks (ל-due_at), לא בdisplay layer.
# ה-spec הספציפי שמור ב-docs/product-spec.md לחיפוש עתידי.

from datetime import timedelta as _timedelta

FOLLOWUP_GRACE_FIRST_RESPONSE = _timedelta(hours=24)
FOLLOWUP_GRACE_PROPOSAL_ORG = _timedelta(days=4)  # 3-5 ימי עסקים
