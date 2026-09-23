"""
Authentication routes.
"""

from fastapi import APIRouter

from app.api.deps import DbSession
from app.schemas.auth import LoginRequest, RefreshRequest, TokenResponse
from app.services import auth as auth_service
from app.utils.rate_limit import SlidingWindowLimiter

router = APIRouter(prefix="/auth", tags=["auth"])


# מגבלת קצב ל-`/public-access`. 30 בקשות לדקה מכסה בנוחות שימוש רגיל
# (כניסה + חידוש מדי פעם, גם מכמה מכשירים) ועוצר לולאה או סקריפט.
# גלובלית ולא לפי IP — ההסבר המלא ב-`app/utils/rate_limit.py`.
_public_access_limiter = SlidingWindowLimiter(max_events=30, window_seconds=60)


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: DbSession) -> TokenResponse:
    return await auth_service.login(db, payload.email, payload.password)


@router.post("/public-access", response_model=TokenResponse)
async def public_access(db: DbSession) -> TokenResponse:
    """מנפיק tokens לבעלים **בלי אימות** — המערכת פתוחה בכוונה.

    זו החלטת מוצר מפורשת של הלקוח: אין מסך כניסה, וכל מי שמחזיק את
    כתובת האפליקציה נכנס כנועה — כולל למסכי ה-OwnerOnly.

    ⚠️ **אל תסתכלו על זה כ"כמו `/setup/initial-owner`".** הדמיון הוא
    בצורת הקוד בלבד, ולא בפרופיל הסיכון:

    | | `/setup/initial-owner` | כאן |
    |---|---|---|
    | מתי עובד | רק כשאין אף משתמש | תמיד |
    | כמה פעמים | פעם אחת בחיי המערכת | ללא הגבלה |
    | למי | ל-owner שהוא *יוצר* | ל-owner *קיים* |
    | הגנה | advisory lock + `count(User) == 0` | מגבלת קצב בלבד |

    ה-endpoint ההוא סגור מעצמו ברגע שנוצר משתמש ראשון; זה לא.

    אין דגל env שמכבה את זה בכוונה: "להסיר את הסיסמה לגמרי" פירושו
    שאין מצב שני, ודגל שנשכח להגדיר היה נועל את המערכת בלי דרך חזרה.
    """
    _public_access_limiter.check()
    return await auth_service.issue_owner_tokens(db)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(payload: RefreshRequest, db: DbSession) -> TokenResponse:
    return await auth_service.refresh(db, payload.refresh_token)


@router.post("/logout", status_code=204)
async def logout() -> None:
    # JWT הוא stateless — logout בצד הלקוח (מחיקת הטוקן).
    # בעתיד אפשר להוסיף blacklist ב-Redis.
    return None
