"""
סכמות לדף קביעת תור הציבורי (/book/{token}).
"""

from datetime import date, datetime, timezone
from typing import Annotated
from uuid import UUID

from pydantic import AfterValidator, BaseModel, Field, field_validator


# ===== טיפוסי שדה משותפים לשני מסלולי הקביעה =====
#
# קישור של ליד וקישור פתוח מקבלים את אותו מועד ואת אותו טלפון, ולכן
# הכללים שלהם כתובים כאן **פעם אחת**, כטיפוס. עותק שני של ולידטור היה
# נסחף בשינוי הראשון, ואז אותו מספר היה מתקבל בדף אחד ונדחה בשני.
#
# `Annotated` + `AfterValidator` ולא מחלקת בסיס עם השדות: ירושה הייתה
# מקבעת את שדות הבסיס *לפני* שדות המחלקה, ומשנה את סדר השדות בקישור
# הפתוח — ואיתו את השגיאה שמוצגת ראשונה (`_humanize_validation_error`
# לוקח את הראשונה). ב-Pydantic 2.10 `field_validator` במצב after הופך
# פנימית בדיוק ל-`AfterValidator`, כך שההתנהגות זהה.
# מקור: pydantic/functional_validators.py, `AfterValidator._from_decorator`.


def _require_aware_utc(v: datetime) -> datetime:
    # חובה לכלול timezone offset — אחרת ההשוואה עם now_utc בשירות
    # תיכשל. מנרמלים ל-UTC כדי להבטיח אחידות בכל הקוד.
    if v.tzinfo is None:
        raise ValueError(
            "תאריך/שעה חייבים לכלול אזור זמן (ISO 8601 עם offset)."
        )
    return v.astimezone(timezone.utc)


def _normalize_contact_phone(v: str) -> str:
    """אותה ולידציה בדיוק כמו בכרטיס הליד.

    הנרמול קורה כאן ולא ב-service, כי `ValueError` מתוך validator של
    Pydantic הופך לתשובת ולידציה עם ההודעה בעברית — בעוד שקריאה ישירה
    ל-`normalize_for_storage` מתוך ה-service הייתה מייצרת 500 (CLAUDE.md
    כלל 3).
    """
    from app.utils.phone import normalize_phone_input

    normalized = normalize_phone_input(v)
    if not normalized:
        raise ValueError("יש להזין מספר טלפון.")
    return normalized


SlotTime = Annotated[datetime, AfterValidator(_require_aware_utc)]

# **חובה.** הטלפון שבו נועה תיצור קשר עם הלקוח אם הפגישה מתבטלת או
# משתנה, והוא מגיע גם לתיאור האירוע ביומן. מאוחסן על הפגישה ולא נוגע
# ב-`lead.phone` — זה המספר לפגישה הזו, לא עדכון לכרטיס.
#
# max_length תואם לעמודה `bookings.contact_phone` (VARCHAR(32)), כדי
# שקלט ארוך מדי יחזור כשגיאת ולידציה בעברית ולא כ-500 מה-DB.
ContactPhone = Annotated[
    str,
    Field(min_length=1, max_length=32),
    AfterValidator(_normalize_contact_phone),
]


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
    slot_start: SlotTime
    slot_end: SlotTime
    contact_phone: ContactPhone
    # פרטים אופציונליים שהליד יכול לעדכן בעת הזמנה
    notes: str | None = Field(default=None, max_length=500)

    @field_validator("notes")
    @classmethod
    def normalize_notes(cls, v: str | None) -> str | None:
        """הערה של רווחים בלבד היא הערה ריקה — וצריך שהיא תהיה `None`.

        הנרמול חייב לקרות **כאן**, בגבול, ולא אצל כל צרכן בנפרד:
        מחרוזת של רווחים היא truthy גם ב-Python וגם ב-JS, ולכן בלי
        השורה הזו היא עוברת את כל שלוש הבדיקות שבהמשך המסלול —
        `if booking.notes:` ב-`build_event_description`, ו-
        `{booking.notes && ...}` ב-`BookingCard.tsx` — ומייצרת שורת
        "הערה מהלקוח:" בלי שום דבר אחריה ביומן של נועה, ובלוק הערה
        ריק בכרטיס הליד. ה-`strip` שכבר קיים ב-`_sanitize_for_event`
        רץ *אחרי* ההחלטה ולכן לא עוזר.
        """
        if v is None:
            return None
        stripped = v.strip()
        return stripped or None


class CreateBookingResponse(BaseModel):
    booking_id: UUID
    status: str  # "pending_approval"
    slot_start: datetime
    slot_end: datetime


# ===== קישור פתוח — קביעה בלי ליד =====


class OpenBookingPageInfo(BaseModel):
    """מה שהדף הפתוח צריך לפני שהוא טוען זמינות.

    הגבולות מחושבים בשרת בשעון ישראל מאותה סיבה בדיוק כמו ב-
    `BookingPageInfo`: מכשיר שמוגדר לאזור זמן אחר, או עם תאריך שגוי,
    היה בונה גריד שהשרת לא מוכן לקבל. אין כאן שם, קטגוריה או פגישות
    קיימות — אין ליד שממנו הם היו נלקחים.
    """

    default_duration_minutes: int
    timezone: str = "Asia/Jerusalem"
    today: date
    booking_horizon_end: date


class CreateOpenBookingRequest(BaseModel):
    """בקשה מהקישור הפתוח. אין token ואין ליד — רק מה שהלקוח מילא."""

    slot_start: SlotTime
    slot_end: SlotTime

    # **חובה.** בזרימת הליד השם מגיע מכרטיס הליד; כאן אין כרטיס, ולכן
    # בלי השדה הזה נועה מקבלת ביומן פגישה בלי לדעת עם מי.
    #
    # 200 אינו מספר עגול שנבחר: זו המידה שכבר קבועה ב-`leads.full_name`
    # וב-`LeadCreate`, כלומר התשובה הקיימת של המערכת לשאלה "כמה ארוך
    # שם". השדה **נדחה** ולא נחתך — חיתוך שקט היה שולח ליומן שם אחר
    # מזה שהלקוח הקליד, ולנועה אין דרך לדעת שזה קרה.
    full_name: str = Field(min_length=1, max_length=200)

    # אותו טיפוס בדיוק כמו בקישור של הליד — ראה `ContactPhone` למעלה.
    contact_phone: ContactPhone

    @field_validator("full_name")
    @classmethod
    def normalize_full_name(cls, v: str) -> str:
        """שם של רווחים בלבד הוא שם ריק.

        בלי זה `"   "` עובר את `min_length=1` (הוא באורך 3), נשמר,
        ומגיע לכותרת האירוע ביומן כ-"פגישה — ". אותו דפוס בדיוק של
        ההערה הריקה: ההחלטה נבדקת על הערך הגולמי בזמן שהניקוי קורה
        אחריה.
        """
        stripped = v.strip()
        if not stripped:
            raise ValueError("יש להזין שם.")
        return stripped


class OpenBookingResponse(BaseModel):
    """תשובה ללקוח. **בלי `booking_id`** — אין לו מה לעשות איתו.

    השורה ב-DB קיימת רק כדי לשריין את המועד, ואינה ישות שהלקוח מנהל:
    אין לו דף, אין לו ביטול עצמי, ואין מסך שמציג אותה. חשיפת המזהה
    הייתה מרמזת על ממשק שלא קיים.
    """

    slot_start: datetime
    slot_end: datetime
