"""
מגבלת קצב פשוטה ל-endpoints ציבוריים.

=== למה לא לפי IP ===

הדרך המקובלת היא דלי לכל כתובת IP. היא **לא בטוחה כאן**: ב-Render
האפליקציה יושבת מאחורי proxy, ולכן כתובת המקור האמיתית מגיעה רק
ב-header `X-Forwarded-For` — header שכל אחד יכול לקבוע בעצמו. תוקף
ששולח ערך אחר בכל בקשה מקבל "IP" חדש בכל פעם, והמגבלה לעולם לא נורית.
(`bugbot-rules/rate-limit-xff-spoofing.md` + CRITICAL K2 ב-
`amir-bug-patterns`.)

הדרך הנכונה לקרוא IP מאחורי proxy היא middleware של trusted-proxy
(`ProxyHeadersMiddleware` עם רשימת ה-proxies), ואז `request.client.host`.
אבל `render.yaml` מריץ `uvicorn app.main:app` **בלי** `--proxy-headers`
ובלי `--forwarded-allow-ips`, כלומר `request.client.host` הוא ה-proxy
עצמו — כתובת אחת לכל המשתמשים.

לכן ההחלטה כאן: **מגבלה גלובלית לכל endpoint, לא לפי IP.** מגבלה
גלובלית כנה עדיפה על מגבלה פר-IP שמספרת סיפור שקרי. היא מגינה על מה
שבאמת צריך הגנה — עומס על ה-DB ומכסת Google API — במחיר שבשעת עומס
אמיתי משתמש לגיטימי עלול לקבל 429 ולנסות שוב.

=== מגבלות המימוש, במפורש ===

המונה חי בזיכרון התהליך. `render.yaml:71` מריץ תהליך uvicorn יחיד ואין
`numInstances`, ולכן כרגע הוא מדויק. אם יתווספו workers או instances,
המגבלה בפועל תוכפל במספרם — ואז המקום הנכון הוא Redis או טבלה ב-DB.
"""

from __future__ import annotations

import time
from collections import deque

from app.core.exceptions import AppException


class RateLimitExceeded(AppException):
    status_code = 429
    code = "rate_limit_exceeded"
    user_message = "יותר מדי בקשות. נסי שוב בעוד רגע."


class SlidingWindowLimiter:
    """חלון מתגלגל: לכל היותר `max_events` בתוך `window_seconds`.

    חלון מתגלגל ולא "דלי לדקה": דלי קבוע מאפשר פעמיים את המכסה סביב
    גבול הדקה (סוף דקה אחת + תחילת הבאה).

    ה-deque מחזיק חותמות זמן וה-`popleft` מנקה ישנות בכל בדיקה, ולכן
    הזיכרון חסום ב-`max_events` ואין צורך ב-eviction נפרד.

    `time.monotonic` ולא `time.time`: שעון הקיר יכול לקפוץ אחורה
    (NTP), ואז חלון שלם "נעלם" והמגבלה נפתחת.
    """

    __slots__ = ("_events", "_max_events", "_window")

    def __init__(self, max_events: int, window_seconds: float) -> None:
        self._events: deque[float] = deque()
        self._max_events = max_events
        self._window = window_seconds

    def check(self) -> None:
        """מעלה RateLimitExceeded אם חרגנו. אחרת רושם את הבקשה."""
        now = time.monotonic()
        cutoff = now - self._window
        while self._events and self._events[0] <= cutoff:
            self._events.popleft()
        if len(self._events) >= self._max_events:
            raise RateLimitExceeded()
        self._events.append(now)

    def reset(self) -> None:
        """לשימוש בטסטים — מנקה את החלון."""
        self._events.clear()
