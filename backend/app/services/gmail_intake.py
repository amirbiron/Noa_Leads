"""
Gmail intake pipeline — Phase 3 Stage 18 commit 4/4.

The click moment של Phase 3: webhook → fetch → classify → extract →
create lead. כל ה-pieces מ-commits 1-3/4 מתחברים כאן.

ה-pipeline אחראי על:
- fetching מסרים חדשים מ-Gmail מאז history_id שמור.
- per-message: idempotency (gmail_message_id UNIQUE), heuristic filter,
  cleaning, classify, extract, lead creation.
- error handling: AIRateLimitError ו-AIError → email_messages row עם
  classification_retry_count, cron retry. אחרי MAX → ליד עם
  manual_review_needed.

לא כאן: ה-webhook route (gmail_webhook.py), ה-cron (retry_pending_classification.py).
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
from typing import Any

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.constants import (
    SERVICE_SUBTYPES,
    PreferredContact,
    ServiceCategory,
    SourceChannel,
)
from app.db.session import AsyncSessionLocal
from app.models.email_message import (
    PROCESSING_STATUS_HEURISTIC_SPAM,
    PROCESSING_STATUS_LEAD_CREATED,
    PROCESSING_STATUS_MANUAL_REVIEW,
    PROCESSING_STATUS_NOT_BUSINESS,
    PROCESSING_STATUS_PENDING,
    EmailMessage,
)
from app.models.gmail_credentials import GmailCredentials
from app.schemas.lead import LeadCreate
from app.services import ai, gmail, leads as leads_service
from app.utils.email_cleaning import clean_email_body_for_ai
from app.utils.email_filtering import should_skip_ai_classification
from app.utils.phone import normalize_for_storage

logger = logging.getLogger(__name__)


# ===== Public: webhook entry point =====


async def process_gmail_history(notify_history_id: int) -> None:
    """
    נקראת מ-background task של ה-webhook. סורקת את ההיסטוריה מאז
    history_id שמור, מעבדת כל מסר חדש. silent on missing credentials
    (webhook יכול להגיע אחרי disconnect).
    """
    async with AsyncSessionLocal() as db:
        row = await gmail._load_row(db)
        if row is None:
            logger.warning(
                "Gmail webhook received but no credentials in DB (notify=%d)",
                notify_history_id,
            )
            return

        # שמירת ה-history_id המקורי (יכול להיות None). expected_old המקורי
        # נדרש ל-CAS — אסור להחליף ב-str(notify_history_id) כי אז ה-WHERE
        # היה `history_id = 'X'` ולא יתפוס שורה עם NULL (Postgres NULL != X).
        # תיקון bugbot: כש-row.history_id=NULL (אחרי _reset_history_id או
        # לפני watch ראשון), CAS היה rowcount=0 וה-cursor היה נשאר NULL לעד.
        original_history_id: str | None = row.history_id

        # ל-Gmail API צריך start_history_id non-empty. אם NULL — נתחיל
        # מ-notify_history_id (לא נפספס שום דבר חדש אבל גם לא נשלוף משהו
        # ישן יותר; ה-message שגרם ל-webhook עצמו לא מוחזר ע"י history.list
        # כש-startHistoryId == שלו, אבל webhook הבא יקבל אותו).
        start_history_id = original_history_id or str(notify_history_id)

        try:
            creds = await gmail.get_credentials_or_404(db)
        except (gmail.GmailNotConnectedError, gmail.GmailAuthInvalidError):
            logger.warning("Gmail credentials invalid — skipping history process")
            return

        try:
            new_msg_ids = await asyncio.to_thread(
                _fetch_new_message_ids, creds, start_history_id
            )
        except HttpError as e:
            # 404 = historyId too old (Gmail keeps ~7 days). Reset by
            # calling watch again — ה-cron renew_gmail_watch יקבל historyId טרי.
            if e.resp.status == 404:
                logger.warning(
                    "history_id %s too old (Gmail HTTP 404). Will reset via watch.",
                    start_history_id,
                )
                await _reset_history_id(db)
                return
            raise

        logger.info(
            "Gmail history: %d new message(s) since history_id=%s",
            len(new_msg_ids),
            start_history_id,
        )

        for msg_id in new_msg_ids:
            try:
                await process_incoming_message(db, msg_id)
            except Exception:
                # שגיאה ב-message בודד לא משפיעה על השאר
                logger.exception("Failed to process Gmail message %s", msg_id)

        # advance history_id (CAS — לא לדרוס webhook מקביל שכבר התקדם).
        # מעבירים את original_history_id (יכול להיות None), לא את start_history_id
        # — כי start עבר fallback ל-notify_history_id וה-CAS חייב לתאר את המצב
        # האמיתי בDB.
        await _persist_history_id(
            db, new_id=str(notify_history_id), expected_old=original_history_id
        )


# ===== Public: per-message processing =====


async def process_incoming_message(
    db: AsyncSession, gmail_message_id: str
) -> EmailMessage | None:
    """
    מעבדת מסר Gmail בודד דרך כל ה-pipeline. מחזירה את EmailMessage row
    (או None אם המסר נדלג בגלל idempotency).

    יוצרת לכל היותר ליד אחד. שגיאות AI לא מעיפות exception — נשמרות
    כ-classification_retry_count ב-email_messages ו-cron יטפל.
    """
    # idempotency: אותו gmail_message_id מטופל פעם אחת בלבד.
    existing = await db.execute(
        select(EmailMessage).where(
            EmailMessage.gmail_message_id == gmail_message_id
        )
    )
    if existing.scalar_one_or_none() is not None:
        return None

    try:
        creds = await gmail.get_credentials_or_404(db)
    except (gmail.GmailNotConnectedError, gmail.GmailAuthInvalidError):
        logger.warning("Cannot process msg %s — Gmail credentials invalid", gmail_message_id)
        return None

    raw_msg = await asyncio.to_thread(_fetch_message_blocking, creds, gmail_message_id)
    if raw_msg is None:
        return None  # 404 = הודעה נמחקה לפני שעיבדנו

    headers = _extract_headers(raw_msg.get("payload", {}))
    from_addr = headers.get("from")
    to_addr = headers.get("to")
    subject = headers.get("subject") or ""
    raw_body = _extract_body(raw_msg.get("payload", {}))
    received_at_ms = int(raw_msg.get("internalDate") or 0)
    received_at = (
        _ms_to_datetime(received_at_ms) if received_at_ms else None
    )

    # heuristic spam filter — חוסך AI call אם מקור אוטומטי + אין סימני פנייה אישית.
    if should_skip_ai_classification(from_addr, headers, raw_body):
        logger.info("Skipping AI for spam-heuristic msg %s from=%s", gmail_message_id, from_addr)
        await _apply_filter_label(db, gmail_message_id, creds)
        # processing_status=heuristic_spam → cron יידלג עליה.
        return await _save_email_message(
            db,
            gmail_message_id=gmail_message_id,
            from_addr=from_addr,
            to_addr=to_addr,
            subject=subject,
            raw_body=raw_body,
            cleaned_text=None,
            cleaning_metadata={"skipped_reason": "heuristic_spam"},
            received_at=received_at,
            lead_id=None,
            processing_status=PROCESSING_STATUS_HEURISTIC_SPAM,
        )

    # cleaning + classification
    cleaned_text, cleaning_meta = clean_email_body_for_ai(raw_body, "classification")

    email_msg = await _save_email_message(
        db,
        gmail_message_id=gmail_message_id,
        from_addr=from_addr,
        to_addr=to_addr,
        subject=subject,
        raw_body=raw_body,
        cleaned_text=cleaned_text,
        cleaning_metadata=cleaning_meta,
        received_at=received_at,
        lead_id=None,
    )
    if email_msg is None:
        return None  # IntegrityError בגלל race — אחר כבר טיפל

    # classify + extract + create lead. אם נכשל — email_msg נשאר עם
    # lead_id=NULL ו-classification_retry_count=0, cron יטפל.
    await _classify_extract_and_create_lead(db, email_msg, subject, cleaned_text)
    return email_msg


async def retry_pending_email(db: AsyncSession, email_msg: EmailMessage) -> None:
    """
    נקראת מ-cron retry_pending_classification. מנסה שוב classify+extract.
    אם retry_count מגיע ל-MAX → יצירת ליד עם manual_review_needed=True.

    הערה על heuristic spam filter: לא מורצים שוב כאן (bugbot finding 2).
    הסיבה — ה-heuristic רץ ב-process_incoming_message *לפני* שמירה כ-pending,
    ולכן כל row שמגיע לפה בוודאות עבר את הסינון. ה-heuristic גם דטרמיניסטי
    על אותו from/headers/body, ועל retry אין לנו את ה-headers המלאים בDB
    (רק from_address). מבחירה: לא לקרוא ל-Gmail API שוב רק כדי להריץ heuristic
    זהה.
    """
    max_retries = get_settings().ai_max_classification_retries

    # כבר מעבר ל-MAX — מצב recovery (manual_review_lead נכשל בעבר).
    # bugbot finding 1: לפני התיקון, count היה מתקדם ל-MAX לפני
    # _create_manual_review_lead; אם הוא היה זורק exception, ה-row היה
    # נשאר 'pending' עם count >= MAX, וה-cron (שסיננה גם לפי `< MAX`)
    # לא היה אוסף אותו לעולם. עכשיו: cron אוספת לפי processing_status
    # בלבד, וה-MAX check עבר לתוך הפונקציה הזו.
    if email_msg.classification_retry_count >= max_retries:
        logger.warning(
            "Email msg %s already at MAX (%d) — retrying manual_review_needed lead creation",
            email_msg.id,
            max_retries,
        )
        await _create_manual_review_lead(db, email_msg)
        return

    # מעלים את ה-count לפני הניסיון. אם הניסיון קורס באמצע (process killed),
    # ה-count כבר התקדם — לא תקועים ב-loop של אותו ניסיון נצחי. אם נכשל
    # ב-AIError, gracefully נשאר 'pending' עם count חדש.
    email_msg.classification_retry_count += 1
    await db.commit()
    await db.refresh(email_msg)

    cleaned_text = email_msg.cleaned_text or ""
    subject = email_msg.subject or ""

    if email_msg.classification_retry_count >= max_retries:
        # הגענו ל-MAX אחרי ה-increment הנוכחי — manual_review.
        # אם הקריאה תזרוק exception, ה-row יישאר 'pending' עם count=MAX,
        # והענף למעלה (count>=MAX) יטפל בהרצה הבאה.
        logger.warning(
            "Email msg %s reached MAX retries (%d) — creating lead with manual_review_needed",
            email_msg.id,
            max_retries,
        )
        await _create_manual_review_lead(db, email_msg)
        return

    await _classify_extract_and_create_lead(db, email_msg, subject, cleaned_text)


# ===== Internal: classification + extraction + lead creation =====


async def _classify_extract_and_create_lead(
    db: AsyncSession,
    email_msg: EmailMessage,
    subject: str,
    cleaned_text: str,
) -> None:
    """
    Heart of the pipeline. classify → if business: extract → create lead.
    שגיאות AI לא מעיפות exception — email_msg נשאר ללא lead_id ו-cron
    יטפל.
    """
    try:
        classification = await ai.classify_email(
            subject=subject, cleaned_body=cleaned_text
        )
    except ai.AIRateLimitError:
        logger.info("classify rate-limited for msg %s — will retry via cron", email_msg.id)
        return
    except ai.AIError as e:
        logger.warning("classify failed for msg %s: %s — will retry via cron", email_msg.id, e)
        return

    if not classification.is_business:
        # לסמן ב-Gmail + לסיים. הליד לא נוצר. ה-email_msg נשאר עם
        # cleaning_metadata + classification result ב-log.
        logger.info(
            "msg %s classified as NOT business (confidence=%.2f) — labeling in Gmail",
            email_msg.id,
            classification.confidence,
        )
        try:
            creds = await gmail.get_credentials_or_404(db)
            await _apply_filter_label(db, email_msg.gmail_message_id, creds)
        except Exception:
            logger.exception("Failed to apply filter label to msg %s", email_msg.id)
        # processing_status=not_business → terminal, cron יידלג. בלי השדה
        # הזה ה-cron היה סורק אותה לעד (lead_id IS NULL לנצח).
        await db.execute(
            update(EmailMessage)
            .where(EmailMessage.id == email_msg.id)
            .values(processing_status=PROCESSING_STATUS_NOT_BUSINESS)
        )
        await db.commit()
        return

    # is_business=True — חולץ פרטים
    try:
        draft = await ai.extract_lead_from_email(
            subject=subject, cleaned_body=cleaned_text
        )
    except ai.AIRateLimitError:
        logger.info("extract rate-limited for msg %s — will retry via cron", email_msg.id)
        return
    except ai.AIError as e:
        logger.warning("extract failed for msg %s: %s — will retry via cron", email_msg.id, e)
        return

    # יוצרים ליד. confidence < threshold → סימון low_confidence_classification.
    settings = get_settings()
    low_conf = classification.confidence < settings.ai_classify_confidence_threshold

    lead = await _create_lead_from_draft(
        db,
        email_msg=email_msg,
        draft=draft,
        ai_reason=classification.reason,
        ai_confidence=classification.confidence,
        low_confidence=low_conf,
        manual_review=False,
    )
    logger.info(
        "msg %s → lead %s created (confidence=%.2f, low_conf=%s)",
        email_msg.id,
        lead.id,
        classification.confidence,
        low_conf,
    )


async def _create_lead_from_draft(
    db: AsyncSession,
    *,
    email_msg: EmailMessage,
    draft: ai.LeadDraft,
    ai_reason: str | None,
    ai_confidence: float | None,
    low_confidence: bool,
    manual_review: bool,
) -> Any:
    """ממיר LeadDraft + email_msg → LeadCreate, יוצר ליד, מקשר email_msg.lead_id.

    Validation:
    - service_category: רק אם ערך תקף ב-ServiceCategory enum.
    - service_subtype: רק אם ב-SERVICE_SUBTYPES של הקטגוריה.
    - phone: normalize_for_storage.
    """
    category_str = draft.service_category
    category_enum: ServiceCategory | None = None
    if category_str and category_str in {s.value for s in ServiceCategory}:
        category_enum = ServiceCategory(category_str)

    subtype: str | None = None
    if (
        category_enum is not None
        and draft.service_subtype
        and draft.service_subtype in SERVICE_SUBTYPES.get(category_enum, [])
    ):
        subtype = draft.service_subtype

    # phone: AI עלול להחזיר מספר חלקי/לא תקין. ValueError ב-normalize →
    # נשמרים בלי טלפון, נועה תשלים. עדיף ליד עם שדה ריק מאשר אובדן ליד.
    phone: str | None = None
    if draft.phone:
        try:
            phone = normalize_for_storage(draft.phone)
        except ValueError:
            logger.info("Ignoring invalid phone from AI draft: %r", draft.phone)

    # email: אם AI החזיר string שלא תקין כ-EmailStr, LeadCreate ייכשל.
    # נסה ליצור LeadCreate; אם email שובר ולידציה, חזור בלי email.
    #
    # preferred_contact=EMAIL: לקוח שפנה דרך Gmail רוצה תגובה בערוץ שלו.
    # ה-default של LeadCreate הוא WHATSAPP — בלי הקביעה המפורשת כאן, ליד
    # ממייל היה מקבל preferred=WHATSAPP וה-DynamicActionButton היה מציע
    # "שלחי תבנית פתיחה" (WA) במקום "השב במייל".
    try:
        lead_create = LeadCreate(
            full_name=draft.full_name or "ללא שם",
            phone=phone,
            email=draft.email,
            service_category=category_enum,
            service_subtype=subtype,
            source_channel=SourceChannel.EMAIL,
            source_detail=draft.subject_summary,
            preferred_contact=PreferredContact.EMAIL,
        )
    except ValidationError:
        logger.info(
            "LeadCreate validation failed with draft email %r — retrying without email",
            draft.email,
        )
        lead_create = LeadCreate(
            full_name=draft.full_name or "ללא שם",
            phone=phone,
            email=None,
            service_category=category_enum,
            service_subtype=subtype,
            source_channel=SourceChannel.EMAIL,
            source_detail=draft.subject_summary,
            preferred_contact=PreferredContact.EMAIL,
        )

    # commit=False כדי שנוסיף activity + נעדכן email_msg.lead_id באטומיות
    lead = await leads_service.create_lead(
        db, lead_create, current_user_id=None, commit=False
    )

    # סימוני AI
    update_values: dict[str, Any] = {}
    if low_confidence:
        update_values["low_confidence_classification"] = True
    if manual_review:
        update_values["manual_review_needed"] = True
    if update_values:
        from app.models.lead import Lead
        await db.execute(
            update(Lead).where(Lead.id == lead.id).values(**update_values)
        )

    # קשירת email_msg → lead + סימון processing_status סופי. בלי
    # processing_status המסלול של manual_review (lead_id IS NOT NULL אבל
    # נוצר אחרי MAX retries) היה זהה ל-lead_created — מקובל מהפרספקטיבה
    # של ה-cron, אבל מאבד מידע ל-analytics/dashboard בעתיד.
    final_status = (
        PROCESSING_STATUS_MANUAL_REVIEW if manual_review
        else PROCESSING_STATUS_LEAD_CREATED
    )
    await db.execute(
        update(EmailMessage)
        .where(EmailMessage.id == email_msg.id)
        .values(lead_id=lead.id, processing_status=final_status)
    )

    # activity record — מציג subject + תחילת body של המייל ב-timeline.
    # *לא* את ה-classifier reason ("פנייה ישירה...") — טאוטולוגי לליד
    # שכבר נוצר (היו עוברים את ה-classifier ולא היו ליד). נועה צריכה
    # תוכן ספציפי, לא תיוג AI שמשוכפל את הקטגוריה שכבר בכרטיס.
    # ai_reason/ai_confidence נשארים ב-metadata ל-debug.
    if email_msg.subject or email_msg.cleaned_text:
        from app.constants import ActivityType
        from app.services.activities import log_activity
        await log_activity(
            db,
            lead_id=lead.id,
            activity_type=ActivityType.LEAD_CREATED,
            performed_by=None,
            content=_build_email_activity_content(email_msg),
            metadata={
                "source": "gmail_intake",
                "ai_reason": ai_reason,
                "ai_confidence": ai_confidence,
                "low_confidence": low_confidence,
                "manual_review_needed": manual_review,
            },
        )

    await db.commit()
    await db.refresh(lead)
    return lead


async def _create_manual_review_lead(
    db: AsyncSession, email_msg: EmailMessage
) -> None:
    """
    Last resort כש-AI נכשל MAX פעמים. יוצר ליד מינימלי עם
    manual_review_needed=True, full_name מ-From header.
    נועה תשלים פרטים.
    """
    full_name = _name_from_address(email_msg.from_address) or "לבדיקה ידנית"
    draft = ai.LeadDraft(
        full_name=full_name,
        email=email_msg.from_address,
        subject_summary=(email_msg.subject or "")[:200] or "מייל שהגיע ללא סיווג AI",
    )
    await _create_lead_from_draft(
        db,
        email_msg=email_msg,
        draft=draft,
        ai_reason=None,
        ai_confidence=None,
        low_confidence=False,
        manual_review=True,
    )


# ===== Internal: Gmail API helpers =====


def _fetch_new_message_ids(creds, start_history_id: str) -> list[str]:
    """blocking — מחזיר רק msg_ids של messagesAdded (לא labelChanges).
    מסונן לקטגוריית primary INBOX (labelIds=["INBOX"])."""
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)
    msg_ids: list[str] = []
    page_token: str | None = None
    while True:
        request = service.users().history().list(
            userId="me",
            startHistoryId=start_history_id,
            historyTypes=["messageAdded"],
            labelId="INBOX",
            pageToken=page_token,
        )
        response = request.execute()
        for history_entry in response.get("history", []):
            for added in history_entry.get("messagesAdded", []):
                m = added.get("message", {})
                mid = m.get("id")
                if mid:
                    msg_ids.append(mid)
        page_token = response.get("nextPageToken")
        if not page_token:
            break
    # dedup — אם אותה message מופיעה ב-2 history entries
    seen: set[str] = set()
    result: list[str] = []
    for mid in msg_ids:
        if mid not in seen:
            seen.add(mid)
            result.append(mid)
    return result


def _fetch_message_blocking(creds, msg_id: str) -> dict | None:
    """blocking — fetch מלא של message. None אם 404 (נמחק)."""
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)
    try:
        return service.users().messages().get(
            userId="me", id=msg_id, format="full"
        ).execute()
    except HttpError as e:
        if e.resp.status == 404:
            return None
        raise


def _extract_headers(payload: dict) -> dict[str, str]:
    """payload.headers הוא list של {"name": ..., "value": ...}. הופך ל-dict."""
    result: dict[str, str] = {}
    for h in payload.get("headers", []):
        name = h.get("name", "").lower()
        value = h.get("value", "")
        if name:
            result[name] = value
    return result


def _extract_body(payload: dict) -> str:
    """traversal של multipart. עדיפות ל-text/html, fallback ל-text/plain.

    Gmail message payload יכול להיות:
    - leaf (mimeType=text/...) — body.data base64 url-safe
    - multipart — parts[] רקורסיבי
    """
    html_body: str | None = None
    text_body: str | None = None

    def visit(part: dict) -> None:
        nonlocal html_body, text_body
        mime = part.get("mimeType", "")
        body = part.get("body", {})
        data = body.get("data")
        if data:
            decoded = base64.urlsafe_b64decode(data + "===").decode("utf-8", errors="replace")
            if mime == "text/html" and html_body is None:
                html_body = decoded
            elif mime == "text/plain" and text_body is None:
                text_body = decoded
        for child in part.get("parts", []):
            visit(child)

    visit(payload)
    return html_body or text_body or ""


# ===== Internal: DB helpers =====


async def _save_email_message(
    db: AsyncSession,
    *,
    gmail_message_id: str,
    from_addr: str | None,
    to_addr: str | None,
    subject: str,
    raw_body: str,
    cleaned_text: str | None,
    cleaning_metadata: dict | None,
    received_at,
    lead_id,
    processing_status: str = PROCESSING_STATUS_PENDING,
) -> EmailMessage | None:
    """INSERT email_message. UNIQUE על gmail_message_id → race ייתפס.

    processing_status חייב להיות מצוין במפורש בקריאות שמייצגות מצב סופי
    (heuristic_spam, lead_created, ...) — אחרת ה-cron יסרוק את הרשומה
    שוב ושוב.
    """
    msg = EmailMessage(
        lead_id=lead_id,
        gmail_message_id=gmail_message_id,
        direction="inbound",
        from_address=(from_addr or "")[:200] or None,
        to_address=(to_addr or "")[:200] or None,
        subject=subject or None,
        raw_html=raw_body or None,
        cleaned_text=cleaned_text,
        cleaning_metadata=cleaning_metadata,
        received_at=received_at,
        processing_status=processing_status,
    )
    db.add(msg)
    try:
        await db.commit()
        await db.refresh(msg)
        return msg
    except IntegrityError:
        # אותו gmail_message_id כבר נשמר ב-race (לא צפוי — process_incoming
        # בודק קודם, אבל defense in depth מול webhook מקביל).
        await db.rollback()
        logger.info("EmailMessage already exists for gmail_message_id=%s", gmail_message_id)
        return None


async def _persist_history_id(
    db: AsyncSession, *, new_id: str, expected_old: str | None
) -> None:
    """CAS UPDATE — מעדכן history_id רק אם עדיין == expected_old. מונע
    דריסת cursor חדש יותר ע"י webhook מאוחר.

    כש-expected_old=None (DB מכיל NULL — אחרי reset או לפני watch ראשון),
    חייבים `IS NULL` ולא `= NULL` — Postgres מחזיר NULL להשוואה עם NULL,
    ולא TRUE. בלי זה התיקון התופס שאמור להציב cursor ראשון היה rowcount=0,
    וכל webhook הבא היה ממשיך לפתור מ-NULL בלי לקדם — תיקון bugbot.
    """
    if expected_old is None:
        where_clause = GmailCredentials.history_id.is_(None)
    else:
        where_clause = GmailCredentials.history_id == expected_old

    result = await db.execute(
        update(GmailCredentials)
        .where(
            GmailCredentials.id == 1,
            where_clause,
        )
        .values(history_id=new_id)
    )
    await db.commit()
    if result.rowcount == 0:
        logger.info(
            "history_id %s already advanced by parallel webhook (expected %s)",
            new_id,
            expected_old,
        )


async def _reset_history_id(db: AsyncSession) -> None:
    """מאפס history_id ל-NULL. cron renew_gmail_watch הבא יקבל historyId
    טרי מ-watch() response. משמש כשhistoryId הישן פג (Gmail 404)."""
    await db.execute(
        update(GmailCredentials)
        .where(GmailCredentials.id == 1)
        .values(history_id=None)
    )
    await db.commit()


async def _apply_filter_label(
    db: AsyncSession, gmail_message_id: str | None, creds
) -> None:
    """מוסיף תווית "סוננו" למייל ב-Gmail. silent על שגיאות (לא קריטי)."""
    if not gmail_message_id:
        return
    try:
        label_id = await gmail.ensure_filter_label(db)
        await asyncio.to_thread(_modify_labels_blocking, creds, gmail_message_id, [label_id])
    except Exception:
        logger.exception("Failed to apply filter label to %s", gmail_message_id)


def _modify_labels_blocking(creds, msg_id: str, add_label_ids: list[str]) -> None:
    """blocking — מוסיף labels למסר."""
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)
    service.users().messages().modify(
        userId="me",
        id=msg_id,
        body={"addLabelIds": add_label_ids},
    ).execute()


# ===== Utilities =====


_DISPLAY_NAME_RE = re.compile(r"^\s*(?:\"?([^\"<]+?)\"?\s*)?<([^>]+)>\s*$")


def _name_from_address(addr: str | None) -> str | None:
    """'John Doe <jd@x.com>' → 'John Doe'. 'jd@x.com' → 'jd' (best-effort)."""
    if not addr:
        return None
    m = _DISPLAY_NAME_RE.match(addr)
    if m and m.group(1):
        return m.group(1).strip()
    # email בלבד — לקחת את ה-local-part
    if "@" in addr:
        local = addr.split("@", 1)[0]
        # אם יש נקודה/קו תחתון — להחליף ברווחים
        local = local.replace(".", " ").replace("_", " ")
        return local or None
    return None


def _ms_to_datetime(epoch_ms: int):
    """epoch milliseconds → tz-aware UTC datetime."""
    from datetime import datetime, timezone
    return datetime.fromtimestamp(epoch_ms / 1000, tz=timezone.utc)


# כמה תווים מגוף המייל להציג ב-activity content. 80 = מספיק להבין על מה
# מדובר, לא יותר מדי לרשומה ב-timeline. ניתן לעדכן לפי משוב.
_BODY_PREVIEW_CHARS = 80


def _build_email_activity_content(email_msg: EmailMessage) -> str:
    """בונה content ל-activity של ליד שהגיע ממייל.

    פורמט: subject\nbody_preview (~80 תווים).
    הסיבה לבחור את התוכן הזה במקום ai_reason: ai_reason של ה-classifier
    תמיד אומר "פנייה עסקית..." — טאוטולוגי לליד שכבר נוצר. נועה צריכה
    תוכן ספציפי שעוזר לה להחליט.

    קריסת רווחים מרובים: cleaned_text כבר עבר ניקוי HTML אבל יכול
    לכלול \\n\\n / רווחים שמכוערים בשורה אחת ב-timeline.
    """
    subject = (email_msg.subject or "").strip() or "(ללא נושא)"
    body = (email_msg.cleaned_text or "").strip()
    if not body:
        return subject
    body_flat = " ".join(body.split())
    if len(body_flat) > _BODY_PREVIEW_CHARS:
        body_flat = body_flat[:_BODY_PREVIEW_CHARS] + "…"
    return f"{subject}\n{body_flat}"
