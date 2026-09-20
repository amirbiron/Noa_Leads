"""
בדיקות לפונקציות הטהורות של זרימת הפגישה.

הפונקציות כאן חולצו במכוון מתוך קוד שמדבר עם Google, כדי שהחלקים
שאפשר לבדוק בלי חשבון חי — ייבדקו. מה שנשאר תלוי ב-Google (יצירת
האירוע בפועל, `calendarList.list`, watch channel) לא נבדק כאן ומסומן
כך במפורש בדוח.

אין צורך ב-DB: כל מה שכאן עובד על אובייקטים בזיכרון.
"""

from datetime import datetime, timedelta, timezone

import pytest


def _lead(**kwargs):
    from app.models.lead import Lead

    defaults = dict(
        full_name="דנה כהן",
        service_subtype=None,
        organization_name=None,
        phone=None,
        email=None,
    )
    defaults.update(kwargs)
    return Lead(**defaults)


def _booking(**kwargs):
    from app.models.booking import Booking

    now = datetime.now(timezone.utc)
    defaults = dict(
        requested_slot_start=now,
        requested_slot_end=now + timedelta(hours=1),
        contact_phone=None,
        notes=None,
    )
    defaults.update(kwargs)
    return Booking(**defaults)


# ===================== תיאור האירוע ביומן =====================


def test_description_includes_phone_and_note():
    """הבאג שדווח: ההערה של הלקוח לא הגיעה ליומן.

    עד לתיקון, `notes` נשמר רק ביומן הפעילות של הליד — לא בטבלת
    הפגישות ולא בתיאור האירוע.
    """
    from app.services.booking import build_event_description

    desc = build_event_description(
        _lead(),
        _booking(contact_phone="052-1234567", notes="אגיע עם בן זוג"),
    )
    assert "052-1234567" in desc
    assert "אגיע עם בן זוג" in desc
    assert "הערה מהלקוח" in desc


def test_description_prefers_the_phone_from_the_booking():
    """הטלפון שהלקוח הזין לפגישה גובר על זה שבכרטיס הליד.

    זו כל הנקודה בשדה החדש: המספר שהוא השאיר *עכשיו* הוא זה שנועה
    צריכה כדי להשיג אותו לגבי הפגישה הזו.
    """
    from app.services.booking import build_event_description

    desc = build_event_description(
        _lead(phone="03-1111111"),
        _booking(contact_phone="052-1234567"),
    )
    assert "052-1234567" in desc
    assert "03-1111111" not in desc


def test_description_falls_back_to_lead_phone_for_old_bookings():
    """פגישות שנוצרו לפני שהשדה היה קיים עדיין מציגות טלפון."""
    from app.services.booking import build_event_description

    desc = build_event_description(
        _lead(phone="03-1111111"), _booking(contact_phone=None)
    )
    assert "03-1111111" in desc


def test_description_escapes_html_from_the_client():
    """טקסט חופשי מ-endpoint ציבורי עובר escape לפני היומן.

    `description` של אירוע ב-Google Calendar מרונדר כ-HTML חלקי, ולכן
    הוא output עם סינטקס פעיל (CLAUDE.md כלל 6). בלי escape, הערה עם
    תגית הייתה משנה את מראה האירוע ביומן של נועה.
    """
    from app.services.booking import build_event_description

    desc = build_event_description(
        _lead(),
        _booking(
            contact_phone="052-1234567",
            notes='<b>דחוף</b> <a href="http://evil">לחצי כאן</a> & עוד',
        ),
    )
    assert "<b>" not in desc
    assert "<a href" not in desc
    assert "&lt;b&gt;" in desc
    assert "&amp;" in desc


def test_description_strips_control_characters():
    """תווי בקרה מוסרים — הם בלתי נראים ומבלבלים לקוחות יומן."""
    from app.services.booking import build_event_description

    desc = build_event_description(
        _lead(), _booking(notes="שלום\x00\x07עולם")
    )
    assert "\x00" not in desc
    assert "\x07" not in desc
    assert "שלוםעולם" in desc


def test_description_truncates_a_very_long_note():
    from app.services.booking import build_event_description

    desc = build_event_description(_lead(), _booking(notes="א" * 5000))
    assert len(desc) < 1000
    assert desc.endswith("…")


def test_description_omits_empty_fields():
    """ליד בלי ארגון/מייל/סוג שירות לא מקבל שורות ריקות."""
    from app.services.booking import build_event_description

    desc = build_event_description(_lead(), _booking())
    assert desc == ""


# ===================== ניתוח תשובת FreeBusy =====================


def test_freebusy_merges_ranges_from_all_calendars():
    """הבאג שדווח: היומן השני לא נספר.

    הגרסה הקודמת חיפשה את המפתח `"primary"` בלבד בתשובה, ולכן שעה
    תפוסה ביומן המשני נראתה פנויה ללקוח.
    """
    from app.services.booking import _parse_freebusy_response

    result = {
        "calendars": {
            "primary": {
                "busy": [
                    {
                        "start": "2026-10-01T09:00:00Z",
                        "end": "2026-10-01T10:00:00Z",
                    }
                ]
            },
            "second@group.calendar.google.com": {
                "busy": [
                    {
                        "start": "2026-10-01T14:00:00Z",
                        "end": "2026-10-01T15:00:00Z",
                    }
                ]
            },
        }
    }
    busy = _parse_freebusy_response(
        result, ["primary", "second@group.calendar.google.com"]
    )
    assert len(busy) == 2
    assert {s.hour for s, _ in busy} == {9, 14}


def test_freebusy_normalizes_offsets_to_utc():
    from app.services.booking import _parse_freebusy_response

    busy = _parse_freebusy_response(
        {
            "calendars": {
                "primary": {
                    "busy": [
                        {
                            "start": "2026-10-01T09:00:00+03:00",
                            "end": "2026-10-01T10:00:00+03:00",
                        }
                    ]
                }
            }
        },
        ["primary"],
    )
    assert busy[0][0] == datetime(2026, 10, 1, 6, 0, tzinfo=timezone.utc)


def test_freebusy_errors_block_the_page():
    """יומן שנכשל = fail-safe, לא "פנוי".

    Google מחזיר 200 גם כשחישוב ליומן מסוים נכשל (נמחק, הרשאה נשללה),
    והשדה `busy` פשוט חוזר ריק. בלי הבדיקה הזו יומן שבור נראה בדיוק
    כמו יומן פנוי — וזה בדיוק הבאג שבגללו נבנתה התמיכה ביומן שני.
    """
    from app.services.booking import (
        CalendarTemporarilyUnavailable,
        _parse_freebusy_response,
    )

    with pytest.raises(CalendarTemporarilyUnavailable):
        _parse_freebusy_response(
            {
                "calendars": {
                    "primary": {"busy": []},
                    "gone@group.calendar.google.com": {
                        "errors": [{"domain": "global", "reason": "notFound"}]
                    },
                }
            },
            ["primary", "gone@group.calendar.google.com"],
        )


def test_freebusy_missing_calendar_blocks_the_page():
    """יומן שנשאל ולא חזר בתשובה — לא מניחים שהוא פנוי."""
    from app.services.booking import (
        CalendarTemporarilyUnavailable,
        _parse_freebusy_response,
    )

    with pytest.raises(CalendarTemporarilyUnavailable):
        _parse_freebusy_response(
            {"calendars": {"primary": {"busy": []}}},
            ["primary", "missing@group.calendar.google.com"],
        )


# ===================== בחירת היומנים =====================


def test_target_calendar_is_always_counted_as_busy():
    """היומן שאליו נכתבות הפגישות תמיד נחשב תפוס, בלי כפילויות."""
    from app.models.google_credentials import GoogleCalendarCredentials
    from app.services.google_calendar import busy_calendar_ids

    row = GoogleCalendarCredentials(
        calendar_id="work@example.com",
        # מישהו הוסיף את היעד גם לרשימת הנוספים — לא אמור להיכפל.
        busy_calendar_ids=["work@example.com", "personal@example.com"],
    )
    assert busy_calendar_ids(row) == [
        "work@example.com",
        "personal@example.com",
    ]


def test_target_calendar_defaults_to_primary():
    """שורה ישנה בלי בחירה מפורשת ממשיכה לעבוד."""
    from app.models.google_credentials import GoogleCalendarCredentials
    from app.services.google_calendar import (
        busy_calendar_ids,
        target_calendar_id,
    )

    row = GoogleCalendarCredentials(calendar_id="primary", busy_calendar_ids=[])
    assert target_calendar_id(row) == "primary"
    assert busy_calendar_ids(row) == ["primary"]


# ===================== ולידציית טלפון =====================


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("0521234567", "052-1234567"),
        ("052-123-4567", "052-1234567"),
        ("+972521234567", "052-1234567"),
        ("+972-52-123-4567", "052-1234567"),
        ("  052 1234567  ", "052-1234567"),
        ("026251111", "02-6251111"),
    ],
)
def test_phone_is_normalized(raw, expected):
    """כל הצורות שלקוח עשוי להקליד מגיעות לאותו ערך מאוחסן."""
    from app.utils.phone import normalize_phone_input

    assert normalize_phone_input(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "052123",  # קצר מדי
        "0521234567890",  # ארוך מדי
        "057-1234567",  # 057 אינה קידומת בשימוש
        "<script>",  # תווים לא חוקיים
        "0" * 40,  # מעל תקרת האורך
    ],
)
def test_invalid_phone_raises_a_hebrew_message(raw):
    """קלט פסול נדחה עם הודעה בעברית — לא 500 ולא טקסט טכני.

    הוולידציה יושבת ב-Pydantic ולא ב-service בדיוק בשביל זה: `ValueError`
    מתוך validator הופך לתשובת ולידציה, לא לשגיאת שרת (כלל 3).
    """
    from app.utils.phone import normalize_phone_input

    with pytest.raises(ValueError) as exc:
        normalize_phone_input(raw)
    # ההודעה בעברית — לפחות תו עברי אחד.
    assert any("֐" <= ch <= "ת" for ch in str(exc.value))


def test_booking_request_requires_a_phone():
    """הדף הציבורי לא מקבל בקשה בלי טלפון."""
    from pydantic import ValidationError as PydanticValidationError

    from app.schemas.booking_page import CreateBookingRequest

    now = datetime.now(timezone.utc)
    with pytest.raises(PydanticValidationError):
        CreateBookingRequest(
            slot_start=now,
            slot_end=now + timedelta(hours=1),
            contact_phone="",
        )


def test_booking_request_normalizes_the_phone():
    from app.schemas.booking_page import CreateBookingRequest

    now = datetime.now(timezone.utc)
    req = CreateBookingRequest(
        slot_start=now,
        slot_end=now + timedelta(hours=1),
        contact_phone="+972-52-123-4567",
    )
    assert req.contact_phone == "052-1234567"


# ===================== מגבלת קצב =====================


def test_rate_limiter_blocks_after_the_cap():
    from app.utils.rate_limit import RateLimitExceeded, SlidingWindowLimiter

    limiter = SlidingWindowLimiter(max_events=3, window_seconds=60)
    for _ in range(3):
        limiter.check()
    with pytest.raises(RateLimitExceeded) as exc:
        limiter.check()
    assert exc.value.status_code == 429


def test_rate_limiter_window_rolls_forward(monkeypatch):
    """אחרי שהחלון עובר — המכסה מתאפסת."""
    import app.utils.rate_limit as rl

    fake_now = [1000.0]
    monkeypatch.setattr(rl.time, "monotonic", lambda: fake_now[0])

    limiter = rl.SlidingWindowLimiter(max_events=2, window_seconds=60)
    limiter.check()
    limiter.check()
    with pytest.raises(rl.RateLimitExceeded):
        limiter.check()

    fake_now[0] += 61
    limiter.check()  # לא אמור לזרוק


# ===================== הערה ריקה =====================


def test_notes_of_only_whitespace_becomes_none():
    """הערה של רווחים בלבד היא הערה ריקה.

    בלי הנרמול בגבול, `"   "` הוא truthy גם ב-Python וגם ב-JS, ולכן
    הוא עובר את `if booking.notes:` וגם את `{booking.notes && ...}` —
    ומייצר שורת "הערה מהלקוח:" ריקה ביומן ובלוק הערה ריק בכרטיס.
    """
    from app.schemas.booking_page import CreateBookingRequest

    now = datetime.now(timezone.utc)
    req = CreateBookingRequest(
        slot_start=now,
        slot_end=now + timedelta(hours=1),
        contact_phone="052-1234567",
        notes="   \t\n  ",
    )
    assert req.notes is None


def test_notes_keeps_content_and_trims_edges():
    from app.schemas.booking_page import CreateBookingRequest

    now = datetime.now(timezone.utc)
    req = CreateBookingRequest(
        slot_start=now,
        slot_end=now + timedelta(hours=1),
        contact_phone="052-1234567",
        notes="  אגיע עם בן זוג  ",
    )
    assert req.notes == "אגיע עם בן זוג"


def test_description_omits_a_whitespace_only_note():
    """הצד השני של אותו באג — ברמת בניית התיאור."""
    from app.services.booking import build_event_description

    desc = build_event_description(_lead(), _booking(notes="   "))
    assert "הערה מהלקוח" not in desc
