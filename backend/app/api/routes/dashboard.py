"""
Dashboard routes — מסך הבית, פעולות היום, ממתין, הצעות, תובנות.
"""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession
from app.constants import SummaryType
from app.schemas.dashboard import (
    DashboardPollResponse,
    HomeDashboardResponse,
    PendingResponse,
    ProposalsResponse,
    TodayResponse,
    UrgentResponse,
    WeeklyInsights,
)
from app.services import dashboard as dashboard_service

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/home", response_model=HomeDashboardResponse)
async def home(db: DbSession, user: CurrentUser) -> HomeDashboardResponse:
    """
    תמונת מצב למסך הבית ("לוח בוקר") — בלוקי counter + תובנות + סיכומי AI.

    הרשימות המלאות (פעולות היום / פניות חדשות / ממתין) חיות בדפים
    הייעודיים (/dashboard/today, /dashboard/pending, /leads). הבית
    מציג רק מונים + כפתורי כניסה — כדי שהבוקר של נועה יתחיל ממיקוד.
    """
    new_leads_24h_count = await dashboard_service.get_new_leads_24h_count(db)
    urgent_no_first_response_count = (
        await dashboard_service.get_urgent_no_first_response_count(db)
    )
    weekly_insights = await dashboard_service.get_weekly_insights(db)
    daily_summary = await dashboard_service.get_latest_daily_summary(db)
    ai_daily_summary = await dashboard_service.get_latest_ai_summary(
        db, SummaryType.DAILY.value
    )
    ai_weekly_summary = await dashboard_service.get_latest_ai_summary(
        db, SummaryType.WEEKLY.value
    )
    return HomeDashboardResponse(
        new_leads_24h_count=new_leads_24h_count,
        urgent_no_first_response_count=urgent_no_first_response_count,
        weekly_insights=weekly_insights,
        daily_summary=daily_summary,
        ai_daily_summary=ai_daily_summary,
        ai_weekly_summary=ai_weekly_summary,
    )


@router.get("/today", response_model=TodayResponse)
async def today(db: DbSession, user: CurrentUser) -> TodayResponse:
    items = await dashboard_service.get_today_actions(db)
    return TodayResponse(items=items)


@router.get("/pending", response_model=PendingResponse)
async def pending(db: DbSession, user: CurrentUser) -> PendingResponse:
    items = await dashboard_service.get_pending(db)
    return PendingResponse(items=items)


@router.get("/urgent", response_model=UrgentResponse)
async def urgent(db: DbSession, user: CurrentUser) -> UrgentResponse:
    """היעד של Block 3 בבית — הלידים שממתינים למענה ראשון 48h+.

    הרשימה נשענת על אותם תנאים שמזינים את המונה ב-/home, כך שהמספר
    בכרטיס ומה שנפתח בלחיצה עליו לא יכולים להתפצל.
    """
    items = await dashboard_service.get_urgent_no_first_response_leads(db)
    return UrgentResponse(items=items)


@router.get("/proposals", response_model=ProposalsResponse)
async def proposals(db: DbSession, user: CurrentUser) -> ProposalsResponse:
    items = await dashboard_service.get_open_proposals(db)
    return ProposalsResponse(items=items)


@router.get("/weekly", response_model=WeeklyInsights)
async def weekly(db: DbSession, user: CurrentUser) -> WeeklyInsights:
    return await dashboard_service.get_weekly_insights(db)


@router.post("/ai-summaries/{summary_id}/inaccurate", status_code=204)
async def mark_ai_summary_inaccurate(
    summary_id: UUID, db: DbSession, user: CurrentUser
) -> None:
    """כפתור "לא מדויק" (§3.7/§6.8) — מעלה את inaccurate_count ב-1.

    זמין לכל משתמש מאומת (לא OwnerOnly — §3.7 לא מגביל). 404 אם הסיכום
    לא נמצא. אין body בתשובה (204).

    ה-service עושה UPDATE בלבד (כלל 15) — ה-commit כאן. NotFoundError
    שיוטל מה-service קופץ מעל ה-commit, ו-FastAPI עוטף ל-HTTP 404.
    """
    await dashboard_service.increment_inaccurate_count(db, summary_id)
    await db.commit()


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
