"""
הכניסה ללא סיסמה — בחירת ה-owner.

מאז שהמערכת נכנסת אוטומטית, `issue_owner_tokens` היא **השורה היחידה
שקובעת כזהות מי** כל מבקר בכתובת נכנס. לכן היא צריכה להיות
דטרמיניסטית, ולומר משהו כשההנחה שמאחוריה (owner אחד) לא מתקיימת.
"""

import logging
from datetime import datetime, timezone

import pytest

pytestmark = pytest.mark.asyncio


async def _mk_owner(db, *, email: str, created_at: datetime):
    from app.constants import UserRole
    from app.core.security import hash_password
    from app.models.user import User

    user = User(
        name="נועה",
        email=email,
        password_hash=hash_password("x" * 12),
        role=UserRole.OWNER.value,
        created_at=created_at,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


async def test_picks_the_lowest_id_among_owners_created_together(db):
    """שני owners עם `created_at` זהה → נבחר זה עם ה-id הקטן.

    זו אכיפה של הכלל המתועד, ולא רק בדיקת "יציבות": `created_at`
    לבדו אינו עמודה ייחודית, ולכן `ORDER BY` עליו אינו סדר טוטאלי.

    **מגבלת הראיה:** אין לטסט הזה מוטציה תקפה. בלי ה-tiebreaker
    Postgres עשוי להחזיר במקרה את אותה שורה — סדר לא מוגדר אינו
    סדר אקראי מובטח — ולכן הסרת התיקון אינה מבטיחה נפילה. הטסט
    מאמת שהכלל נאכף; הוא אינו מוכיח שהוא מסוגל לתפוס את היעדרו.
    """
    from app.services.auth import issue_owner_tokens
    from app.core.security import decode_refresh_token

    # אותה חותמת זמן *בדיוק* — כמו שני owners שנוצרו באותה טרנזקציה.
    same_moment = datetime.now(timezone.utc)
    a = await _mk_owner(db, email="a@example.com", created_at=same_moment)
    b = await _mk_owner(db, email="b@example.com", created_at=same_moment)
    expected = min(a.id, b.id, key=str)

    for _ in range(5):
        tokens = await issue_owner_tokens(db)
        assert decode_refresh_token(tokens.refresh_token) == expected


async def test_warns_when_more_than_one_owner_exists(db, caplog):
    """המצב החריג נרשם, במקום להיבחר בשקט."""
    from app.services.auth import issue_owner_tokens

    now = datetime.now(timezone.utc)
    await _mk_owner(db, email="one@example.com", created_at=now)
    await _mk_owner(db, email="two@example.com", created_at=now)

    with caplog.at_level(logging.WARNING, logger="app.services.auth"):
        await issue_owner_tokens(db)

    assert any("יותר מ-owner אחד" in r.getMessage() for r in caplog.records)


async def test_single_owner_does_not_warn(db, caplog):
    """המקרה הרגיל שקט — אזהרה שנורית תמיד אינה אזהרה."""
    from app.services.auth import issue_owner_tokens

    await _mk_owner(
        db, email="solo@example.com", created_at=datetime.now(timezone.utc)
    )

    with caplog.at_level(logging.WARNING, logger="app.services.auth"):
        await issue_owner_tokens(db)

    assert not [r for r in caplog.records if "owner" in r.getMessage()]


async def test_no_owner_raises_auth_error(db):
    """DB ריק → 401, וה-frontend מפנה ל-/setup."""
    from app.core.exceptions import AuthError
    from app.services.auth import issue_owner_tokens

    with pytest.raises(AuthError):
        await issue_owner_tokens(db)
