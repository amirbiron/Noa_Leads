"""
פונקציות escape פר-יעד פלט (כלל 6 ב-CLAUDE.md).

כל יעד פלט עם סינטקס פעיל דורש escape ספציפי. עדיף פונקציה נפרדת
פר-target על format-string גנרי, כי כללי ה-escape שונים פר ספק.
"""

import html


def escape_html(text: str) -> str:
    """
    Escape כללי ל-HTML — מתאים לגוף מייל HTML.
    מטפל ב-& < > ובציטוטים.
    """
    return html.escape(text, quote=True)


def escape_telegram_html(text: str) -> str:
    """
    Escape ל-Telegram parse_mode=HTML.
    Telegram מצפה ל-escape של & < > בלבד (לא ציטוטים).
    דוגמה למה חשוב: שולח בשם "AT&T" — בלי escape ההודעה נכשלת.
    """
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def escape_slack_mrkdwn(text: str) -> str:
    """
    Escape ל-Slack mrkdwn — & < > בלבד, ללא ציטוטים.
    שונה מ-Telegram (גם אם הכלל זהה) — שמירת פונקציה נפרדת מונעת
    שגיאות אם בעתיד אחד הספקים ישנה כללים.
    """
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def to_plain_text(text: str) -> str:
    """
    זרימה ניטרלית — להחזרה כ-text לוואטסאפ (שליחה ידנית של נועה).
    אין סינטקס פעיל ב-WhatsApp פלטפורמת-משתמש, אז אין צורך ב-escape.
    הפונקציה קיימת כתיעוד וכ-API אחיד.
    """
    return text
