"""
Users routes — קריאה בלבד. יצירת משתמשים נעשית דרך CLI (scripts/create_user.py).
המערכת חד-טננטית: רק נועה + עוזרת אחת. ה-API משמש את ה-frontend
לבחירת יעד ב"העברת ליד".
"""

from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.models.user import User
from app.schemas.user import UserRead

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserRead)
async def read_me(user: CurrentUser) -> UserRead:
    return UserRead.model_validate(user)


@router.get("", response_model=list[UserRead])
async def list_users(db: DbSession, user: CurrentUser) -> list[UserRead]:
    result = await db.execute(select(User).order_by(User.name.asc()))
    return [UserRead.model_validate(u) for u in result.scalars().all()]
