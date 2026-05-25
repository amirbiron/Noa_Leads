"""
Webhook עבור push notifications של Gmail (Phase 3 Stage 18 commit 4/4).

Gmail שולח הודעה ל-Pub/Sub topic על כל שינוי במייל; Pub/Sub Push מגיע
אלינו כ-POST עם OIDC JWT ב-Authorization header.

מבנה ה-payload (Pub/Sub Push):
    {
      "message": {
        "data": "base64(json)",  # {"emailAddress": "...", "historyId": "12345"}
        "messageId": "...",
        "publishTime": "..."
      },
      "subscription": "..."
    }

אבטחה:
- חתימת ה-JWT מאומתת מול Google certificates (verify_oauth2_token).
- aud חייב להתאים ל-BACKEND_URL/webhooks/gmail.
- אם GMAIL_PUBSUB_SERVICE_ACCOUNT מוגדר — גם email של ה-token מאומת.
- כשל אימות → 200 OK בלי לעבד (לא חושפים failure ל-spoofers).

ביצועים:
- ack מהיר (204) — היסטוריה נסרקת ברקע דרך BackgroundTasks.
  Pub/Sub Push דורש ack תוך 10s (default) אחרת retry.
"""

from __future__ import annotations

import base64
import binascii
import json
import logging

from fastapi import APIRouter, BackgroundTasks, Header, Request, Response
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2 import id_token

from app.config import get_settings
from app.services import gmail_intake

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/gmail")
async def gmail_webhook(
    request: Request,
    background: BackgroundTasks,
    authorization: str | None = Header(default=None),
) -> Response:
    """
    מקבל push מ-Pub/Sub. אימות JWT → decode envelope → background task.
    תמיד מחזיר 2xx (גם בכשל אימות) — לא לעורר retry של Pub/Sub ולא לחשוף
    האם ה-endpoint קיים ל-spoofers.
    """
    settings = get_settings()

    # 1. אימות OIDC JWT. כשל → 200 (אך לא מעבד).
    if not _verify_pubsub_jwt(authorization, settings):
        return Response(status_code=200)

    # 2. parse envelope. malformed → 200 (לא לחזור — Pub/Sub יחזור אחרת).
    try:
        body = await request.json()
    except (json.JSONDecodeError, ValueError):
        logger.warning("Gmail webhook: malformed JSON body")
        return Response(status_code=200)

    history_id = _decode_envelope(body)
    if history_id is None:
        return Response(status_code=200)

    # 3. עיבוד ברקע. Pub/Sub מצפה ל-ack מהיר.
    background.add_task(_run_intake_in_new_session, history_id)
    return Response(status_code=204)


def _verify_pubsub_jwt(
    authorization: str | None, settings
) -> bool:
    """
    מאמת OIDC JWT שנשלח ע"י Pub/Sub Push.
    - חתימה: verify_oauth2_token מוודא חתימה ע"י Google.
    - aud: חייב להתאים לכתובת ה-webhook המלאה.
    - email (אופציונלי): אם GMAIL_PUBSUB_SERVICE_ACCOUNT מוגדר.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        logger.warning("Gmail webhook: missing Bearer token")
        return False

    token = authorization.split(" ", 1)[1].strip()
    if not token:
        return False

    if not settings.backend_url:
        # אי-אפשר לאמת aud בלי backend_url. מסרבים — adminstrator חייב להגדיר.
        logger.error(
            "Gmail webhook: BACKEND_URL not configured — cannot verify Pub/Sub JWT"
        )
        return False

    expected_audience = settings.backend_url.rstrip("/") + "/webhooks/gmail"

    try:
        claims = id_token.verify_oauth2_token(
            token, GoogleAuthRequest(), audience=expected_audience
        )
    except ValueError as e:
        # signature invalid / expired / aud mismatch
        logger.warning("Gmail webhook: JWT verification failed: %s", e)
        return False

    # iss חייב להיות Google
    issuer = claims.get("iss", "")
    if issuer not in ("https://accounts.google.com", "accounts.google.com"):
        logger.warning("Gmail webhook: unexpected iss=%s", issuer)
        return False

    # אופציה: אימות email של ה-service account
    expected_sa = settings.gmail_pubsub_service_account
    if expected_sa:
        token_email = claims.get("email", "")
        token_email_verified = claims.get("email_verified", False)
        if not token_email_verified or token_email != expected_sa:
            logger.warning(
                "Gmail webhook: SA mismatch (got %s, expected %s, verified=%s)",
                token_email,
                expected_sa,
                token_email_verified,
            )
            return False

    return True


def _decode_envelope(body: dict) -> int | None:
    """
    Pub/Sub Push envelope → historyId (int).
    `body["message"]["data"]` = base64 url-safe JSON עם emailAddress + historyId.
    """
    message = body.get("message")
    if not isinstance(message, dict):
        logger.warning("Gmail webhook: envelope missing 'message'")
        return None

    data_b64 = message.get("data")
    if not data_b64:
        # Pub/Sub יכול לשלוח keep-alive ללא data. ack בשקט.
        return None

    try:
        # urlsafe_b64decode מקבל גם padding לא מלא אם נוסיף '===' (מתעלם מעודף).
        decoded_bytes = base64.urlsafe_b64decode(data_b64 + "===")
        payload = json.loads(decoded_bytes.decode("utf-8"))
    except (binascii.Error, ValueError, UnicodeDecodeError) as e:
        logger.warning("Gmail webhook: failed to decode data: %s", e)
        return None

    history_id_str = payload.get("historyId")
    if history_id_str is None:
        logger.warning("Gmail webhook: payload missing historyId: %s", payload)
        return None

    try:
        return int(history_id_str)
    except (TypeError, ValueError):
        logger.warning("Gmail webhook: bad historyId value %r", history_id_str)
        return None


async def _run_intake_in_new_session(history_id: int) -> None:
    """רץ ברקע, פותח session משלו (ה-request DbSession כבר נסגר)."""
    try:
        await gmail_intake.process_gmail_history(history_id)
    except Exception:
        logger.exception(
            "Gmail intake failed for history_id=%d", history_id
        )
