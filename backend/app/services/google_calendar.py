"""
Google Calendar service — OAuth flow + ניהול credentials.

מבוסס על: docs/references/google-calendar-blueprint.md סעיף 1.
שינויים אצלנו:
- async wrapper סביב הקריאות הסינכרוניות של google-auth (asyncio.to_thread)
- שמירה דרך SQLAlchemy async session
- הצפנת tokens עם Fernet (app/utils/encryption.py)
- התראה לטלגרם ב-RefreshError, עם owner_alert_sent_at למניעת ספאם
"""

from __future__ import annotations

import asyncio
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

# OAuth2 scope-drift tolerance. נדרש כי `authorization_url(
# include_granted_scopes="true")` (הן ב-Calendar והן ב-Gmail) מבקש מ-Google
# לכלול scopes שהמשתמש כבר אישר. כשמתחברים ל-Gmail אחרי Calendar (או
# להפך), Google מחזיר ב-token response את *כל* ה-scopes שאי-פעם אישרו,
# לא רק את אלה של ה-flow הנוכחי. oauthlib מתייחס לכל drift כ-security
# warning ומכשיל את החילוף עם `Warning: Scope has changed from ... to ...`.
# הדגל מתועד ב-oauthlib (https://oauthlib.readthedocs.io/) ובמובן הזה הוא
# אופציה רשמית — לא hack. ערך 'setdefault' כדי לא לדרוס override בסביבה.
# חייב לקרות לפני שה-Flow נוצר (קוראים ל-`Flow.from_client_config` בעת
# `_new_flow`), ולכן ב-module-import-time. gmail.py מייבא מהמודול הזה,
# אז גם ה-flow של Gmail מקבל את הדגל לפני הקריאה.
os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")

import google_auth_httplib2
import httplib2
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from jose import JWTError, jwt as jose_jwt
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.exceptions import AppException, ValidationError
from app.models.google_credentials import GoogleCalendarCredentials
from app.utils.encryption import decrypt_secret, encrypt_secret

logger = logging.getLogger(__name__)

# scope יחיד — קריאה+כתיבה ביומן (הכי מינימלי לצרכים שלנו)
SCOPES = ["https://www.googleapis.com/auth/calendar"]

_TOKEN_URI = "https://oauth2.googleapis.com/token"
_AUTH_URI = "https://accounts.google.com/o/oauth2/auth"

# id קבוע לשורה היחידה
_SINGLETON_ID = 1

# ===================== Service builder =====================

# timeout לכל קריאה ל-Google Calendar, בשניות.
#
# למה זה קריטי דווקא כאן: קביעת פגישה מהדף הציבורי יוצרת את האירוע
# ביומן **בתוך טרנזקציה פתוחה** שמחזיקה נעילת שורה על הליד וחיבור מה-
# pool (`pool_size=5, max_overflow=10` ב-`app/db/session.py` = 15 חיבורים
# מול תהליך uvicorn יחיד). בלי timeout, תקיעה אצל Google מחזיקה את
# החיבור ואת הנעילה ללא הגבלת זמן — ב-endpoint ציבורי שכל אחד יכול
# לקרוא לו. 10 שניות נדיב לקריאת API רגילה וחוסם תקיעה.
#
# httplib2 הוא ה-transport שבו google-api-python-client משתמש כברירת
# מחדל, ו-`AuthorizedHttp` עוטף אותו עם ה-credentials. כשמעבירים `http=`
# אסור להעביר גם `credentials=` — ה-builder מקבל אחד מהשניים.
_GOOGLE_API_TIMEOUT_SECONDS = 10


def _calendar_service(creds: Credentials):
    """בונה client של Calendar API עם timeout. blocking — רק בתוך thread.

    נקודה אחת לכל הקריאות: `build(...)` הופיע ב-7 מקומות בקובץ הזה
    ובעוד אחד ב-`booking.py`, וכל אחד מהם היה צריך לזכור את ה-timeout
    בנפרד.
    """
    authed_http = google_auth_httplib2.AuthorizedHttp(
        creds, http=httplib2.Http(timeout=_GOOGLE_API_TIMEOUT_SECONDS)
    )
    return build("calendar", "v3", http=authed_http, cache_discovery=False)


# ===================== בחירת יומנים =====================


def target_calendar_id(row: GoogleCalendarCredentials) -> str:
    """היומן שאליו נכתבים אירועים ושעליו רשום ה-watch.

    fallback ל-"primary" אם העמודה ריקה משום מה — "primary" הוא כינוי
    של Google ליומן הראשי, ולכן תמיד תקף.
    """
    return row.calendar_id or "primary"


async def get_credentials_row(
    db: AsyncSession,
) -> GoogleCalendarCredentials | None:
    """שורת ה-credentials, או None אם Google לא מחובר.

    wrapper ציבורי סביב `_load_row` עבור קוראים מחוץ למודול (חישוב
    הזמינות ב-`booking.py` צריך את בחירת היומנים). קיים כדי שלא ייווצר
    שוב שכפול של ה-query כמו ב-`routes/google_webhook.py`.
    """
    return await _load_row(db)


def busy_calendar_ids(row: GoogleCalendarCredentials) -> list[str]:
    """כל היומנים שנחשבים "תפוס" בחישוב הזמינות — היעד + הנוספים.

    היעד תמיד ברשימה: הפגישות שאנחנו יוצרים חיות בו, וגם האירועים
    ש-נועה מנהלת שם ידנית. `dict.fromkeys` שומר על סדר ומסיר כפילויות
    (אם מישהו הוסיף את היעד גם לרשימת הנוספים).
    """
    extra = row.busy_calendar_ids or []
    return list(dict.fromkeys([target_calendar_id(row), *extra]))


# ===================== Exceptions =====================


class GoogleNotConfiguredError(AppException):
    status_code = 503
    code = "google_not_configured"
    user_message = "האינטגרציה ל-Google לא הוגדרה. צרי קשר עם המתאם."


class GoogleNotConnectedError(AppException):
    status_code = 409
    code = "google_not_connected"
    user_message = "יומן Google לא מחובר. יש להתחבר ב-/settings."


class GoogleAuthInvalidError(AppException):
    status_code = 401
    code = "google_auth_invalid"
    user_message = "החיבור ל-Google פג תוקף. יש להתחבר מחדש ב-/settings."


# ===================== OAuth Flow =====================


def _client_config() -> dict[str, Any]:
    s = get_settings()
    if not (s.google_client_id and s.google_client_secret and s.google_redirect_uri):
        raise GoogleNotConfiguredError()
    return {
        "web": {
            "client_id": s.google_client_id,
            "client_secret": s.google_client_secret,
            "auth_uri": _AUTH_URI,
            "token_uri": _TOKEN_URI,
            "redirect_uris": [s.google_redirect_uri],
        }
    }


def _new_flow() -> Flow:
    return Flow.from_client_config(
        client_config=_client_config(),
        scopes=SCOPES,
        redirect_uri=get_settings().google_redirect_uri,
    )


def generate_code_verifier() -> str:
    """PKCE code_verifier — 64 bytes URL-safe (88 chars), בטווח של RFC 7636."""
    return secrets.token_urlsafe(64)


# === state encoding (JWT חתום) ===
# המוטיב: ב-Render כל subdomain הוא site נפרד לפי Public Suffix List, אז
# cookies שנשמרים מ-/google/auth/start (cross-origin XHR) לא יגיעו ל-
# /google/auth/callback (top-level navigation מ-Google). הפתרון: לקודד את
# code_verifier + nonce ב-JWT חתום שעובר דרך פרמטר `state` של OAuth.
# המנגנון cookieless לחלוטין, בטוח מ-CSRF בזכות החתימה + exp + nonce.

_STATE_TTL_SECONDS = 600  # 10 דקות מספיק ל-flow רגיל
_STATE_ALG = "HS256"


def encode_oauth_state(code_verifier: str) -> str:
    """
    מקודד code_verifier + nonce ב-JWT חתום ב-JWT_SECRET_KEY.
    התוצאה נשלחת כפרמטר state ל-Google ומוחזרת אלינו בקאלבק.
    """
    s = get_settings()
    now = datetime.now(tz=timezone.utc)
    payload = {
        "ver": code_verifier,
        "nonce": secrets.token_urlsafe(16),  # מגן מפני replay
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=_STATE_TTL_SECONDS)).timestamp()),
        "use": "google_oauth",  # type tag — מונע שימוש חוזר ב-JWTs אחרים
    }
    return jose_jwt.encode(payload, s.jwt_secret_key, algorithm=_STATE_ALG)


def decode_oauth_state(state: str) -> str:
    """
    מאמת חתימה + exp ומחזיר code_verifier. זורק ValidationError אם state
    לא תקין, פג תוקף, או נחתם בשונה.
    """
    s = get_settings()
    try:
        payload = jose_jwt.decode(state, s.jwt_secret_key, algorithms=[_STATE_ALG])
    except JWTError as e:
        raise ValidationError("state לא תקף") from e
    if payload.get("use") != "google_oauth":
        raise ValidationError("state לא תקף")
    verifier = payload.get("ver")
    if not isinstance(verifier, str):
        raise ValidationError("state לא תקף")
    return verifier


def build_auth_url(code_verifier: str) -> str:
    """
    מחזיר את ה-auth URL להפניית הbrowser ל-Google. ה-state כבר מוטמע ב-URL
    (cookieless flow — ראה encode_oauth_state).
    """
    flow = _new_flow()
    flow.code_verifier = code_verifier
    state = encode_oauth_state(code_verifier)
    auth_url, _ = flow.authorization_url(
        # offline → מקבלים גם refresh_token (לא רק access)
        access_type="offline",
        # prompt=consent → מבטיח refresh_token גם בחיבור חוזר
        prompt="consent",
        include_granted_scopes="true",
        # מחליפים את ה-state ש-google-auth ייצור אוטומטית בlנו
        state=state,
    )
    return auth_url


async def exchange_code_and_save(
    db: AsyncSession, code: str, code_verifier: str
) -> GoogleCalendarCredentials:
    """
    מחליף את ה-code ל-tokens ושומר ל-DB. שולח גם פעולה ל-Calendar API
    כדי לקבל את האימייל וה-timezone של הלקוחה.
    """
    flow = _new_flow()
    flow.code_verifier = code_verifier

    # fetch_token עושה blocking HTTP — מבודד ל-thread כדי לא לחסום event loop
    await asyncio.to_thread(flow.fetch_token, code=code)
    creds: Credentials = flow.credentials

    if not creds.refresh_token:
        # קורה אם המשתמש כבר אישר בעבר ולא ביקשנו prompt=consent. אצלנו
        # always prompt — אז זה שגיאת קונפיגורציה. בכל זאת — fail loud.
        raise ValidationError(
            "Google לא החזיר refresh_token. נסי לנתק את האפליקציה בחשבון "
            "Google ולהתחבר מחדש."
        )

    # שליפת פרטי החשבון — primary calendar.id == האימייל של המשתמש
    email, calendar_tz = await asyncio.to_thread(_fetch_account_info, creds)

    # בחירת היומנים של נועה חייבת לשרוד חיבור מחדש. ה-upsert כאן הוא
    # DELETE+INSERT, ולכן בלי השימור הזה כל "התחברות מחדש" — בדיוק מה
    # שהיא מתבקשת לעשות כשה-token פג — הייתה מאפסת את יומן היעד ואת
    # רשימת היומנים התפוסים בשקט, והזמינות הייתה חוזרת להציג שעות תפוסות
    # כפנויות.
    #
    # השימור מותנה באותו חשבון: אם נועה התחברה עם כתובת אחרת, מזהי
    # היומנים הישנים לא קיימים שם, ולכן מתחילים מחדש מ-"primary".
    previous = await _load_row(db)
    if previous is not None and previous.google_account_email == email:
        preserved_calendar_id = previous.calendar_id or "primary"
        preserved_busy_ids = list(previous.busy_calendar_ids or [])
    else:
        preserved_calendar_id = "primary"
        preserved_busy_ids = []

    # אם יש שורת credentials ישנה עם watch פעיל — לעצור אותו אצל Google
    # לפני המחיקה. אחרת ה-channel ישאר orphan ויתפוגג רק אחרי כשבוע.
    # stop_watch כבר עמיד לכשלי auth (creds ישנים) — נספגים בשקט.
    try:
        await stop_watch(db)
    except Exception:
        logger.exception("Failed to stop watch during reconnect (continuing)")

    # שמירה ל-DB (upsert: delete + insert, פשוט יותר מ-ON CONFLICT עם CHECK)
    await db.execute(
        delete(GoogleCalendarCredentials).where(
            GoogleCalendarCredentials.id == _SINGLETON_ID
        )
    )
    row = GoogleCalendarCredentials(
        id=_SINGLETON_ID,
        google_account_email=email,
        calendar_id=preserved_calendar_id,
        busy_calendar_ids=preserved_busy_ids,
        refresh_token_encrypted=encrypt_secret(creds.refresh_token),
        access_token_encrypted=(
            encrypt_secret(creds.token) if creds.token else None
        ),
        token_expiry=creds.expiry.replace(tzinfo=timezone.utc) if creds.expiry else None,
        timezone=calendar_tz or "Asia/Jerusalem",
        auth_invalid_at=None,
        owner_alert_sent_at=None,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    logger.info("Google Calendar connected as %s", email)

    # יצירת watch channel אוטומטית — אם backend_url מוגדר. כשלון כאן לא
    # מבטל את החיבור (הסנכרון ההפוך אופציונלי; DB→Google עובד גם בלעדיו).
    # ב-dev בלי URL ציבורי, פשוט יידלג עם warning.
    try:
        await create_watch(db)
    except WatchNotConfiguredError:
        logger.info(
            "Skipping watch creation: BACKEND_URL not configured (dev mode)"
        )
    except Exception:
        logger.exception("Failed to create watch channel after OAuth")

    return row


def _fetch_account_info(creds: Credentials) -> tuple[str, str]:
    """שליפה סינכרונית של email + timezone. נקראת בתוך asyncio.to_thread."""
    service = _calendar_service(creds)
    cal = service.calendars().get(calendarId="primary").execute()
    # id של primary calendar = אימייל החשבון
    return cal["id"], cal.get("timeZone", "Asia/Jerusalem")


# ===================== Credentials loading + refresh =====================


async def get_credentials_or_404(db: AsyncSession) -> Credentials:
    """
    טוען credentials מה-DB, מבצע refresh אם פג, מטפל ב-RefreshError.
    זורק:
    - GoogleNotConfiguredError אם env vars חסרים (client_id/secret/redirect)
    - GoogleNotConnectedError אם אין שורה ב-DB
    - GoogleAuthInvalidError אם auth_invalid_at מסומן או refresh נכשל
    """
    # ולידציה שכל ה-Google env vars מוגדרים — אחרת build_credentials עם
    # client_id=None יעבור init אבל יפיל בrefresh עם הודעת libc גנרית.
    # _client_config זורק GoogleNotConfiguredError אם משהו חסר.
    _client_config()

    row = await _load_row(db)
    if row is None:
        raise GoogleNotConnectedError()
    if row.auth_invalid_at is not None:
        raise GoogleAuthInvalidError()

    s = get_settings()
    creds = Credentials(
        token=decrypt_secret(row.access_token_encrypted)
        if row.access_token_encrypted
        else None,
        refresh_token=decrypt_secret(row.refresh_token_encrypted),
        token_uri=_TOKEN_URI,
        client_id=s.google_client_id,
        client_secret=s.google_client_secret,
        scopes=SCOPES,
        expiry=row.token_expiry.replace(tzinfo=None) if row.token_expiry else None,
    )

    if creds.expired or not creds.token:
        try:
            await asyncio.to_thread(creds.refresh, Request())
        except RefreshError:
            # מסמן ב-session נפרד — לא לסיים-commit את ה-transaction של הקורא
            await _mark_auth_invalid(row.owner_alert_sent_at is None)
            raise GoogleAuthInvalidError() from None
        # שומרים את ה-access_token החדש ב-session נפרד. לפני התיקון: db.commit()
        # על ה-session המשותף היה מסיים-commit את כל ה-pending changes של
        # הקורא (למשל approve_booking שכבר עשתה UPDATE לbooking/lead), והופך
        # את הfail-safe rollback למחיק עם רישומים שכבר persisted.
        await _persist_refreshed_token(creds.token, creds.expiry)

    return creds


async def _load_row(db: AsyncSession) -> GoogleCalendarCredentials | None:
    result = await db.execute(
        select(GoogleCalendarCredentials)
        .where(GoogleCalendarCredentials.id == _SINGLETON_ID)
        .execution_options(populate_existing=True)
    )
    return result.scalar_one_or_none()


async def _persist_refreshed_token(
    new_access_token: str, new_expiry: datetime | None
) -> None:
    """שומר access_token שעודכן ב-session נפרד — כדי לא לגרור commit
    של ה-transaction של הקורא. ראה comment ב-get_credentials_or_404."""
    from app.db.session import AsyncSessionLocal

    expiry_utc = (
        new_expiry.replace(tzinfo=timezone.utc) if new_expiry else None
    )
    async with AsyncSessionLocal() as fresh:
        await fresh.execute(
            update(GoogleCalendarCredentials)
            .where(GoogleCalendarCredentials.id == _SINGLETON_ID)
            .values(
                access_token_encrypted=encrypt_secret(new_access_token),
                token_expiry=expiry_utc,
            )
        )
        await fresh.commit()


async def _mark_auth_invalid(should_alert: bool) -> None:
    """
    מסמן את ה-credentials כשגויים. אם should_alert — מנסה לשלוח לטלגרם
    *לפני* persistence של owner_alert_sent_at — אחרת כשל בטלגרם (network
    / bot token) משאיר את הflag set והמשתמש לא יקבל התראה לעולם
    (refresh הבא יראה owner_alert_sent_at!=None ולא ינסה שוב).

    סדר: send → אם הצליח, הוסף לvalues → commit. כשל בtelegram = הflag
    נשאר None, refresh הבא ינסה שוב.

    עובד ב-session נפרד מהקורא — לפני התיקון, הcommit היה מסיים-commit
    transactions של callers (כמו approve_booking) ושובר את הfail-safe.
    """
    from app.db.session import AsyncSessionLocal

    now = datetime.now(timezone.utc)
    values: dict[str, datetime] = {"auth_invalid_at": now}

    alert_sent_ok = False
    if should_alert:
        # local import — telegram עשוי לא להיות מוגדר ב-dev
        from app.services import telegram as telegram_service

        try:
            alert_sent_ok = bool(
                await telegram_service.send_message(
                    "⚠️ <b>חיבור היומן ל-Google פג תוקף</b>\n"
                    "פגישות חדשות לא יסונכרנו ליומן עד שתתחברי מחדש ב-/settings.\n"
                    "ההודעה הזו תישלח פעם אחת בלבד."
                )
            )
        except Exception:
            logger.exception(
                "Failed to send Calendar auth-invalid Telegram alert"
            )
            alert_sent_ok = False

    if alert_sent_ok:
        values["owner_alert_sent_at"] = now

    async with AsyncSessionLocal() as fresh:
        await fresh.execute(
            update(GoogleCalendarCredentials)
            .where(GoogleCalendarCredentials.id == _SINGLETON_ID)
            .values(**values)
        )
        await fresh.commit()


# ===================== Status + Disconnect =====================


async def get_status(db: AsyncSession) -> dict[str, Any]:
    """תיאור החיבור הנוכחי לתצוגה ב-UI."""
    row = await _load_row(db)
    if row is None:
        return {"connected": False, "auth_invalid": False}
    return {
        "connected": True,
        "google_account_email": row.google_account_email,
        "calendar_id": row.calendar_id,
        "timezone": row.timezone,
        "connected_at": row.created_at,
        "auth_invalid": row.auth_invalid_at is not None,
        # שדות סנכרון הפוך (שלב 14)
        "watch_active": row.watch_channel_id is not None,
        "watch_expiration": row.watch_expiration,
        # בחירת היומנים (מיגרציה 0032)
        "busy_calendar_ids": list(row.busy_calendar_ids or []),
    }


# ===================== בחירת יומנים =====================


async def list_account_calendars(db: AsyncSession) -> list[dict[str, Any]]:
    """כל היומנים שברשימת היומנים של החשבון המחובר.

    זה המקור לבורר ב-/settings: נועה מסמנת אילו מהם נחשבים "תפוס"
    ולאיזה מהם ייכתבו הפגישות. היומן שהיא "צירפה ליומן הראשי" מופיע
    כאן כרשומה נפרדת, גם אם הוא שייך לחשבון אחר ושותף איתה.

    ה-scope הקיים `.../auth/calendar` כבר מכסה את `calendarList.list`
    (אומת מול מסמך ה-discovery הרשמי של Calendar v3), ולכן אין צורך
    בהרשאה נוספת ולא בחיבור OAuth שני.
    """
    creds = await get_credentials_or_404(db)
    return await asyncio.to_thread(_list_calendars_blocking, creds)


def _list_calendars_blocking(creds: Credentials) -> list[dict[str, Any]]:
    """blocking — נקרא רק מתוך asyncio.to_thread."""
    service = _calendar_service(creds)
    items: list[dict[str, Any]] = []
    page_token: str | None = None
    while True:
        params: dict[str, Any] = {"maxResults": 250, "showHidden": True}
        if page_token:
            params["pageToken"] = page_token
        result = service.calendarList().list(**params).execute()
        for entry in result.get("items", []):
            # יומן שהוסר מהרשימה חוזר עם deleted=true — לא להציג.
            if entry.get("deleted"):
                continue
            items.append(
                {
                    "id": entry["id"],
                    # summaryOverride = השם שנועה נתנה ליומן אצלה; מה
                    # שהיא רואה ב-Google הוא זה, ולכן הוא קודם.
                    "summary": entry.get("summaryOverride")
                    or entry.get("summary")
                    or entry["id"],
                    "primary": bool(entry.get("primary")),
                    "access_role": entry.get("accessRole", ""),
                }
            )
        page_token = result.get("nextPageToken")
        if not page_token:
            return items


# accessRole שמספיק כדי *לקרוא* תפוסה. "freeBusyReader" רואה רק
# פנוי/תפוס — בדיוק מה שצריך ליומן "תפוס" ותו לא.
_READABLE_ROLES = {"freeBusyReader", "reader", "writer", "owner"}
# accessRole שמספיק כדי *ליצור* אירוע. יומן יעד חייב להיות אחד מאלה,
# אחרת יצירת הפגישה תיכשל רק ברגע האמת — מול הלקוח.
_WRITABLE_ROLES = {"writer", "owner"}


async def set_calendar_selection(
    db: AsyncSession, *, target_id: str, busy_ids: list[str]
) -> bool:
    """שומר את יומן היעד ואת רשימת היומנים ה"תפוסים".

    מחזיר `target_changed` — האם יומן היעד השתנה, כלומר האם צריך להזיז
    את ה-watch. הפונקציה עושה `flush` בלבד ו**לא** `commit`: גבול
    הטרנזקציה שייך ל-route (CLAUDE.md כלל 15). הזזת ה-watch עצמה יושבת
    ב-route ורצה *אחרי* ה-commit, כי היא קריאה חיצונית best-effort ואין
    סיבה שהיא תחזיק טרנזקציה פתוחה — אותו דפוס שכבר קיים ב-
    `booking.cancel_booking`.

    שני המזהים מאומתים מול `calendarList` בזמן השמירה, ולא רק בזמן
    השימוש. הסיבה: `_fetch_google_busy` הוא fail-safe — יומן שלא ניתן
    לקרוא ממנו מפיל את דף קביעת הפגישה כולו ל-503. עדיף שהשגיאה תגיע
    לנועה כאן, כשהיא בוחרת, מאשר ללקוח שמנסה לקבוע תור.

    אם יומן היעד השתנה — ה-watch וה-syncToken מתאפסים ונוצרים מחדש על
    היומן החדש. בלי זה ה-cursor היה ממשיך להצביע ליומן הקודם, ושינויים
    שנועה עושה ביומן החדש לא היו מסונכרנים בחזרה.
    """
    row = await _load_row(db)
    if row is None:
        raise GoogleNotConnectedError()

    available = {c["id"]: c for c in await list_account_calendars(db)}

    target = available.get(target_id)
    if target is None:
        raise ValidationError("היומן שנבחר לא נמצא בחשבון Google המחובר.")
    if target["access_role"] not in _WRITABLE_ROLES:
        raise ValidationError(
            "אין הרשאת כתיבה ליומן שנבחר, ולכן לא ניתן לקבוע בו פגישות."
        )

    # dict.fromkeys מסיר כפילויות ושומר סדר. היעד לא צריך להופיע ברשימה
    # הנוספת — `busy_calendar_ids()` מוסיף אותו ממילא בכל חישוב.
    cleaned_busy: list[str] = []
    for cid in dict.fromkeys(busy_ids):
        if cid == target_id:
            continue
        entry = available.get(cid)
        if entry is None:
            raise ValidationError(
                "אחד היומנים שנבחרו לא נמצא בחשבון Google המחובר."
            )
        if entry["access_role"] not in _READABLE_ROLES:
            raise ValidationError(
                f"אין הרשאה לקרוא את הזמינות של היומן \"{entry['summary']}\"."
            )
        cleaned_busy.append(cid)

    target_changed = (row.calendar_id or "primary") != target_id

    # החלפת יומן יעד **לא** מפסיקה לבדוק את היומן הקודם.
    #
    # `busy_calendar_ids()` מוסיף את היעד הנוכחי אוטומטית, ולכן היעד
    # אף פעם לא מופיע ברשימת ה"נוספים" — וברגע שהוא מפסיק להיות היעד
    # הוא נופל מהחישוב לגמרי. התוצאה: כל הפגישות שכבר קיימות ביומן
    # שנועה עזבה הופכות ל"פנוי", ולקוחות יכולים לקבוע עליהן. השתיקה
    # כאן מוחלטת — אין שגיאה, רק סלוטים שנראים זמינים.
    #
    # ברירת המחדל היא fail-safe: שומרים אותו כנבדק. אם נועה רוצה
    # להפסיק לבדוק אותו, היא מורידה את הסימון — פעולה מפורשת, ולא
    # תופעת לוואי של החלפת יעד.
    previous_target = row.calendar_id or "primary"
    if (
        target_changed
        and previous_target != target_id
        and previous_target in available
        and previous_target not in cleaned_busy
    ):
        cleaned_busy.append(previous_target)

    await db.execute(
        update(GoogleCalendarCredentials)
        .where(GoogleCalendarCredentials.id == _SINGLETON_ID)
        .values(calendar_id=target_id, busy_calendar_ids=cleaned_busy)
    )
    await db.flush()
    return target_changed


async def disconnect(db: AsyncSession) -> None:
    """מנתק לחלוטין — עוצר watch ומוחק את שורת ה-credentials."""
    # stop_watch קודם — אחרת ייוותר channel פעיל אצל Google שישלח push
    # ל-webhook שלנו, שיכשל באימות (אין credentials → 401) ויבוזבזו ניסיונות.
    try:
        await stop_watch(db)
    except Exception:
        logger.exception("Failed to stop watch during disconnect")

    await db.execute(
        delete(GoogleCalendarCredentials).where(
            GoogleCalendarCredentials.id == _SINGLETON_ID
        )
    )
    await db.commit()
    logger.info("Google Calendar disconnected")


# ===================== Event creation =====================


async def create_calendar_event(
    db: AsyncSession,
    *,
    booking_id: UUID,
    summary: str,
    description: str,
    start: datetime,
    end: datetime,
) -> tuple[str, str]:
    """
    יוצר אירוע ב**יומן היעד** של נועה ומחזיר `(event_id, calendar_id)`.

    **למה מוחזר גם מזהה היומן:** האירוע חי ביומן שאליו נכתב, וזו עובדה
    עליו — לא מצב גלובלי. אם נועה תחליף את יומן היעד ב-/settings,
    `credentials.calendar_id` ישתנה, והאירוע הישן יישאר במקומו. קורא
    שיבקש למחוק אותו לפי היעד ה*נוכחי* יפנה ליומן הלא נכון. לכן הקורא
    שומר את מזהה היומן על שורת ה-Booking ומעביר אותו למחיקה.

    יומן היעד נקרא מ-`credentials.calendar_id` ולא מקובע ל-"primary" —
    נועה יכולה לבחור יומן אחר ב-/settings. היומנים ה"נוספים" (
    `busy_calendar_ids`) משמשים לחישוב זמינות בלבד; לעולם לא נכתב אליהם
    דבר, כדי שפגישה לא תיווצר פעמיים.

    booking_id נשמר ב-extendedProperties.private.bookingId כעוגן לסנכרון
    דו-כיווני בשלב 14 (Google→DB) — מאפשר לזהות שאירוע שינוי/נמחק
    שייך לbooking ספציפי שלנו. ראה: docs/references/google-calendar-blueprint.md
    סעיף 5.

    attendees לא נוספים — החלטה ל-MVP. נועה תיצור קשר עם הליד ידנית.

    מעלה את החריגות של get_credentials_or_404 (Google not connected /
    auth invalid). הקורא אחראי להחליט אם זה fail-safe (rollback) או
    fall-through (אירוע יווצר ידנית).
    """
    creds = await get_credentials_or_404(db)
    row = await _load_row(db)
    if row is None:
        raise GoogleNotConnectedError()
    calendar_id = target_calendar_id(row)
    event_id = await asyncio.to_thread(
        _create_event_blocking,
        creds,
        calendar_id,
        booking_id,
        summary,
        description,
        start,
        end,
    )
    return event_id, calendar_id


def _create_event_blocking(
    creds: Credentials,
    calendar_id: str,
    booking_id: UUID,
    summary: str,
    description: str,
    start: datetime,
    end: datetime,
) -> str:
    """blocking — נקרא רק מתוך asyncio.to_thread."""
    service = _calendar_service(creds)
    body = {
        "summary": summary,
        "description": description,
        "start": {
            "dateTime": start.isoformat(),
            "timeZone": "Asia/Jerusalem",
        },
        "end": {
            "dateTime": end.isoformat(),
            "timeZone": "Asia/Jerusalem",
        },
        # 🟣 צבע "לקוחות" לפי האפיון יב, סעיף 220. Google colorId="3"
        # = Grape (סגול). שאר הקטגוריות (סדנאות/הכנה/ניהול/אישי/חסום)
        # נועה מנהלת בעצמה ביומן — אנחנו יוצרים רק אירועי לקוחות.
        "colorId": "3",
        "extendedProperties": {
            "private": {"bookingId": str(booking_id)},
        },
        # reminders ברירת מחדל של היומן (popup 10 דק' לפני). לא דורסים
        # כדי שנועה תוכל לכוונן באופן גלובלי דרך הגדרות יומן Google.
    }
    result = (
        service.events()
        .insert(calendarId=calendar_id, body=body)
        .execute()
    )
    return result["id"]



async def delete_calendar_event(
    db: AsyncSession, event_id: str, calendar_id: str | None = None
) -> None:
    """
    מוחק אירוע. 404/410 (אירוע כבר נמחק) נספג שקט — אינדמפוטנטי.
    משמש לcompensation: אם commit של ה-DB נכשל אחרי יצירת אירוע, הקורא
    מוחק את האירוע ה-orphan כדי לא להשאיר ביומן של נועה פגישה שאינה ב-CRM.

    `calendar_id` הוא **היומן שבו האירוע באמת נמצא**, כפי שנשמר על שורת
    ה-Booking בעת היצירה. חובה להעביר אותו כשהוא ידוע: מחיקה לפי יומן
    היעד ה*נוכחי* נכשלת ב-404 אם נועה החליפה יומן בינתיים, וה-404
    נספג בשקט (זה מה שנדרש לאידמפוטנטיות) — כלומר האירוע היה נשאר
    ביומן הישן לנצח, בלי שאיש יידע. `None` נשאר רק עבור פגישות שנוצרו
    לפני שהעמודה קיימת, ושם הנפילה חזרה ליעד הנוכחי היא הניחוש הטוב
    ביותר האפשרי.
    """
    creds = await get_credentials_or_404(db)
    row = await _load_row(db)
    if row is None:
        raise GoogleNotConnectedError()
    await asyncio.to_thread(
        _delete_event_blocking,
        creds,
        calendar_id or target_calendar_id(row),
        event_id,
    )


def _delete_event_blocking(
    creds: Credentials, calendar_id: str, event_id: str
) -> None:
    """blocking — נקרא רק מתוך asyncio.to_thread."""
    service = _calendar_service(creds)
    try:
        service.events().delete(
            calendarId=calendar_id, eventId=event_id
        ).execute()
    except HttpError as e:
        # 404/410 — האירוע כבר לא קיים. אינדמפוטנטי.
        if e.resp.status in (404, 410):
            return
        raise


# ===================== Watch channels + reverse sync =====================
#
# Google Calendar שולח push notifications ל-webhook שלנו בכל שינוי ביומן.
# ראה: docs/references/google-calendar-blueprint.md סעיף 6.
#
# זרימה:
# 1. create_watch — נרשם ל-events, מקבל channel_id + resource_id + expiration.
# 2. Google שולח POST ל-/webhooks/google-calendar בכל שינוי (headers בלבד,
#    אין payload משמעותי).
# 3. webhook קורא ל-sync_changes(db) שמשתמש ב-syncToken להבאת deltas בלבד.
# 4. ה-deltas מוחזרים — והקורא (booking_sync) מטמיע ב-DB.


# תוקף watch מקסימלי (Google clamps לעיתים לשעות). שבוע = הערך הגבוה.
_WATCH_TTL_SECONDS = 7 * 24 * 3600
# מתי לחדש מוקדם — אם פג תוך 24 שעות, ה-cron יחדש מבעוד מועד
_WATCH_RENEW_WITHIN = timedelta(hours=24)


class WatchNotConfiguredError(AppException):
    """backend_url לא מוגדר — לא ניתן ליצור watch channel."""

    status_code = 503
    code = "backend_url_not_configured"
    user_message = (
        "סנכרון יומן הפוך לא מוגדר (חסר BACKEND_URL). צרי קשר עם המתאם."
    )


async def create_watch(db: AsyncSession) -> dict[str, Any]:
    """
    יוצר watch channel על **יומן היעד** + מאתחל syncToken דרך events.list.

    ה-watch יושב רק על יומן היעד, כי רק בו חיים האירועים שאנחנו יצרנו —
    היומנים ה"נוספים" משמשים לחישוב זמינות בלבד ואין בהם מה לסנכרן.
    לכן גם ה-`sync_token` נשאר יחיד ואין שני cursors שיכולים לדרוס זה את זה.

    אם כבר קיים watch פעיל — עוצר אותו קודם (idempotent — לא נוצרים כפילויות).
    מחזיר dict עם פרטי ה-channel לתצוגה ב-UI/לוג.
    """
    s = get_settings()
    if not s.backend_url:
        raise WatchNotConfiguredError()

    creds = await get_credentials_or_404(db)
    row = await _load_row(db)
    if row is None:
        raise GoogleNotConnectedError()

    # עצירת watch קודם אם קיים — מונע orphan channels אצל Google
    if row.watch_channel_id and row.watch_resource_id:
        try:
            await asyncio.to_thread(
                _stop_channel_blocking,
                creds,
                row.watch_channel_id,
                row.watch_resource_id,
            )
        except Exception:
            # שגיאת stop לא חוסמת — אולי כבר פג מעצמו
            logger.warning(
                "Failed to stop existing watch channel %s", row.watch_channel_id
            )

    channel_id = f"noa-cal-{secrets.token_urlsafe(16)}"
    watch_token = secrets.token_urlsafe(32)
    address = s.backend_url.rstrip("/") + "/webhooks/google-calendar"

    calendar_id = target_calendar_id(row)
    result = await asyncio.to_thread(
        _watch_blocking, creds, calendar_id, channel_id, address, watch_token
    )

    # קבלת syncToken התחלתי — events.list ראשון מחזיר nextSyncToken
    # (לפעמים דרך paging — הפעם הזו אנחנו רק רוצים את ה-token, לא את האירועים).
    sync_token = await asyncio.to_thread(
        _initial_sync_token_blocking, creds, calendar_id
    )

    # שמירה ל-DB
    expiration_ms = int(result.get("expiration", 0))
    expiration_dt = datetime.fromtimestamp(
        expiration_ms / 1000, tz=timezone.utc
    ) if expiration_ms else None

    await db.execute(
        update(GoogleCalendarCredentials)
        .where(GoogleCalendarCredentials.id == _SINGLETON_ID)
        .values(
            watch_channel_id=channel_id,
            watch_resource_id=result["resourceId"],
            watch_expiration=expiration_dt,
            watch_token_encrypted=encrypt_secret(watch_token),
            sync_token=sync_token,
        )
    )
    await db.commit()

    logger.info(
        "Created Google Calendar watch channel %s (expires %s)",
        channel_id,
        expiration_dt,
    )
    return {
        "channel_id": channel_id,
        "resource_id": result["resourceId"],
        "expiration": expiration_dt,
    }


def _watch_blocking(
    creds: Credentials,
    calendar_id: str,
    channel_id: str,
    address: str,
    token: str,
) -> dict[str, Any]:
    """blocking — נקרא רק מתוך asyncio.to_thread."""
    service = _calendar_service(creds)
    expiration_ms = int(
        (datetime.now(timezone.utc) + timedelta(seconds=_WATCH_TTL_SECONDS)).timestamp() * 1000
    )
    body = {
        "id": channel_id,
        "type": "web_hook",
        "address": address,
        "token": token,
        "expiration": expiration_ms,
    }
    return service.events().watch(calendarId=calendar_id, body=body).execute()


def _initial_sync_token_blocking(
    creds: Credentials, calendar_id: str
) -> str | None:
    """events.list ראשון לקבלת nextSyncToken. עוקבים אחר pageToken עד הסוף."""
    service = _calendar_service(creds)
    page_token: str | None = None
    while True:
        params: dict[str, Any] = {
            "calendarId": calendar_id,
            "showDeleted": True,
            "singleEvents": True,
            "maxResults": 2500,
        }
        if page_token:
            params["pageToken"] = page_token
        result = service.events().list(**params).execute()
        next_token = result.get("nextSyncToken")
        if next_token:
            return next_token
        page_token = result.get("nextPageToken")
        if not page_token:
            return None


def _stop_channel_blocking(
    creds: Credentials, channel_id: str, resource_id: str
) -> None:
    service = _calendar_service(creds)
    try:
        service.channels().stop(
            body={"id": channel_id, "resourceId": resource_id}
        ).execute()
    except HttpError as e:
        if e.resp.status in (404, 410):
            return
        raise


async def stop_watch(db: AsyncSession) -> None:
    """עוצר את ה-watch הנוכחי (אם קיים) ומנקה את שדות ה-watch ב-DB."""
    row = await _load_row(db)
    if row is None or not (row.watch_channel_id and row.watch_resource_id):
        return
    try:
        creds = await get_credentials_or_404(db)
        await asyncio.to_thread(
            _stop_channel_blocking,
            creds,
            row.watch_channel_id,
            row.watch_resource_id,
        )
    except (GoogleNotConnectedError, GoogleAuthInvalidError):
        # לא מחובר/auth שבור — מנקים בכל מקרה את ה-DB
        pass
    await db.execute(
        update(GoogleCalendarCredentials)
        .where(GoogleCalendarCredentials.id == _SINGLETON_ID)
        .values(
            watch_channel_id=None,
            watch_resource_id=None,
            watch_expiration=None,
            watch_token_encrypted=None,
        )
    )
    await db.commit()


async def renew_watch_if_needed(db: AsyncSession) -> bool:
    """
    מחדש את ה-watch אם הוא פג תוך _WATCH_RENEW_WITHIN או כבר פג.
    מחזיר True אם חודש, False אם לא היה צורך.
    משמש מ-cron יומי (jobs/renew_calendar_watch.py).
    """
    row = await _load_row(db)
    if row is None:
        return False
    if not row.watch_expiration:
        # אין watch בכלל — יוצרים חדש אם backend_url מוגדר ויש credentials
        try:
            await create_watch(db)
            return True
        except (GoogleNotConnectedError, GoogleAuthInvalidError, WatchNotConfiguredError):
            return False

    now = datetime.now(timezone.utc)
    if row.watch_expiration - now > _WATCH_RENEW_WITHIN:
        return False  # עוד יש זמן

    await create_watch(db)  # create_watch מטפל ב-stop של הישן
    return True


# ===================== Reverse sync (events.list with syncToken) =====================


class CalendarChange:
    """שינוי בודד שזוהה ב-sync. struct פשוט, אין צורך ב-dataclass."""

    __slots__ = ("booking_id", "event_id", "status", "start", "end", "updated_at")

    def __init__(
        self,
        booking_id: UUID,
        event_id: str,
        status: str,
        start: datetime | None,
        end: datetime | None,
        updated_at: datetime | None = None,
    ) -> None:
        self.booking_id = booking_id
        self.event_id = event_id
        self.status = status  # "cancelled" או "confirmed"/"tentative"
        self.start = start
        self.end = end
        # זמן השינוי האמיתי ב-Google (לא זמן עיבוד webhook). חשוב לסינון
        # post_meeting: ביטול שקרה לפני slot_end = הפגישה לא קרתה, גם אם
        # ה-webhook התעכב והגיע אחרי slot_end.
        self.updated_at = updated_at


async def sync_changes(
    db: AsyncSession,
) -> tuple[list[CalendarChange], str | None, str | None]:
    """
    מביא deltas מ-events.list עם sync_token, ומחזיר (changes, next_token, old_token).
    *אינו* persists את ה-token, *אינו* תופס lock — race correctness מושג ע"י:
    - CAS ב-persist_sync_token: WHERE על old_token, רק writer ראשון מקדם.
    - optimistic locking ב-_apply_reschedule: WHERE על start/end הקיימים.
    - _apply_cancellation אינדמפוטנטי דרך WHERE על status פעיל.

    כלומר: שני webhooks מקבילים יכולים לעבד אותם deltas, אבל ה-second
    תמיד יזהה שלא נשאר לו מה לעדכן (rowcount=0 בכל UPDATE) ולא ירשום
    activities כפולים. ה-CAS על ה-token מבטיח שלא נדרוס cursor חדש
    יותר בערך ישן.

    הגישה הזו פשוטה יותר מ"הgולdtag lock על פני apply" (שדורש single-tx
    apply + savepoints). ראה: docs/references/google-calendar-blueprint.md
    סעיף 6 — אצלנו ה-bookingId ב-extendedProperties.private (לא בdesc).

    יוצא מן הכלל: 410 GONE → ה-token הישן מת. עושים full re-sync,
    מחזירים ([], new_full_token, old_token). הקורא יעשה CAS אם DB עוד
    מחזיק את old_token.
    """
    creds = await get_credentials_or_404(db)
    row = await _load_row(db)
    if row is None:
        raise GoogleNotConnectedError()

    calendar_id = target_calendar_id(row)
    old_token = row.sync_token
    try:
        events, next_token = await asyncio.to_thread(
            _list_events_blocking, creds, calendar_id, old_token
        )
    except HttpError as e:
        if e.resp.status == 410:
            logger.warning("syncToken expired (410), resetting to full sync")
            new_token = await asyncio.to_thread(
                _initial_sync_token_blocking, creds, calendar_id
            )
            return ([], new_token, old_token)
        raise

    changes: list[CalendarChange] = []
    for ev in events:
        # רק אירועים שלנו — מזוהים ע"י bookingId ב-extendedProperties.private.
        # ראה: docs/references/google-calendar-blueprint.md סעיף 6 (המקור
        # מאחסן את העוגן ב-description; אצלנו ב-extendedProperties — יציב
        # יותר ל-parsing, לא נשבר אם נועה תערוך description ידנית).
        booking_id_str = (
            ev.get("extendedProperties", {})
            .get("private", {})
            .get("bookingId")
        )
        if not booking_id_str:
            continue
        try:
            booking_uuid = UUID(booking_id_str)
        except ValueError:
            continue

        status = ev.get("status", "confirmed")
        start_dt = _parse_event_dt(ev.get("start"))
        end_dt = _parse_event_dt(ev.get("end"))

        # `updated` הוא ISO 8601 string ב-RFC 3339; ב-Google זה תמיד aware UTC.
        updated_at: datetime | None = None
        updated_str = ev.get("updated")
        if updated_str:
            try:
                updated_at = datetime.fromisoformat(updated_str.replace("Z", "+00:00"))
            except ValueError:
                pass

        changes.append(
            CalendarChange(
                booking_id=booking_uuid,
                event_id=ev["id"],
                status=status,
                start=start_dt,
                end=end_dt,
                updated_at=updated_at,
            )
        )

    return (changes, next_token, old_token)


async def persist_sync_token(
    db: AsyncSession,
    new_token: str | None,
    expected_old: str | None,
) -> bool:
    """
    Compare-and-swap על sync_token: persists רק אם הערך הנוכחי תואם
    expected_old. מחזיר True אם הקדמנו, False אם webhook מקביל כבר
    הקדים אותנו.

    apply שלנו הוא idempotent (optimistic locking ב-_apply_reschedule
    ו-WHERE על status פעיל ב-_apply_cancellation), אז False כאן פירושו
    "עבדנו ללא הצורך" — לא איבוד נתונים.
    """
    stmt = update(GoogleCalendarCredentials).where(
        GoogleCalendarCredentials.id == _SINGLETON_ID
    )
    if expected_old is None:
        stmt = stmt.where(GoogleCalendarCredentials.sync_token.is_(None))
    else:
        stmt = stmt.where(
            GoogleCalendarCredentials.sync_token == expected_old
        )
    stmt = stmt.values(sync_token=new_token)

    result = await db.execute(stmt)
    await db.commit()
    return result.rowcount == 1


def _list_events_blocking(
    creds: Credentials, calendar_id: str, sync_token: str | None
) -> tuple[list[dict[str, Any]], str | None]:
    """blocking — נקרא רק מתוך asyncio.to_thread.
    מחזיר (events, nextSyncToken)."""
    service = _calendar_service(creds)
    all_events: list[dict[str, Any]] = []
    page_token: str | None = None
    next_sync_token: str | None = None
    while True:
        params: dict[str, Any] = {
            "calendarId": calendar_id,
            "showDeleted": True,
            "singleEvents": True,
            "maxResults": 2500,
        }
        if sync_token:
            params["syncToken"] = sync_token
        if page_token:
            params["pageToken"] = page_token
        result = service.events().list(**params).execute()
        all_events.extend(result.get("items", []))
        next_sync_token = result.get("nextSyncToken")
        page_token = result.get("nextPageToken")
        if not page_token:
            break
    return all_events, next_sync_token


def _parse_event_dt(field: dict[str, Any] | None) -> datetime | None:
    """parsing של start/end של אירוע ביומן (dateTime ISO או date ל-all-day)."""
    if not field:
        return None
    if "dateTime" in field:
        return datetime.fromisoformat(field["dateTime"])
    # all-day events — לא רלוונטיים לפגישות שלנו, נדלג
    return None


async def verify_watch_token(db: AsyncSession, received_token: str | None) -> bool:
    """
    מאמת ש-X-Goog-Channel-Token התקבל מ-Google תואם למה שיצרנו ב-create_watch.
    מגן מפני webhook spoofing.
    """
    if not received_token:
        return False
    row = await _load_row(db)
    if row is None or not row.watch_token_encrypted:
        return False
    try:
        expected = decrypt_secret(row.watch_token_encrypted)
    except Exception:
        return False
    return secrets.compare_digest(expected, received_token)
