"""
Webhook עבור push notifications של Google Calendar.

Google שולח POST בכל שינוי ביומן שאליו נרשמנו ב-create_watch. ה-body
ריק; כל המידע ב-headers:
- X-Goog-Channel-ID: ה-channel שיצרנו (verify מול DB)
- X-Goog-Resource-State: "sync" (אחרי יצירה — ack בלבד) / "exists" (שינוי)
- X-Goog-Channel-Token: shared secret שיצרנו ב-create_watch
- X-Goog-Resource-ID: ה-resource של calendar (אינפורמטיבי בלבד)

אבטחה:
- Channel-Token מאומת מול DB (Fernet-decrypted comparison).
- Channel-ID מאומת מול DB.
- אם אחד מאלה לא תואם — 200 OK בלי לעשות כלום (לא לחשוף 401 ל-spoofer).

ביצועים:
- ack מהיר (200) — סנכרון רץ ברקע דרך BackgroundTasks. Google מעדיף תגובה
  <500ms ועושה retry אגרסיבי על non-2xx.
"""

import logging

from fastapi import APIRouter, BackgroundTasks, Header, Response

from app.api.deps import DbSession
from app.db.session import AsyncSessionLocal
from app.services import booking_sync, google_calendar as gc_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/google-calendar")
async def google_calendar_webhook(
    background: BackgroundTasks,
    db: DbSession,
    x_goog_channel_id: str | None = Header(default=None),
    x_goog_resource_state: str | None = Header(default=None),
    x_goog_channel_token: str | None = Header(default=None),
) -> Response:
    """
    מקבל push מ-Google. תמיד מחזיר 200 כדי לא לעורר retry אגרסיבי, אבל
    סנכרון בפועל רץ רק לאחר אימות headers.
    """
    # ack מיידי ל-sync (Google שולח את זה ביצירת channel — אין מה לסנכרן)
    if x_goog_resource_state == "sync":
        return Response(status_code=200)

    # אימות channel_id + token. כשל שקט (200 בלי פעולה) — לא חושפים למתקיף
    # שיש לנו channel רשום וכן/לא.
    row = await _load_credentials(db)
    if row is None or row.watch_channel_id != x_goog_channel_id:
        logger.warning(
            "Webhook with unknown channel_id=%s (ignored)", x_goog_channel_id
        )
        return Response(status_code=200)

    token_ok = await gc_service.verify_watch_token(db, x_goog_channel_token)
    if not token_ok:
        logger.warning(
            "Webhook channel_id=%s with bad/missing token (ignored)",
            x_goog_channel_id,
        )
        return Response(status_code=200)

    # סנכרון ברקע — לא חוסם את ה-200. background task פותח session משלו
    # (ה-DbSession הזה ייסגר ברגע שנחזיר).
    background.add_task(_run_sync_in_new_session)
    return Response(status_code=200)


async def _load_credentials(db):
    """שליפת שורת ה-credentials לאימות channel_id. לא משתמש ב-_load_row
    הפרטי של google_calendar.py — שכפול מינימלי כדי לא לשבור encapsulation."""
    from sqlalchemy import select

    from app.models.google_credentials import GoogleCalendarCredentials

    result = await db.execute(
        select(GoogleCalendarCredentials).where(
            GoogleCalendarCredentials.id == 1
        )
    )
    return result.scalar_one_or_none()


async def _run_sync_in_new_session() -> None:
    """
    מריץ סנכרון מלא ב-session חדש. רץ אחרי שה-response של ה-webhook נשלח
    (BackgroundTasks). שגיאות נספגות + נכתבות ללוג — Google לא ממתין.

    sync_changes מחזיר את ה-token החדש בלי לpersist אותו. אנחנו persists
    אם apply עבר ללא שגיאות (כולל מקרה של 0 changes — Google כן מקדם
    token גם אם אין delta בbookings שלנו, חייבים לפרסם אחרת ניתקע על
    אותו עמוד events לנצח).
    """
    async with AsyncSessionLocal() as session:
        try:
            changes, next_token, old_token = await gc_service.sync_changes(
                session
            )

            if changes:
                stats = await booking_sync.apply_calendar_changes(
                    session, changes
                )
                logger.info("Calendar sync applied: %s", stats)
                error_count = stats["errors"]
            else:
                # 0 changes רלוונטיים, אבל ייתכן ש-Google נתן next_token
                # חדש (events לא-מ-bookings שלנו). חייבים להתקדם.
                error_count = 0

            if error_count == 0:
                # CAS: persists רק אם sync_token עוד == old_token. אם
                # webhook מקביל הקדים — persisted=False, רושמים בלוג
                # ולא דורסים cursor חדש יותר.
                persisted = await gc_service.persist_sync_token(
                    session, next_token, old_token
                )
                if not persisted:
                    logger.info(
                        "sync_token already advanced by parallel webhook — "
                        "our apply was idempotent (no data lost)"
                    )
            else:
                # ה-token לא מתקדם — הwebhook הבא יקבל את אותם האירועים שוב.
                # אם השגיאה קבועה (event פגום), זה ייתקע. אופרטור צריך
                # לחקור לוג ולתקן/לחפש פתרון.
                logger.warning(
                    "Sync had %d errors — sync_token NOT advanced. "
                    "Failed events will be retried on next webhook.",
                    error_count,
                )
        except Exception:
            logger.exception("Calendar sync failed in webhook background task")
