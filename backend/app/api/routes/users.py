"""
Users routes — קריאה (me / list) + יצירת עוזרת חד-פעמית מה-UI.
המערכת חד-טננטית: רק נועה (owner) + עוזרת אחת (assistant). ה-list משמש את
ה-frontend לבחירת יעד ב"העברת ליד". יצירת עוזרת היא setup חד-פעמי (§13.5) —
נדחית אם כבר קיימת עוזרת.
"""

from fastapi import APIRouter
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, DbSession, OwnerOnly
from app.constants import UserRole
from app.core.exceptions import ConflictError
from app.core.security import hash_password
from app.models.user import User
from app.schemas.user import AssistantCreate, UserRead

router = APIRouter(prefix="/users", tags=["users"])

# מפתח קבוע ל-advisory lock של יצירת העוזרת. שונה מ-_SETUP_LOCK_KEY שב-setup.py
# כדי שלא יתנגשו. ascii sum של "noa-assistant".
_ASSISTANT_LOCK_KEY = 8242198


@router.get("/me", response_model=UserRead)
async def read_me(user: CurrentUser) -> UserRead:
    return UserRead.model_validate(user)


@router.get("", response_model=list[UserRead])
async def list_users(db: DbSession, user: CurrentUser) -> list[UserRead]:
    result = await db.execute(select(User).order_by(User.name.asc()))
    return [UserRead.model_validate(u) for u in result.scalars().all()]


@router.post("", response_model=UserRead, status_code=201)
async def create_assistant(
    payload: AssistantCreate, db: DbSession, _owner: OwnerOnly
) -> UserRead:
    """
    יצירת עוזרת — owner-only, חד-פעמי (§13.5). נדחה עם 409 אם כבר קיימת עוזרת.

    אטומיות (כלל 2+8): pg_advisory_xact_lock מסדר בקשות מקבילות. בלי זה, שתי
    בקשות במקביל היו רואות count=0 ושתיהן יוצרות עוזרת (unique על email לא תופס
    כי המיילים שונים). ה-lock נשחרר אוטומטית בסוף ה-transaction.
    """
    # נעילה — לפני ה-SELECT count, חוסמת מקבילות עד commit.
    await db.execute(
        text("SELECT pg_advisory_xact_lock(:k)").bindparams(k=_ASSISTANT_LOCK_KEY)
    )

    # gate: כבר קיימת עוזרת? — עכשיו בטוח, אף transaction אחר לא יקדים.
    existing = await db.execute(
        select(func.count())
        .select_from(User)
        .where(User.role == UserRole.ASSISTANT.value)
    )
    if int(existing.scalar_one()) > 0:
        raise ConflictError("כבר קיימת עוזרת במערכת.")

    user = User(
        email=payload.email,
        name=payload.name,
        role=UserRole.ASSISTANT.value,
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    try:
        await db.commit()
        await db.refresh(user)
    except IntegrityError:
        # email כבר קיים (unique constraint) — למשל מייל של נועה.
        await db.rollback()
        raise ConflictError("כתובת המייל כבר קיימת במערכת.")

    return UserRead.model_validate(user)
