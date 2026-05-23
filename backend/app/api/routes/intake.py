"""
Intake routes — קליטת לידים מטופס/מייל/הזנה ידנית.
"""

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.schemas.intake import IntakeFormRequest, IntakeResponse
from app.schemas.lead import LeadCreate
from app.services import intake as intake_service

router = APIRouter(prefix="/intake", tags=["intake"])


@router.post("/form", response_model=IntakeResponse)
async def intake_form(payload: IntakeFormRequest, db: DbSession) -> IntakeResponse:
    """
    קליטה מטופס באתר — public, ללא auth.
    בעתיד נוסיף rate-limiting (לפי IP) כדי למנוע spam.
    """
    return await intake_service.intake_from_form(db, payload)


@router.post("/manual", response_model=IntakeResponse)
async def intake_manual(
    payload: LeadCreate, db: DbSession, user: CurrentUser
) -> IntakeResponse:
    """הזנה ידנית מהאפליקציה — דורש משתמש מחובר."""
    return await intake_service.intake_manual(db, payload, user.id)


# ===== Email webhook — skeleton =====
# חיבור Gmail Pub/Sub יושלם בשלב מאוחר יותר עם OAuth + Pub/Sub setup.
# נשמר כאן כ-placeholder כדי שה-route יהיה רשום ולא תהיה הפתעה.

@router.post("/email", status_code=202)
async def intake_email() -> dict[str, str]:
    return {
        "status": "accepted",
        "message": "אינטגרציית Gmail עוד לא פעילה — webhook יישמר ל-debugging.",
    }
