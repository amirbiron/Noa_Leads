"""
Dashboard routes — מסך הבית, פעולות היום, ממתין, הצעות, תובנות.
"""

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.schemas.dashboard import (
    HomeDashboardResponse,
    PendingResponse,
    ProposalsResponse,
    TodayResponse,
    WeeklyInsights,
)
from app.services import dashboard as dashboard_service

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/home", response_model=HomeDashboardResponse)
async def home(db: DbSession, user: CurrentUser) -> HomeDashboardResponse:
    """
    תמונת מצב מרוכזת למסך הבית.
    הסדר תואם את האפיון: פעולות היום → פניות חדשות → ממתין → תובנות.
    """
    today_actions = await dashboard_service.get_today_actions(db)
    new_leads = await dashboard_service.get_new_leads(db)
    pending = await dashboard_service.get_pending(db)
    weekly_insights = await dashboard_service.get_weekly_insights(db)
    return HomeDashboardResponse(
        today_actions=today_actions,
        new_leads=new_leads,
        pending=pending,
        weekly_insights=weekly_insights,
    )


@router.get("/today", response_model=TodayResponse)
async def today(db: DbSession, user: CurrentUser) -> TodayResponse:
    items = await dashboard_service.get_today_actions(db)
    return TodayResponse(items=items)


@router.get("/pending", response_model=PendingResponse)
async def pending(db: DbSession, user: CurrentUser) -> PendingResponse:
    items = await dashboard_service.get_pending(db)
    return PendingResponse(items=items)


@router.get("/proposals", response_model=ProposalsResponse)
async def proposals(db: DbSession, user: CurrentUser) -> ProposalsResponse:
    items = await dashboard_service.get_open_proposals(db)
    return ProposalsResponse(items=items)


@router.get("/weekly", response_model=WeeklyInsights)
async def weekly(db: DbSession, user: CurrentUser) -> WeeklyInsights:
    return await dashboard_service.get_weekly_insights(db)
