"""
תשתית טסטים — fixture של DB session מבודד לכל טסט.

הטסטים הם integration מול Postgres אמיתי (העמודה tasks.metadata JSONB +
האופרטורים ->> דורשים PG, לא SQLite).

=== שלוש בעיות שתוקנו כאן, ולמה ===

**1. לולאת אירועים לכל טסט מול pool גלובלי.**
`app.db.session.engine` נוצר פעם אחת בטעינת המודול, עם pool רגיל.
`asyncio_mode = auto` (ראה pytest.ini) נותן לכל טסט לולאת אירועים *חדשה*,
וחיבור asyncpg קשור ללולאה שיצרה אותו. התוצאה: הטסט הראשון פותח חיבור,
הוא חוזר ל-pool, והטסט הבא מקבל אותו בלולאה אחרת ונופל על
`got Future ... attached to a different loop`. הגרסה הקודמת של ה-fixture
תפסה את זה ב-`except Exception` רחב ודיווחה "DB not available" — כלומר
**דילגה** על הטסט. בפועל: טסט DB אחד רץ בכל קובץ וכל השאר דולגו בשקט
(נמדד: 125 passed / 54 skipped, בזמן שה-DB היה זמין לחלוטין).

הפתרון: engine ייעודי לטסטים עם `NullPool` — אף חיבור לא נשמר ל-pool,
ולכן אין חיבור ששורד למעבר בין לולאות.

**2. services ו-jobs שעושים commit מול ניקוי ב-rollback.**
CLAUDE.md כלל 15 אומר ש-service עושה flush וה-route עושה commit, אבל
בקוד הקיים יש services שעדיין עושים commit בעצמם. `commit` אי-אפשר
ל-rollback, ושורה ששרדה מפילה את ההרצה הבאה על constraint.

הפתרון הוא הדפוס הרשמי של SQLAlchemy ל-"join an external transaction":
פותחים טרנזקציה חיצונית על connection, ובונים session עם
`join_transaction_mode="create_savepoint"`. לפי ה-docstring של
`Session.__init__` ב-SQLAlchemy 2.0, הערך הזה גורם ל-session להשתמש
ב-`begin_nested()` בכל מקרה, כך ש-`commit()` פנימי משחרר SAVEPOINT
במקום לסיים את הטרנזקציה החיצונית. ה-rollback החיצוני ב-teardown מנקה
הכול, כולל מה ש"נשמר".

**3. jobs שפותחים session משלהם — חייבים את *אותו* חיבור.**
`jobs/daily_summary.py:152` עושה `async with AsyncSessionLocal() as db`.
אם ה-session הזה יושב על חיבור *אחר*, נוצרת נעילה הדדית אמיתית: הטסט
מחק שורה בטרנזקציה שלו (שלא הסתיימה, כי commit הוא רק SAVEPOINT),
וה-job מנסה INSERT לאותה שורה מחיבור שני וממתין לנצח על `transactionid`.
זה לא תיאורטי — זה מה שקרה, ואומת ב-`pg_stat_activity`.

לכן ה-fixture קושר את `AsyncSessionLocal` עצמו ל**חיבור של הטסט**
למשך הטסט. `configure(bind=...)` משנה את ה-bind של *אותו אובייקט*
sessionmaker, ולכן גם מודולים שעשו `from app.db.session import
AsyncSessionLocal` ומחזיקים הפניה משלהם מקבלים אותו. תוצאה: טרנזקציה
אחת, בלי תחרות על נעילות, וגם ה-commit של ה-job מתגלגל אחורה בסוף.
(בטוח כי ה-jobs פותחים sessions ברצף ולא במקביל — חיבור asyncpg יחיד
לא יודע לשרת שתי פעולות בו-זמנית.)

אם אין DB זמין באמת (DATABASE_URL לא מוגדר / השרת לא עונה) — הטסט
מדלג. הדילוג מצומצם בכוונה לשגיאות חיבור בלבד, כדי שבאג בקוד לא
יתחזה שוב ל"אין DB".
"""

import pytest
import pytest_asyncio
from sqlalchemy.exc import DBAPIError, InterfaceError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import get_settings

# רק אלה נחשבים "אין DB". כל שגיאה אחרת היא באג ותיפול כמו שצריך.
_CONNECTION_ERRORS = (OperationalError, InterfaceError, DBAPIError, OSError)


@pytest_asyncio.fixture
async def db():
    from app.db import session as session_module

    # NullPool: בלי שמירת חיבורים בין טסטים (ראה §1 ב-docstring).
    engine = create_async_engine(
        get_settings().database_url,
        echo=False,
        poolclass=NullPool,
    )

    try:
        conn = await engine.connect()
    except _CONNECTION_ERRORS as exc:
        await engine.dispose()
        pytest.skip(f"DB not available: {exc}")

    # טרנזקציה חיצונית שאף session לא מסיים — ה-rollback שלה בסוף הטסט
    # הוא מה שמנקה, גם אם הקוד שנבדק עשה commit.
    outer = await conn.begin()

    session = AsyncSession(
        bind=conn,
        expire_on_commit=False,  # מיישר קו עם AsyncSessionLocal (כלל 5)
        autoflush=False,
        join_transaction_mode="create_savepoint",
    )

    # ה-sessions ש-jobs פותחים בעצמם יושבים על אותו חיבור (§3).
    session_module.AsyncSessionLocal.configure(
        bind=conn,
        join_transaction_mode="create_savepoint",
    )

    try:
        yield session
    finally:
        # מחזירים את ה-sessionmaker למצבו לפני שהחיבור נסגר, אחרת טסט
        # שלא משתמש ב-fixture יקבל sessionmaker שמצביע לחיבור מת.
        session_module.AsyncSessionLocal.configure(
            bind=session_module.engine,
            join_transaction_mode="conditional_savepoint",
        )
        await session.close()
        if outer.is_active:
            await outer.rollback()
        await conn.close()
        await engine.dispose()
