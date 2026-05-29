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
import json
import logging
from typing import Literal, TypeVar

from anthropic import (
    APIConnectionError,
    APIError as AnthropicAPIError,
    APITimeoutError,
    AsyncAnthropic,
    InternalServerError,
    RateLimitError,
)
from pydantic import BaseModel, Field, ValidationError

from app.config import get_settings
from app.prompts import classify_email as classify_prompts
from app.prompts import dormant_suggestion as dormant_prompts
from app.prompts import extract_lead as extract_prompts

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


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
    "dormant_suggestion",
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
        "dormant_suggestion": s.ai_model_dormant_suggestion,
    }
    override = override_map.get(purpose)
    # explicit check: גם None וגם "" מטופלים כ-"לא מוגדר → tier default".
    # pydantic-settings מפרסר env var ריק (AI_MODEL_X="") כמחרוזת ריקה, לא
    # None — בלי הצ'ק הזה משתמש שמנסה "לאפס" override היה מקבל ברירה
    # קבועה של string ריק שפסל הקריאה ל-Anthropic.
    if override is not None and override.strip():
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
            except AnthropicAPIError as e:
                # שגיאות Anthropic שאינן retryable: AuthenticationError (bad
                # API key), BadRequestError / NotFoundError (model לא קיים,
                # malformed request), PermissionDeniedError, ConflictError,
                # APIResponseValidationError. כולן מצביעות על bug של
                # config/code — retry לא יעזור, fallback לאותו מפתח/SDK
                # ישחזר את אותה שגיאה. ממיר ל-AIError עם type ב-message
                # כדי שcaller (commit 4/4) ידע מה לסמן ב-log.
                #
                # סדר ה-except חשוב: _RETRYABLE לפני AnthropicAPIError, כי
                # InternalServerError יורש מ-APIError (ויש לעשות retry עליו).
                logger.error(
                    "AI non-retryable error on model=%s: %s: %s",
                    model,
                    type(e).__name__,
                    e,
                )
                raise AIError(
                    f"Anthropic {type(e).__name__}: {e}"
                ) from e

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
                except AnthropicAPIError as e:
                    # שגיאות SDK שאינן rate-limit — auth/bad-request/וכו'.
                    # ממיר ל-AIError במפורש (לא להעביר Anthropic exception
                    # לcaller — חוזה ה-API שלנו הוא AIError/AIRateLimitError בלבד).
                    last_error = e
                except Exception as e:
                    # safety net לכל שגיאה אחרת (timeout במהלך הfallback,
                    # network שחזר, וכו'). caller יקבל AIError.
                    last_error = e

        raise AIError(
            f"AI call failed after {_MAX_ATTEMPTS} attempts: {last_error}"
        ) from last_error

    async def _call_once(
        self, model: str, system: str, user: str, max_tokens: int
    ) -> tuple[str, dict]:
        """ניסיון בודד. לא תופס חריגות — _complete אחראית על הretry.

        ה-system נשלח כ-content block עם cache_control ephemeral —
        Anthropic prompt caching, ~90% חיסכון על system tokens בקריאות
        חוזרות (cache hit חי כ-5 דקות אחרי כל קריאה). ל-classifier
        שרץ מאות פעמים ביום זה משמעותי.
        """
        message = await self._client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=[
                {
                    "type": "text",
                    "text": system,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
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
            # cache hit ratio — אם זמין ב-API response. מאפשר monitoring
            # של ה-cache effectiveness בעתיד (Spec §20.9).
            "cache_creation_input_tokens": getattr(
                message.usage, "cache_creation_input_tokens", 0
            ),
            "cache_read_input_tokens": getattr(
                message.usage, "cache_read_input_tokens", 0
            ),
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

    Thread-safety: ה-global לא מוגן בlock. בתרחיש race נדיר (2 קוראים
    בו-זמנית בpopulate ראשון) יווצרו 2 instances, האחרון "ינצח"
    וה-stale ייגרר ב-GC. ב-single-user app זה אקדמי בלבד; lock היה
    דורש get_ai_client async ו-שינוי כל ה-callers. accepted trade-off.

    Settings reload: ה-api_key נלכד בקריאה הראשונה. אם תרגיש need
    להחליף API key ב-runtime — צריך גם לאפס _ai_client וגם לרענן את
    get_settings().clear_cache() (התלות הסתויה).
    """
    global _ai_client
    if _ai_client is None:
        _ai_client = AIClient(get_settings().anthropic_api_key)
    return _ai_client


# ===== Result models — Phase 3 Stage 18 =====


class ClassificationResult(BaseModel):
    """תוצאת classify_email. רף ההחלטה (0.7) של ה-caller, לא של ה-model."""

    is_business: bool
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(max_length=200)


class LeadDraft(BaseModel):
    """
    תוצאת extract_lead_from_email. שדות nullable + service_category/
    subtype כ-str פתוח (לא ServiceCategory enum) — כדי לסבול נתונים
    חסרים או category לא צפויה: Pydantic לא יפיל את כל ה-extract רק
    כי AI החזיר "voice_training" במקום "voice_development" (השמות
    קרובים — AI עלול להחליף).

    ה-caller (commit 4/4) אחראי על validation:
    - אם service_category לא ב-ServiceCategory enum → מנקה ל-None,
      נועה תסווג ידנית.
    - אם service_subtype לא ב-SERVICE_SUBTYPES של הקטגוריה → גם null.

    הפלוסופיה: עדיף ליד עם שדות ריקים שנועה תשלים, מאשר ליד שלא נוצר
    בכלל בגלל subfield אחד מנוח.

    `full_name` גם nullable — מייל ללא חתימה / "From: name@domain" בלי
    display name → AI מחזיר null. ה-caller מטפל ב-fallback ל-"ללא שם".
    אילו השדה היה required, Pydantic היה מכשיל את כל ה-extract רק בגלל
    שאין שם → cron retry לעד MAX → manual_review_needed lead מיותר.
    """

    full_name: str | None = None
    phone: str | None = None
    email: str | None = None
    service_category: str | None = None
    service_subtype: str | None = None
    subject_summary: str = Field(max_length=200)


class DormantSuggestionResult(BaseModel):
    """תוצאת suggest_action_for_dormant (§19 D.1). action מתוך 4 ערכים סגורים;
    reasoning משפט-שניים בעברית (caller שומר ב-task_metadata, מציג בכרטיס)."""

    action: Literal["gentle_followup", "archive", "call", "no_action"]
    reasoning: str = Field(min_length=1, max_length=220)


# ===== JSON parsing =====


def _parse_json_response(text: str, model_cls: type[T]) -> T:
    """
    מאתר JSON block בתוך response של AI ומפרס דרך Pydantic.

    משתמש ב-json.JSONDecoder().raw_decode() במקום regex: ה-decoder עוצר
    אוטומטית בסוף ה-JSON ומתעלם מ-trailing prose. ה-regex הקודם
    `\\{.*\\}` היה greedy עד ה-`}` האחרון בטקסט — אם AI הוסיף prose
    שמכיל `}` (למשל "JSON: {...} — כפי שצוין למעלה}"), כל הגוץ' היה
    נספח ל-match וה-parsing נשבר. raw_decode מטפל גם בקינון פנימי בלי
    הבעיה הזו.

    שלוש שגיאות אפשריות (כולן → AIError, caller יטפל ב-retry / manual review):
    1. אין `{` בכלל ב-response.
    2. JSON לא תקף (syntax error).
    3. JSON תקף אבל לא תואם לschema (Pydantic ValidationError).
    """
    start = text.find("{")
    if start < 0:
        raise AIError(f"No JSON block in AI response: {text[:200]!r}")
    try:
        data, _end = json.JSONDecoder().raw_decode(text[start:])
    except json.JSONDecodeError as e:
        raise AIError(
            f"Invalid JSON in AI response: {e}; text={text[:200]!r}"
        ) from e
    try:
        return model_cls.model_validate(data)
    except ValidationError as e:
        raise AIError(
            f"AI response doesn't match {model_cls.__name__}: {e}"
        ) from e


# ===== Public methods —  classify + extract =====
#
# שתי הפונקציות מקבלות subject + cleaned_body (caller חייב כבר לעבור
# דרך clean_email_body_for_ai מ-Stage 16 + heuristic filter מ-Stage 16).
# החזרת Pydantic results מאפשרת validation מובנה ושמירה ב-DB.


async def classify_email(
    *, subject: str, cleaned_body: str
) -> ClassificationResult:
    """
    מסווג מייל כעסקי/לא-עסקי. caller (commit 4/4) משווה ל-
    AI_CLASSIFY_CONFIDENCE_THRESHOLD (0.7) להחליט אם ליצור ליד רגיל
    או עם דגל low_confidence_classification.

    fallback_on_error=False — classifier חייב להישאר עקבי (גם consistency
    מודלית; אם FAST נכשל ב-network, FAST שוב לא יעזור — Anthropic side issue).

    שגיאות:
    - AIRateLimitError: caller שומר email_messages, cron retry.
    - AIError (כולל JSON parsing): caller שומר עם retry_count++. אחרי
      AI_MAX_CLASSIFICATION_RETRIES → ליד עם manual_review_needed=True.
    """
    client = get_ai_client()
    text, usage = await client._complete(
        model=resolve_model("classifier"),
        system=classify_prompts.SYSTEM_PROMPT,
        user=classify_prompts.USER_TEMPLATE.format(
            subject=subject, body=cleaned_body
        ),
        max_tokens=200,
        fallback_on_error=False,
    )
    logger.info(
        "classify_email usage: input=%d output=%d cache_read=%d",
        usage["input_tokens"],
        usage["output_tokens"],
        usage.get("cache_read_input_tokens", 0),
    )
    return _parse_json_response(text, ClassificationResult)


async def extract_lead_from_email(
    *, subject: str, cleaned_body: str
) -> LeadDraft:
    """
    חולץ פרטי ליד ממייל שכבר סווג כעסקי. שדות חסרים → None.
    service_subtype לא validated מול SERVICE_SUBTYPES של הקטגוריה —
    caller (commit 4/4) יסנן אם לא תקף.

    fallback_on_error=False — extract רץ על FAST, אין tier נמוך יותר.
    """
    client = get_ai_client()
    # FAST ישירות (לא resolve_model("classifier")) — extract לא חלק מ-
    # _Purpose, וב-classifier יש env override (AI_MODEL_EMAIL_CLASSIFIER)
    # שעלול להעלות את הסיווג ל-quality. extract תמיד נשאר FAST: ניתן
    # להוסיף override ב-_Purpose בעתיד אם נועה תרצה לכוונן בנפרד.
    text, usage = await client._complete(
        model=get_settings().ai_model_fast,
        system=extract_prompts.SYSTEM_PROMPT,
        user=extract_prompts.USER_TEMPLATE.format(
            subject=subject, body=cleaned_body
        ),
        max_tokens=400,
        fallback_on_error=False,
    )
    logger.info(
        "extract_lead usage: input=%d output=%d cache_read=%d",
        usage["input_tokens"],
        usage["output_tokens"],
        usage.get("cache_read_input_tokens", 0),
    )
    return _parse_json_response(text, LeadDraft)


async def suggest_action_for_dormant(
    *,
    lead_name: str,
    organization_name: str | None,
    service_subtype: str | None,
    service_category: str | None,
    days_since_last_activity: int,
    activities_text: str,
) -> DormantSuggestionResult:
    """
    ממליץ על פעולה אחת לליד רדום (§19 D.1) לפי ההיסטוריה שלו.
    מודל Opus (resolve_model("dormant_suggestion")) — החלטה אסטרטגית דורשת
    איכות. fallback_on_error=False: כשל → caller (cron) מטפל ב-no_action +
    manual_review. AIRateLimitError → caller משאיר pending לריצה הבאה.

    הקלט הוא היסטוריית activities (טקסט שכבר מובנה), לא HTML — אין צורך
    ב-clean_email_body_for_ai; ה-caller אחראי להגביל אורך לפני הקריאה.
    """
    client = get_ai_client()
    text, usage = await client._complete(
        model=resolve_model("dormant_suggestion"),
        system=dormant_prompts.SYSTEM_PROMPT,
        user=dormant_prompts.USER_TEMPLATE.format(
            lead_name=lead_name,
            organization_name=organization_name if organization_name else "null",
            service_subtype=service_subtype or "לא ידוע",
            service_category=service_category or "לא ידוע",
            days_since_last_activity=days_since_last_activity,
            activities_bulleted_list=activities_text,
        ),
        max_tokens=400,
        fallback_on_error=False,
    )
    logger.info(
        "suggest_action_for_dormant usage: input=%d output=%d cache_read=%d",
        usage["input_tokens"],
        usage["output_tokens"],
        usage.get("cache_read_input_tokens", 0),
    )
    return _parse_json_response(text, DormantSuggestionResult)
