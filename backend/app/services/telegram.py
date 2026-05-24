"""
Telegram service — שליחת הודעות לבעלת המערכת (נועה).

לפי האפיון: פוש לטלגרם רק לליד חדש שנכנס, וסיכום יומי/שבועי.
כל שליחה מטפלת בשגיאות פנימית — לא רוצים שתקלה בטלגרם תפיל
את יצירת הליד או את ה-cron.
"""

import logging

from app.config import get_settings
from app.models.lead import Lead
from app.utils.escape import escape_telegram_html
from app.utils.labels import SERVICE_CATEGORY_HE, SOURCE_CHANNEL_HE

logger = logging.getLogger(__name__)


def _is_configured() -> bool:
    settings = get_settings()
    return bool(settings.telegram_bot_token and settings.telegram_owner_chat_id)


async def send_message(text: str) -> bool:
    """
    שליחת הודעה ב-HTML. מחזיר True אם נשלחה, False אחרת.
    לא זורק חריגות החוצה — אם טלגרם נופל, log פנימי בלבד.
    """
    settings = get_settings()
    if not _is_configured():
        logger.info("Telegram not configured — skipping message")
        return False

    try:
        # import עצל — מקצר זמן startup של ה-app אם טלגרם לא בשימוש
        from telegram import Bot

        async with Bot(token=settings.telegram_bot_token) as bot:
            await bot.send_message(
                chat_id=settings.telegram_owner_chat_id,
                text=text,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
        return True
    except Exception:
        logger.exception("Telegram send_message failed")
        return False


async def notify_new_lead(lead: Lead) -> None:
    """
    פוש מיידי לליד חדש — לפי האפיון, רק זה זוכה ל-push.
    משתמש ב-escape_telegram_html (כלל 6) על כל נתון מהמשתמש.
    """
    name = escape_telegram_html(lead.full_name)
    # F-04: service_category אופציונלי. ב-intake/email או manual ייתכן None —
    # במקרה כזה מדלגים על שורת הקטגוריה במקום להעביר None ל-escape (TypeError).
    category = (
        SERVICE_CATEGORY_HE.get(lead.service_category, lead.service_category)
        if lead.service_category
        else None
    )
    source = SOURCE_CHANNEL_HE.get(lead.source_channel, lead.source_channel)

    lines = ["🔔 <b>ליד חדש</b>", f"<b>{name}</b>"]
    if lead.organization_name:
        lines[-1] += f" — {escape_telegram_html(lead.organization_name)}"
    if category:
        lines.append(f"📋 {escape_telegram_html(category)}")
    if lead.phone:
        lines.append(f"📞 {escape_telegram_html(lead.phone)}")
    if lead.source_detail:
        # מקצרים detail ארוך כדי לא להציף את ההודעה
        snippet = lead.source_detail[:200]
        lines.append(f"\n<i>{escape_telegram_html(snippet)}</i>")
    lines.append(f"\n<b>מקור:</b> {escape_telegram_html(source)}")

    await send_message("\n".join(lines))


# notify_booking_requested הוסרה — לפי Spec §16.3, טלגרם הוא ערוץ ייחודי
# לליד חדש בלבד ("הדבר היחיד שמקבל פוש מיידי"). בקשת תור מליד קיים מופיעה
# בדשבורד דרך next_action_due_at + מצב BOOKING_PENDING. ראה F-06 ב-
# docs/spec-deviations.md.
