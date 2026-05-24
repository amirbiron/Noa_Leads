"""
Setup routes — יצירת משתמש Owner ראשון דרך ה-UI.

ללא auth — מוגן ע"י המחסום: rejected אם כבר קיים משתמש כלשהו במערכת.
חד-פעמי לכל deploy ראשון.
"""

from fastapi import APIRouter
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.api.deps import DbSession
from app.constants import UserRole
from app.core.exceptions import ConflictError
from app.core.security import create_access_token, create_refresh_token, hash_password
from app.models.user import User
from app.schemas.auth import TokenResponse
from app.schemas.setup import InitialOwnerCreate, SetupStatusResponse

router = APIRouter(prefix="/setup", tags=["setup"])


@router.get("/status", response_model=SetupStatusResponse)
async def setup_status(db: DbSession) -> SetupStatusResponse:
    """
    בדיקה אם יש בכלל משתמשים במערכת. אם לא — ה-UI יפנה ל-/setup.
    בטוח לחשוף ציבורית: רק count, לא רשימה.
    """
    result = await db.execute(select(func.count()).select_from(User))
    count = int(result.scalar_one())
    return SetupStatusResponse(setup_needed=count == 0, users_count=count)


@router.post("/initial-owner", response_model=TokenResponse)
async def create_initial_owner(
    payload: InitialOwnerCreate, db: DbSession
) -> TokenResponse:
    """
    יוצר משתמש Owner ראשון + מחזיר tokens (login מיידי).
    אטומי: רק אם עדיין אין משתמשים. ניסיון שני נדחה עם 409.
    """
    # שלב 1: בדיקה רכה לפני insert (כדי לתת שגיאה ידידותית)
    result = await db.execute(select(func.count()).select_from(User))
    if int(result.scalar_one()) > 0:
        raise ConflictError(
            "המערכת כבר הוגדרה. השתמש בדף ההתחברות הרגיל."
        )

    # שלב 2: insert. גם אם בכל זאת היה race — IntegrityError על email unique.
    user = User(
        email=payload.email,
        name=payload.name,
        role=UserRole.OWNER.value,
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    try:
        await db.commit()
        await db.refresh(user)
    except IntegrityError:
        await db.rollback()
        raise ConflictError(
            "המערכת כבר הוגדרה. השתמש בדף ההתחברות הרגיל."
        )

    # שלב 3: מחזיר tokens — המשתמשת מחוברת מיד בלי login נוסף
    access_token, expires_in = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
    )
