"""
סכמות לדף קביעת תור הציבורי (/book/{token}).
"""

from datetime import date, datetime, timezone
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class UpcomingBooking(BaseModel):
    """פגישה עתידית שכבר קבועה ללקוח — לתצוגה בלבד."""

    start: datetime
    end: datetime
    # approved (הרגיל) / pending_approval (שורות מלפני ביטול שלב האישור)
    status: str


class BookingPageInfo(BaseModel):
    """מידע בסיסי לדף קביעת התור — מוצג ללקוח."""

    lead_name: str
    service_category: str | None  # אופציונלי (F-04)
    service_subtype: str | None
    default_duration_minutes: int
    timezone: str = "Asia/Jerusalem"
    # הפגישות שכבר קבועות ללקוח. עד לשינוי הזה, פגישה קיימת *חסמה* את
    # הדף ולא אפשרה לקבוע מועד נוסף; עכשיו היא מידע בלבד, וה-UI מציג
    # אותה כבאנר מעל בורר המועדים.
    upcoming_bookings: list[UpcomingBooking] = Field(default_factory=list)
    # False כשהלקוח הגיע לתקרת הפגישות — ה-UI מסתיר את הבורר.
    can_book_more: bool = True
    max_bookings: int
    # גבולות בחירת התאריך, מחושבים בשרת לפי שעון ישראל. ה-UI בונה מהם
    # את הגריד במקום לגזור "היום" ו"סוף החודש הבא" משעון המכשיר — מכשיר
    # שמוגדר לטוקיו או עם תאריך שגוי היה מייצר גריד שלא תואם למה שהשרת
    # מוכן לקבל, והלקוח היה נתקל בשגיאה רק אחרי שבחר מועד.
    today: date
    booking_horizon_end: date


class TimeSlot(BaseModel):
    start: datetime
    end: datetime


class DayAvailability(BaseModel):
    date: date
    slots: list[TimeSlot]


class AvailabilityResponse(BaseModel):
    """תוצאת חישוב סלוטים פנויים בטווח תאריכים."""

    days: list[DayAvailability]
    # אם False — סלוטים מבוססים רק על שעות עבודה + DB busy (Google לא מחובר).
    # מודיע ל-UI שייתכן שסלוטים מסוימים יסתרו ביומן של נועה.
    includes_google_busy: bool


class CreateBookingRequest(BaseModel):
    slot_start: datetime
    slot_end: datetime
    # **חובה.** הטלפון שבו נועה תיצור קשר עם הלקוח אם הפגישה מתבטלת או
    # משתנה. מגיע גם לתיאור האירוע ביומן. מאוחסן על הפגישה ולא נוגע
    # ב-`lead.phone` — זה המספר לפגישה הזו, לא עדכון לכרטיס.
    #
    # max_length תואם לעמודה `bookings.contact_phone` (VARCHAR(32)),
    # כדי שקלט ארוך מדי יחזור כשגיאת ולידציה בעברית ולא כ-500 מה-DB.
    contact_phone: str = Field(min_length=1, max_length=32)
    # פרטים אופציונליים שהליד יכול לעדכן בעת הזמנה
    notes: str | None = Field(default=None, max_length=500)

    @field_validator("contact_phone")
    @classmethod
    def validate_contact_phone(cls, v: str) -> str:
        """אותה ולידציה בדיוק כמו בכרטיס הליד.

        הנרמול קורה כאן ולא ב-service, כי `ValueError` מתוך validator
        של Pydantic הופך לתשובת ולידציה עם ההודעה בעברית — בעוד שקריאה
        ישירה ל-`normalize_for_storage` מתוך ה-service הייתה מייצרת 500
        (CLAUDE.md כלל 3).
        """
        from app.utils.phone import normalize_phone_input

        normalized = normalize_phone_input(v)
        if not normalized:
            raise ValueError("יש להזין מספר טלפון.")
        return normalized

    @field_validator("slot_start", "slot_end")
    @classmethod
    def must_be_tz_aware(cls, v: datetime) -> datetime:
        # חובה לכלול timezone offset — אחרת השוואה עם now_utc למטה תיכשל.
        # מנרמלים ל-UTC כדי להבטיח אחידות בכל הקוד.
        if v.tzinfo is None:
            raise ValueError(
                "תאריך/שעה חייבים לכלול אזור זמן (ISO 8601 עם offset)."
            )
        return v.astimezone(timezone.utc)


class CreateBookingResponse(BaseModel):
    booking_id: UUID
    status: str  # "pending_approval"
    slot_start: datetime
    slot_end: datetime

