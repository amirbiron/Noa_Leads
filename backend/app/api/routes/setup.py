"""
Setup routes — יצירת משתמש Owner ראשון דרך ה-UI.

ללא auth — מוגן ע"י המחסום: rejected אם כבר קיים משתמש כלשהו במערכת.
חד-פעמי לכל deploy ראשון.
"""

from fastapi import APIRouter
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app.api.deps import DbSession
from app.constants import UserRole
from app.core.exceptions import ConflictError
from app.core.security import create_access_token, create_refresh_token, hash_password
from app.models.user import User
from app.schemas.auth import TokenResponse
from app.schemas.setup import InitialOwnerCreate, SetupStatusResponse

router = APIRouter(prefix="/setup", tags=["setup"])

# מפתח קבוע ל-advisory lock של ה-setup. כל ערך int64 קבוע מספיק —
# חשוב רק שיהיה ייחודי בתוך ה-DB (אין lock-ים אחרים בקוד).
_SETUP_LOCK_KEY = 7307391  # ascii sum של "noa-setup"


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
    מובטח חד-פעמי: רק אם עדיין אין משתמשים. ניסיון שני נדחה עם 409.

    אטומיות: pg_advisory_xact_lock מסדר את הסעיף הקריטי לצורה סדרתית בכל
    ה-DB. שתי קריאות במקביל עם מיילים שונים היו אחרת רואות count=0 ושתיהן
    מצליחות (unique על email לא תופס כי המיילים שונים). הlock נשחרר
    אוטומטית בסוף ה-transaction (commit/rollback).
    """
    # נעילה — חוסמת מקבילות עד commit. חייב להיות לפני ה-SELECT count.
    await db.execute(
        text("SELECT pg_advisory_xact_lock(:k)").bindparams(k=_SETUP_LOCK_KEY)
    )

    # שלב 1: בדיקה — עכשיו בטוחה, אף transaction אחר לא יקדים אותנו
    result = await db.execute(select(func.count()).select_from(User))
    if int(result.scalar_one()) > 0:
        raise ConflictError(
            "המערכת כבר הוגדרה. השתמש בדף ההתחברות הרגיל."
        )

    # שלב 2: insert. IntegrityError גיבוי במקרה של email collision בלבד
    # (למשל אם אדמין דרך ה-CLI הספיק להכניס משתמש בין השלבים בלי lock).
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
