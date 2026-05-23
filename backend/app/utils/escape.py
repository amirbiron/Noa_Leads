"""
פונקציות escape פר-יעד פלט (כלל 6 ב-CLAUDE.md).

כעת בשימוש: escape_telegram_html (פוש לידים חדשים בטלגרם).
פונקציות נוספות (escape_html, escape_slack_mrkdwn) יתווספו בעת הצורך —
לא משאירים API מתפצר ולא בשימוש.
"""


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
