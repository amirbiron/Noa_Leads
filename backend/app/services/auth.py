"""
שירות auth — login, refresh, אימות משתמש.
"""

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    hash_password,
    verify_password,
)
from app.models.user import User
from app.schemas.auth import TokenResponse

logger = logging.getLogger(__name__)


# bcrypt hash אמיתי שנוצר פעם אחת בטעינת המודול. משמש להרצת verify
# על משתמש שלא קיים כדי שזמן התגובה לא יחשוף את קיומו (timing attack).
# בעבר השתמשנו בקבוע פייק ($2b$12$ + "x"*53) שעבד אבל עלול להישבר
# בעדכוני passlib עתידיים. dummy אמיתי יציב לאורך זמן.
_DUMMY_HASH = hash_password("__noa_leads_auth_timing_dummy__")


async def authenticate_user(
    db: AsyncSession, email: str, password: str
) -> User:
    """מאמת user/password. תמיד מחזיר AuthError גנרי — לא חושף אם המייל קיים."""
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    # בדיקת הסיסמה גם אם user is None — למניעת timing attacks.
    if user is None or not user.password_hash:
        # הרצת verify מול hash תקין כדי לשמור על זמן תגובה דומה
        verify_password(password, _DUMMY_HASH)
        raise AuthError()

    if not verify_password(password, user.password_hash):
        raise AuthError()

    return user


async def issue_owner_tokens(db: AsyncSession) -> TokenResponse:
    """מנפיק tokens למשתמש ה-owner, בלי סיסמה.

    משרת את `/auth/public-access` — הכניסה האוטומטית שהחליפה את מסך
    ההתחברות. ההסבר על הסיכון והשוואה ל-`/setup/initial-owner` נמצא
    ב-docstring של ה-route.

    מחזיר tokens של ה-owner ה**אמיתי** ולא של זהות סינתטית, וזו הסיבה
    ששום דבר במורד הזרם לא משתנה: `owner_id`, `assigned_to` ו-
    `performed_by` ממשיכים להיכתב בדיוק כמו קודם, וה-FK נשמר.

    אם אין owner (DB ריק, לפני `/setup`) — `AuthError` (401), וה-
    frontend מפנה ל-`/setup`.
    """
    from app.constants import UserRole

    result = await db.execute(
        select(User)
        .where(User.role == UserRole.OWNER.value)
        # המערכת חד-טננטית ויש owner אחד, אבל זו הנחה — ולכן היא
        # מגודרת. שני דברים חשובים כאן:
        #
        # 1. **ה-tiebreaker על `id` הוא חובה, לא נוי.** `created_at`
        #    לבדו אינו עמודה ייחודית: שני owners שנוצרו באותה
        #    טרנזקציה מקבלים `now()` *זהה בדיוק*, ואז `ORDER BY`
        #    עליו אינו סדר טוטאלי והשורה שתחזור נקבעת לפי מה
        #    שה-planner החליט באותו רגע. בנתיב הזה, שהוא השורה
        #    היחידה שקובעת **כזהות מי** כל מבקר בכתובת נכנס בלי
        #    סיסמה, זהות שמתהפכת בין בקשות אינה פגם קוסמטי.
        # 2. **`limit(2)` ולא `limit(1)`** — כדי שנוכל *לדעת* שהמצב
        #    החריג קרה במקום לבחור בשקט. מסלול חריג נרשם ככזה.
        .order_by(User.created_at.asc(), User.id.asc())
        .limit(2)
    )
    owners = result.scalars().all()
    if not owners:
        raise AuthError()
    if len(owners) > 1:
        logger.warning(
            "public-access: יותר מ-owner אחד במערכת — נבחר %s. "
            "הכניסה ללא סיסמה מכניסה את כולם כמשתמש הזה.",
            owners[0].id,
        )
    owner = owners[0]

    access_token, expires_in = create_access_token(owner.id)
    refresh_token = create_refresh_token(owner.id)
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
    )


async def login(db: AsyncSession, email: str, password: str) -> TokenResponse:
    user = await authenticate_user(db, email, password)
    access_token, expires_in = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
    )


async def refresh(db: AsyncSession, refresh_token: str) -> TokenResponse:
    user_id = decode_refresh_token(refresh_token)
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise AuthError()
    access_token, expires_in = create_access_token(user.id)
    new_refresh = create_refresh_token(user.id)
    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh,
        expires_in=expires_in,
    )


async def get_user_by_id(db: AsyncSession, user_id: UUID) -> User | None:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()
