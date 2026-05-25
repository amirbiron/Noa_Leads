"""
Dashboard routes — מסך הבית, פעולות היום, ממתין, הצעות, תובנות.
"""

from datetime import datetime

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession
from app.schemas.dashboard import (
    DashboardPollResponse,
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
    daily_summary (F-07) מוצג כbubble כשיש סיכום עדכני (cron אחרי 19:00).
    """
    today_actions = await dashboard_service.get_today_actions(db)
    new_leads = await dashboard_service.get_new_leads(db)
    pending = await dashboard_service.get_pending(db)
    weekly_insights = await dashboard_service.get_weekly_insights(db)
    daily_summary = await dashboard_service.get_latest_daily_summary(db)
    return HomeDashboardResponse(
        today_actions=today_actions,
        new_leads=new_leads,
        pending=pending,
        weekly_insights=weekly_insights,
        daily_summary=daily_summary,
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


@router.get("/poll", response_model=DashboardPollResponse)
async def poll(
    db: DbSession,
    user: CurrentUser,
    since: datetime = Query(..., description="ISO 8601 — last poll time"),
) -> DashboardPollResponse:
    """Delta מאז `since`: לידים חדשים + לידים שקיבלו תגובה.

    Pydantic auto-parses `?since=2026-05-25T10:30:00Z` ל-datetime.
    אם ה-client שולח naive datetime (ללא tz), Pydantic מקבל; אבל
    ההשוואה ב-DB עם timestamptz columns תכשל. בפועל ה-frontend תמיד
    שולח server_time שחזר עם tz (UTC).

    ה-service מחזיר server_time שלקח *לפני* הqueries — anchor שמונע
    איבוד rows שcommit במהלך חלון הquery (תיקון bugbot).
    """
    new_leads, replies, server_time = await dashboard_service.poll_dashboard_delta(
        db, since=since
    )
    return DashboardPollResponse(
        new_leads=new_leads,
        leads_with_inbound_replies=replies,
        server_time=server_time,
    )
