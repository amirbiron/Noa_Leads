"""
AI service wrapper — Phase 3 Stage 16.

תשתית לקריאות Anthropic. אין public methods (classify_email,
summarize_daily) ב-Stage הזה — הן יתווספו ב-Stages 17/18/19 לצד
הconsumers. הסיבה: prompt design תלוי ב-use case ספציפי.

מה כן כאן:
- AIClient עם _complete() — internal helper שמטפל ב-retry/fallback.
- resolve_model(purpose) — env-based model resolution.
- custom exceptions: AIError, AIRateLimitError, AIConfigError.
- ai_client singleton (lazy).

מדיניות retry — לפי docs/phase-3-ai-token-management.md §retry:
- שגיאות רשת זמניות → 3 attempts עם backoff (1s, 2s) בין הניסיונות.
- RateLimitError → *לא* retry. raise AIRateLimitError; caller יסמן
  pending_classification=true ו-cron ינסה אחרי דקה. retry על rate
  limit מחמיר את הספירה (כל call מקבל 3× עונשים).
- אחרי כל ה-retries — אם fallback_on_error=True ולא classifier, ניסיון
  אחד עם FAST model. classifier לא נופל ל-fallback (חייב להישאר עקבי).
  גם בfallback, RateLimitError מתורגם ל-AIRateLimitError (לא AIError
  גנרי) כדי שcaller ידע לסמן pending.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Literal

from anthropic import (
    APIConnectionError,
    APITimeoutError,
    AsyncAnthropic,
    InternalServerError,
    RateLimitError,
)

from app.config import get_settings

logger = logging.getLogger(__name__)


# ===== Exceptions =====


class AIError(Exception):
    """שגיאה כללית בקריאה ל-AI (network/server/fallback failed)."""


class AIRateLimitError(AIError):
    """RateLimitError מ-Anthropic. לא לעשות retry — לסמן pending."""


class AIConfigError(AIError):
    """AI לא זמין (אין anthropic_api_key)."""


# ===== Model resolution =====

_Purpose = Literal[
    "classifier",
    "daily_summary",
    "weekly_summary",
    "proposal_draft",
    "dormant_detection",
]


def resolve_model(purpose: _Purpose) -> str:
    """
    מחזיר את ה-model name לpurpose נתון. cascade:
    1. override per-use-case (env: AI_MODEL_<purpose>).
    2. fast/quality tier (לפי הסיווג הסמנטי של ה-purpose).
    3. defaults (claude-haiku-4-5 / claude-sonnet-4-6).
    """
    s = get_settings()
    # use-case override
    override_map = {
        "classifier": s.ai_model_email_classifier,
        "daily_summary": s.ai_model_daily_summary,
        "weekly_summary": s.ai_model_daily_summary,  # משתמשים באותו tier
        "proposal_draft": s.ai_model_proposal_draft,
        "dormant_detection": s.ai_model_dormant_detection,
    }
    if override := override_map.get(purpose):
        return override

    # fallback ל-tier
    quality_purposes = {"daily_summary", "weekly_summary", "proposal_draft"}
    if purpose in quality_purposes:
        return s.ai_model_quality
    return s.ai_model_fast


# ===== Client =====


# שגיאות שמצדיקות retry. RateLimit *לא* פה — מטופל בנפרד.
_RETRYABLE = (APIConnectionError, APITimeoutError, InternalServerError)

# 3 ניסיונות, 2 sleep-ים ביניהם. tuple אורך = מספר ה-sleeps
# (לא מספר הניסיונות). אם נכשל ה-3rd attempt — אין sleep, נופלים
# ל-fallback או raise.
_MAX_ATTEMPTS = 3
_BACKOFF_SECONDS = (1, 2)  # בין attempt 1→2, ובין 2→3


class AIClient:
    """
    Wrapper סביב AsyncAnthropic עם retry/fallback policy.

    שימוש (יבוא ב-Stages 17/18/19):
        client = get_ai_client()
        text, usage = await client._complete(
            model=resolve_model("classifier"),
            system="...", user="...",
            max_tokens=300,
            fallback_on_error=False,  # classifier לא נופל ל-FAST
        )
    """

    def __init__(self, api_key: str | None) -> None:
        self._api_key = api_key
        self._anthropic: AsyncAnthropic | None = None

    @property
    def _client(self) -> AsyncAnthropic:
        if not self._api_key:
            raise AIConfigError(
                "ANTHROPIC_API_KEY לא מוגדר — AI features מושבתים."
            )
        if self._anthropic is None:
            self._anthropic = AsyncAnthropic(api_key=self._api_key)
        return self._anthropic

    async def _complete(
        self,
        *,
        model: str,
        system: str,
        user: str,
        max_tokens: int,
        fallback_on_error: bool = False,
    ) -> tuple[str, dict]:
        """
        קריאה ל-Messages API עם retry על שגיאות רשת זמניות.
        מחזיר (text, usage_dict).
        """
        last_error: Exception | None = None

        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                return await self._call_once(model, system, user, max_tokens)
            except RateLimitError as e:
                # אסור retry על rate limit. raise מיד.
                logger.warning(
                    "AI rate limit on model=%s attempt=%d: %s",
                    model,
                    attempt,
                    e,
                )
                raise AIRateLimitError(str(e)) from e
            except _RETRYABLE as e:
                last_error = e
                logger.warning(
                    "AI retryable error on model=%s attempt=%d/%d: %s",
                    model,
                    attempt,
                    _MAX_ATTEMPTS,
                    e,
                )
                # sleep רק כשיש attempt נוסף. backoffs index = attempt-1.
                if attempt < _MAX_ATTEMPTS:
                    await asyncio.sleep(_BACKOFF_SECONDS[attempt - 1])

        # כל ה-retries נכשלו. fallback ל-FAST אם מותר.
        if fallback_on_error:
            fast = get_settings().ai_model_fast
            if fast != model:  # נמנע fallback ל-אותו model
                logger.info("AI falling back to %s after retries", fast)
                try:
                    return await self._call_once(fast, system, user, max_tokens)
                except RateLimitError as e:
                    # גם ב-fallback — rate limit חייב להיות AIRateLimitError
                    # כדי שcaller ידע לסמן pending_classification (לא לרצף
                    # retries שמחמירים את הספירה).
                    logger.warning(
                        "AI rate limit on fallback model=%s: %s", fast, e
                    )
                    raise AIRateLimitError(str(e)) from e
                except Exception as e:
                    last_error = e

        raise AIError(
            f"AI call failed after {_MAX_ATTEMPTS} attempts: {last_error}"
        ) from last_error

    async def _call_once(
        self, model: str, system: str, user: str, max_tokens: int
    ) -> tuple[str, dict]:
        """ניסיון בודד. לא תופס חריגות — _complete אחראית על הretry."""
        message = await self._client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        # תכן הטקסט — בלוק ראשון מסוג text.
        text_parts = [
            block.text for block in message.content if block.type == "text"
        ]
        text = "".join(text_parts)
        usage = {
            "input_tokens": message.usage.input_tokens,
            "output_tokens": message.usage.output_tokens,
            "model": message.model,
        }
        return text, usage


# ===== Singleton =====

_ai_client: AIClient | None = None


def get_ai_client() -> AIClient:
    """
    Lazy singleton. נוצר בקריאה ראשונה — אם anthropic_api_key חסר,
    AIClient נוצר אבל יזרוק AIConfigError בקריאה ל-_complete. לא קורס
    ב-startup, וקוד שלא משתמש ב-AI לא מושפע.
    """
    global _ai_client
    if _ai_client is None:
        _ai_client = AIClient(get_settings().anthropic_api_key)
    return _ai_client
