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
import secrets
from datetime import datetime, timezone
from typing import Any

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from sqlalchemy import delete, select
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


def build_auth_url(code_verifier: str) -> tuple[str, str]:
    """
    מחזיר (auth_url, state). הקורא שומר state + code_verifier ב-session
    (cookie חתום). בקאלבק נטען אותם בחזרה לאימות.
    """
    flow = _new_flow()
    flow.code_verifier = code_verifier
    auth_url, state = flow.authorization_url(
        # offline → מקבלים גם refresh_token (לא רק access)
        access_type="offline",
        # prompt=consent → מבטיח refresh_token גם בחיבור חוזר
        prompt="consent",
        include_granted_scopes="true",
    )
    return auth_url, state


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

    # שמירה ל-DB (upsert: delete + insert, פשוט יותר מ-ON CONFLICT עם CHECK)
    await db.execute(
        delete(GoogleCalendarCredentials).where(
            GoogleCalendarCredentials.id == _SINGLETON_ID
        )
    )
    row = GoogleCalendarCredentials(
        id=_SINGLETON_ID,
        google_account_email=email,
        calendar_id="primary",
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
    return row


def _fetch_account_info(creds: Credentials) -> tuple[str, str]:
    """שליפה סינכרונית של email + timezone. נקראת בתוך asyncio.to_thread."""
    service = build("calendar", "v3", credentials=creds, cache_discovery=False)
    cal = service.calendars().get(calendarId="primary").execute()
    # id של primary calendar = אימייל החשבון
    return cal["id"], cal.get("timeZone", "Asia/Jerusalem")


# ===================== Credentials loading + refresh =====================


async def get_credentials_or_404(db: AsyncSession) -> Credentials:
    """
    טוען credentials מה-DB, מבצע refresh אם פג, מטפל ב-RefreshError.
    זורק:
    - GoogleNotConnectedError אם אין שורה ב-DB
    - GoogleAuthInvalidError אם auth_invalid_at מסומן או refresh נכשל
    """
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
            await _mark_auth_invalid(db, row)
            raise GoogleAuthInvalidError() from None
        # שומרים את ה-access_token החדש (לא מתעדכן refresh_token בדרך כלל)
        row.access_token_encrypted = encrypt_secret(creds.token)
        row.token_expiry = (
            creds.expiry.replace(tzinfo=timezone.utc) if creds.expiry else None
        )
        await db.commit()

    return creds


async def _load_row(db: AsyncSession) -> GoogleCalendarCredentials | None:
    result = await db.execute(
        select(GoogleCalendarCredentials)
        .where(GoogleCalendarCredentials.id == _SINGLETON_ID)
        .execution_options(populate_existing=True)
    )
    return result.scalar_one_or_none()


async def _mark_auth_invalid(
    db: AsyncSession, row: GoogleCalendarCredentials
) -> None:
    """
    מסמן את ה-credentials כשגויים ושולח התראה חד-פעמית לטלגרם.
    owner_alert_sent_at מונע ספאם בכל ניסיון refresh עוקב.
    """
    now = datetime.now(timezone.utc)
    row.auth_invalid_at = now
    should_alert = row.owner_alert_sent_at is None
    if should_alert:
        row.owner_alert_sent_at = now
    await db.commit()

    if should_alert:
        # local import — telegram עשוי לא להיות מוגדר ב-dev
        from app.services import telegram as telegram_service

        await telegram_service.send_message(
            "⚠️ <b>חיבור היומן ל-Google פג תוקף</b>\n"
            "תורים חדשים לא יסונכרנו ליומן עד שתתחברי מחדש ב-/settings.\n"
            "ההודעה הזו תישלח פעם אחת בלבד."
        )


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
    }


async def disconnect(db: AsyncSession) -> None:
    """מנתק לחלוטין — מוחק את שורת ה-credentials."""
    await db.execute(
        delete(GoogleCalendarCredentials).where(
            GoogleCalendarCredentials.id == _SINGLETON_ID
        )
    )
    await db.commit()
    logger.info("Google Calendar disconnected")
