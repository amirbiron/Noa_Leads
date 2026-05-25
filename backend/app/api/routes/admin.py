"""
Admin routes — דיבוג / כלים פנימיים. OwnerOnly.

לא חלק מה-product flow. נועה לא צריכה להגיע לכאן. נועד למתאם/MVP
debugging — דוגמה: לשלוח טקסט גולמי דרך ה-classifier בלי לחכות
למייל אמיתי שיגיע מ-Gmail.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.api.deps import OwnerOnly
from app.services import ai
from app.utils.email_cleaning import clean_email_body_for_ai
from app.utils.email_filtering import (
    is_heuristic_spam,
    is_likely_personal_inquiry,
    should_skip_ai_classification,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


# ===== Schemas =====


class ClassifierTestRequest(BaseModel):
    """קלט לבדיקת classifier — מדמה מייל נכנס."""

    subject: str = Field(default="", max_length=500)
    body: str = Field(..., max_length=50_000)
    # אופציונלי — לבדיקת heuristic spam (מ-amirbiron@gmail.com → לא ספאם;
    # מ-noreply@mailchimp.com → ספאם). אם לא מועבר — heuristic מדווח כ-False.
    from_address: str | None = Field(default=None, max_length=200)


class HeuristicResult(BaseModel):
    is_spam: bool
    is_personal_inquiry: bool
    would_skip_ai: bool  # התוצאה הסופית של should_skip_ai_classification


class CleaningResult(BaseModel):
    cleaned_text: str
    metadata: dict


class ClassifierTestResponse(BaseModel):
    """תוצאות כל שלבי ה-pipeline — לדיבוג איפה מייל ננעצר."""

    heuristic: HeuristicResult
    cleaning: CleaningResult
    # None אם heuristic.would_skip_ai=True (לא קראנו ל-AI)
    classification: ai.ClassificationResult | None = None
    # None אם is_business=false (לא קראנו ל-extract)
    extracted: ai.LeadDraft | None = None
    # אם נקלעה שגיאה ב-AI (rate limit, JSON parse, וכו') — string תיאורי
    ai_error: str | None = None


# ===== Endpoint =====


@router.post("/classifier-test", response_model=ClassifierTestResponse)
async def classifier_test(
    payload: ClassifierTestRequest, user: OwnerOnly
) -> ClassifierTestResponse:
    """
    מעביר טקסט גולמי דרך כל ה-pipeline של email intake:
    1. heuristic spam filter (האם היה נדלג על AI).
    2. clean_email_body_for_ai (cleaned_text + metadata).
    3. classify_email — is_business + confidence + reason.
    4. אם is_business: extract_lead_from_email — full_name / phone /
       category / subtype / summary.

    כל שלב מוחזר נפרד — אם מייל אמיתי נחסם, אפשר לראות איפה (heuristic /
    classification / extraction). שימושי במיוחד אחרי שינוי prompt — לבדוק
    בלי לחכות למייל בדיקה דרך Gmail.

    *לא* יוצר ליד ב-DB ולא שולח התראת telegram. read-only מבחינת state.
    """
    # 1. heuristic
    spam = is_heuristic_spam(payload.from_address, headers=None)
    personal = is_likely_personal_inquiry(payload.body)
    would_skip = should_skip_ai_classification(
        payload.from_address, headers=None, body=payload.body
    )
    heuristic = HeuristicResult(
        is_spam=spam,
        is_personal_inquiry=personal,
        would_skip_ai=would_skip,
    )

    # 2. cleaning
    cleaned_text, cleaning_metadata = clean_email_body_for_ai(
        payload.body, "classification"
    )
    cleaning = CleaningResult(
        cleaned_text=cleaned_text,
        metadata=cleaning_metadata,
    )

    # אם ה-pipeline האמיתי היה דולג על AI — לא נריץ classifier ב-test.
    # מחזירים את התוצאות כדי שהמשתמש יראה למה.
    if would_skip:
        return ClassifierTestResponse(heuristic=heuristic, cleaning=cleaning)

    # 3. classify
    try:
        classification = await ai.classify_email(
            subject=payload.subject, cleaned_body=cleaned_text
        )
    except ai.AIError as e:
        return ClassifierTestResponse(
            heuristic=heuristic,
            cleaning=cleaning,
            ai_error=f"classify: {type(e).__name__}: {e}",
        )

    # 4. extract (רק אם business)
    extracted = None
    if classification.is_business:
        try:
            extracted = await ai.extract_lead_from_email(
                subject=payload.subject, cleaned_body=cleaned_text
            )
        except ai.AIError as e:
            return ClassifierTestResponse(
                heuristic=heuristic,
                cleaning=cleaning,
                classification=classification,
                ai_error=f"extract: {type(e).__name__}: {e}",
            )

    return ClassifierTestResponse(
        heuristic=heuristic,
        cleaning=cleaning,
        classification=classification,
        extracted=extracted,
    )
