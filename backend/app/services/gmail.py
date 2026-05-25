"""
Gmail service — OAuth flow + ניהול credentials + watch (Pub/Sub) — Stage 17.

מבוסס על הדפוס של google_calendar.py (פאזה 2). השכפול מכוון:
- OAuth flow כמעט זהה אבל scopes שונים (gmail vs calendar).
- Watch שונה מהותית: Gmail שולח ל-Pub/Sub topic, Calendar שולח ישירות
  לwebhook URL. ב-Gmail אין channel_id ב-response, ו-stop() לא דורשת id.
- Sync לפי history_id (לא sync_token).
- ensure_filter_label — Gmail-specific (Spec §20.11).

אין כאן classification או intake — אלה ב-commits 3/4 ו-4/4 של Stage 17/18.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.exceptions import AppException, ValidationError
from app.models.gmail_credentials import GmailCredentials
from app.services.google_calendar import (
    # שיתוף ה-state JWT encoding/decoding — אותו עיקרון (cookieless flow
    # ב-Render). פונקציות גנריות, לא calendar-specific.
    decode_oauth_state,
    encode_oauth_state,
    generate_code_verifier,
)
from app.utils.encryption import decrypt_secret, encrypt_secret

logger = logging.getLogger(__name__)

# gmail.readonly לקריאת מיילים, gmail.modify לתוויות (Spec §20.11).
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
]

_TOKEN_URI = "https://oauth2.googleapis.com/token"
_AUTH_URI = "https://accounts.google.com/o/oauth2/auth"

_SINGLETON_ID = 1

# Gmail watch מקסימום ~7 ימים. cron renewal יומי בודק <24h ומחדש.
_WATCH_RENEW_WITHIN = timedelta(hours=24)


# ===================== Exceptions =====================


class GmailNotConfiguredError(AppException):
    status_code = 503
    code = "gmail_not_configured"
    user_message = "האינטגרציה ל-Gmail לא הוגדרה. צרי קשר עם המתאם."


class GmailNotConnectedError(AppException):
    status_code = 409
    code = "gmail_not_connected"
    user_message = "Gmail לא מחובר. יש להתחבר ב-/settings."


class GmailAuthInvalidError(AppException):
    status_code = 401
    code = "gmail_auth_invalid"
    user_message = "החיבור ל-Gmail פג תוקף. יש להתחבר מחדש ב-/settings."


class GmailWatchNotConfiguredError(AppException):
    status_code = 503
    code = "gmail_watch_not_configured"
    user_message = "Pub/Sub topic לא מוגדר. צרי קשר עם המתאם."


# ===================== OAuth Flow =====================


def _client_config() -> dict[str, Any]:
    s = get_settings()
    if not (s.google_client_id and s.google_client_secret and s.gmail_redirect_uri):
        raise GmailNotConfiguredError()
    return {
        "web": {
            "client_id": s.google_client_id,
            "client_secret": s.google_client_secret,
            "auth_uri": _AUTH_URI,
            "token_uri": _TOKEN_URI,
            "redirect_uris": [s.gmail_redirect_uri],
        }
    }


def _new_flow() -> Flow:
    return Flow.from_client_config(
        client_config=_client_config(),
        scopes=SCOPES,
        redirect_uri=get_settings().gmail_redirect_uri,
    )


def build_auth_url(code_verifier: str) -> str:
    """
    מחזיר את ה-auth URL להפניית הbrowser ל-Google. state=JWT (אותו cookieless
    flow כמו Calendar — ראה google_calendar.encode_oauth_state).
    """
    flow = _new_flow()
    flow.code_verifier = code_verifier
    state = encode_oauth_state(code_verifier)
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        include_granted_scopes="true",
        state=state,
    )
    return auth_url


async def exchange_code_and_save(
    db: AsyncSession, code: str, code_verifier: str
) -> GmailCredentials:
    """מחליף את ה-code ל-tokens ושומר ל-DB. שולף את ה-email דרך users.getProfile."""
    flow = _new_flow()
    flow.code_verifier = code_verifier

    await asyncio.to_thread(flow.fetch_token, code=code)
    creds: Credentials = flow.credentials

    if not creds.refresh_token:
        raise ValidationError(
            "Google לא החזיר refresh_token. נתקי את האפליקציה בחשבון Google "
            "ולהתחבר מחדש."
        )

    email = await asyncio.to_thread(_fetch_account_email, creds)

    # stop_watch ישן אם יש (idempotent — לא נורא אם כשל)
    try:
        await stop_watch(db)
    except Exception:
        logger.exception("Failed to stop Gmail watch during reconnect (continuing)")

    await db.execute(
        delete(GmailCredentials).where(GmailCredentials.id == _SINGLETON_ID)
    )
    row = GmailCredentials(
        id=_SINGLETON_ID,
        google_account_email=email,
        refresh_token_encrypted=encrypt_secret(creds.refresh_token),
        access_token_encrypted=(
            encrypt_secret(creds.token) if creds.token else None
        ),
        token_expiry=creds.expiry.replace(tzinfo=timezone.utc) if creds.expiry else None,
        auth_invalid_at=None,
        owner_alert_sent_at=None,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    logger.info("Gmail connected as %s", email)

    # יצירת watch אוטומטית אם Pub/Sub topic + backend_url מוגדרים
    try:
        await create_watch(db)
    except GmailWatchNotConfiguredError:
        logger.info(
            "Skipping Gmail watch creation: GMAIL_PUBSUB_TOPIC not configured"
        )
    except Exception:
        logger.exception("Failed to create Gmail watch after OAuth")

    return row


def _fetch_account_email(creds: Credentials) -> str:
    """שליפה סינכרונית של email החשבון. נקראת בתוך asyncio.to_thread."""
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)
    profile = service.users().getProfile(userId="me").execute()
    return profile["emailAddress"]


# ===================== Credentials loading + refresh =====================


async def get_credentials_or_404(db: AsyncSession) -> Credentials:
    """
    טוען Gmail credentials, refresh אם פג, מטפל ב-RefreshError.
    זהה במבנה ל-google_calendar.get_credentials_or_404, scopes שונים.
    """
    _client_config()  # validate env vars early

    row = await _load_row(db)
    if row is None:
        raise GmailNotConnectedError()
    if row.auth_invalid_at is not None:
        raise GmailAuthInvalidError()

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
            await _mark_auth_invalid(row.owner_alert_sent_at is None)
            raise GmailAuthInvalidError() from None
        await _persist_refreshed_token(creds.token, creds.expiry)

    return creds


async def _load_row(db: AsyncSession) -> GmailCredentials | None:
    result = await db.execute(
        select(GmailCredentials)
        .where(GmailCredentials.id == _SINGLETON_ID)
        .execution_options(populate_existing=True)
    )
    return result.scalar_one_or_none()


async def _persist_refreshed_token(
    new_access_token: str, new_expiry: datetime | None
) -> None:
    """session נפרד — אותו הרציונל כמו ב-google_calendar (לא לסיים-commit
    transactions של callers — ראה הערה ב-google_calendar.py)."""
    from app.db.session import AsyncSessionLocal

    expiry_utc = (
        new_expiry.replace(tzinfo=timezone.utc) if new_expiry else None
    )
    async with AsyncSessionLocal() as fresh:
        await fresh.execute(
            update(GmailCredentials)
            .where(GmailCredentials.id == _SINGLETON_ID)
            .values(
                access_token_encrypted=encrypt_secret(new_access_token),
                token_expiry=expiry_utc,
            )
        )
        await fresh.commit()


async def _mark_auth_invalid(should_alert: bool) -> None:
    """
    מסמן auth_invalid_at ב-DB. אם should_alert — מנסה לשלוח לטלגרם
    *לפני* persistence של owner_alert_sent_at — אחרת כשל בטלגרם (network /
    bot token) משאיר את הflag set והמשתמש לא יקבל התראה לעולם.

    סדר הפעולות:
    1. שולח טלגרם (אם should_alert).
    2. אם הצליח — values כולל owner_alert_sent_at; אם נכשל — רק auth_invalid_at.
    3. commit אטומי ב-session נפרד.

    תוצאה: התראה תשלח שוב בקריאה הבאה ל-_mark_auth_invalid (כשrefresh
    הבא ייכשל). זה רצוי — owner צריך לדעת.
    """
    from app.db.session import AsyncSessionLocal

    now = datetime.now(timezone.utc)
    values: dict[str, datetime] = {"auth_invalid_at": now}

    alert_sent_ok = False
    if should_alert:
        from app.services import telegram as telegram_service

        try:
            alert_sent_ok = bool(
                await telegram_service.send_message(
                    "⚠️ <b>חיבור Gmail פג תוקף</b>\n"
                    "מיילים חדשים לא יסונכרנו עד שתתחברי מחדש ב-/settings.\n"
                    "ההודעה הזו תישלח פעם אחת בלבד."
                )
            )
        except Exception:
            logger.exception(
                "Failed to send Gmail auth-invalid Telegram alert"
            )
            alert_sent_ok = False

    if alert_sent_ok:
        values["owner_alert_sent_at"] = now

    async with AsyncSessionLocal() as fresh:
        await fresh.execute(
            update(GmailCredentials)
            .where(GmailCredentials.id == _SINGLETON_ID)
            .values(**values)
        )
        await fresh.commit()


# ===================== Status + Disconnect =====================


async def get_status(db: AsyncSession) -> dict[str, Any]:
    """תיאור החיבור לתצוגה ב-UI. filter_label_name מ-config (לא מ-DB —
    היא המקור היחיד; ה-cached_name משמש רק לזיהוי שינוי)."""
    row = await _load_row(db)
    s = get_settings()
    if row is None:
        return {
            "connected": False,
            "auth_invalid": False,
            "filter_label_name": s.ai_filter_label_name,
        }
    return {
        "connected": True,
        "google_account_email": row.google_account_email,
        "history_id": row.history_id,
        "watch_expiration": row.watch_expiration,
        "filter_label_name": s.ai_filter_label_name,
        "connected_at": row.created_at,
        "auth_invalid": row.auth_invalid_at is not None,
    }


async def disconnect(db: AsyncSession) -> None:
    """מנתק לחלוטין — עוצר watch ומוחק את שורת ה-credentials."""
    try:
        await stop_watch(db)
    except Exception:
        logger.exception("Failed to stop Gmail watch during disconnect")

    await db.execute(
        delete(GmailCredentials).where(GmailCredentials.id == _SINGLETON_ID)
    )
    await db.commit()
    logger.info("Gmail disconnected")


# ===================== Watch (Pub/Sub) =====================


async def create_watch(db: AsyncSession) -> dict[str, Any]:
    """
    יוצר watch על תיבת INBOX. שולח ל-Pub/Sub topic (לא ל-webhook ישיר —
    זה ההבדל מ-Calendar).

    Gmail מחזירה {historyId, expiration}. אנחנו שומרים אותם. ה-Push
    subscription של Pub/Sub מוגדרת ב-Google Cloud Console (לא בקוד) —
    היא זו שתעביר ל-/webhooks/gmail (commit 4/4).
    """
    s = get_settings()
    if not s.gmail_pubsub_topic:
        raise GmailWatchNotConfiguredError()

    creds = await get_credentials_or_404(db)

    result = await asyncio.to_thread(
        _watch_blocking, creds, s.gmail_pubsub_topic
    )

    # result: {"historyId": "...", "expiration": "epochMs"}
    expiration_ms = int(result.get("expiration", 0))
    expiration_dt = (
        datetime.fromtimestamp(expiration_ms / 1000, tz=timezone.utc)
        if expiration_ms
        else None
    )
    history_id = str(result.get("historyId", ""))

    await db.execute(
        update(GmailCredentials)
        .where(GmailCredentials.id == _SINGLETON_ID)
        .values(
            history_id=history_id or None,
            watch_expiration=expiration_dt,
        )
    )
    await db.commit()

    logger.info(
        "Gmail watch created: historyId=%s expires=%s",
        history_id,
        expiration_dt,
    )
    return {"history_id": history_id, "expiration": expiration_dt}


def _watch_blocking(
    creds: Credentials, topic_name: str
) -> dict[str, Any]:
    """blocking — נקרא רק מתוך asyncio.to_thread.
    labelIds=["INBOX"] מסנן רק מיילים חדשים שמגיעים ל-INBOX (לא promos/spam)."""
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)
    body = {
        "topicName": topic_name,
        "labelIds": ["INBOX"],
        "labelFilterAction": "include",
    }
    return service.users().watch(userId="me", body=body).execute()


async def stop_watch(db: AsyncSession) -> None:
    """עוצר את ה-watch (Gmail עוצרת את כל ה-watches של המשתמש בקריאה אחת
    — לא דורש id) ומנקה את שדות ה-watch ב-DB."""
    row = await _load_row(db)
    if row is None or row.watch_expiration is None:
        return
    try:
        creds = await get_credentials_or_404(db)
        await asyncio.to_thread(_stop_blocking, creds)
    except (GmailNotConnectedError, GmailAuthInvalidError):
        # לא מחובר/auth שבור — מנקים בכל מקרה את ה-DB
        pass
    except HttpError as e:
        # Gmail עשויה להחזיר 404 אם ה-watch כבר נעצר/פג. לא חוסם.
        logger.info("Gmail stop() returned HttpError (likely already stopped): %s", e)

    await db.execute(
        update(GmailCredentials)
        .where(GmailCredentials.id == _SINGLETON_ID)
        .values(history_id=None, watch_expiration=None)
    )
    await db.commit()


def _stop_blocking(creds: Credentials) -> None:
    """blocking — Gmail עוצרת את כל ה-watches בקריאה אחת."""
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)
    service.users().stop(userId="me").execute()


async def renew_watch_if_needed(db: AsyncSession) -> bool:
    """
    מחדש את ה-watch אם הוא פג תוך _WATCH_RENEW_WITHIN (24h) או כבר פג.
    מחזיר True אם חודש, False אם לא היה צורך.
    Gmail max ~7 ימים → cron יומי. נקרא מ-jobs/renew_gmail_watch.py.
    """
    row = await _load_row(db)
    if row is None:
        raise GmailNotConnectedError()

    now = datetime.now(timezone.utc)
    if row.watch_expiration is not None:
        if row.watch_expiration > now + _WATCH_RENEW_WITHIN:
            return False  # עוד תקף

    await create_watch(db)
    return True


# ===================== Filter label (Spec §20.11) =====================


async def ensure_filter_label(db: AsyncSession) -> str:
    """
    מוודא שתווית AI_FILTER_LABEL_NAME קיימת ב-Gmail ומחזיר את label.id.

    Cache invalidation: אם filter_label_name_cached ב-DB שונה מהשם הנוכחי
    ב-env (`AI_FILTER_LABEL_NAME` השתנה) — יוצר תווית חדשה. ה-admin
    אחראי לטפל בהעברה ידנית של מיילים קיימים (Spec §20.11 admin note).

    משמש ב-commit 4/4 כשclassifier מסמן ספאם.
    """
    s = get_settings()
    target_name = s.ai_filter_label_name

    row = await _load_row(db)
    if row is None:
        raise GmailNotConnectedError()

    # cache hit — name לא השתנה ויש id שמור
    if (
        row.filter_label_id
        and row.filter_label_name_cached == target_name
    ):
        return row.filter_label_id

    creds = await get_credentials_or_404(db)
    label_id = await asyncio.to_thread(
        _ensure_label_blocking, creds, target_name
    )

    await db.execute(
        update(GmailCredentials)
        .where(GmailCredentials.id == _SINGLETON_ID)
        .values(
            filter_label_id=label_id,
            filter_label_name_cached=target_name,
        )
    )
    await db.commit()
    return label_id


def _ensure_label_blocking(creds: Credentials, name: str) -> str:
    """מוצא תווית בשם הנתון; יוצר אם לא קיימת. מחזיר label.id."""
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)
    labels_resp = service.users().labels().list(userId="me").execute()
    for label in labels_resp.get("labels", []):
        if label.get("name") == name:
            return label["id"]
    created = (
        service.users()
        .labels()
        .create(
            userId="me",
            body={
                "name": name,
                "labelListVisibility": "labelShow",
                "messageListVisibility": "show",
            },
        )
        .execute()
    )
    return created["id"]
