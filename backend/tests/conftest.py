"""
תשתית טסטים — fixture של DB session עם rollback.

הטסטים הם integration מול Postgres אמיתי (העמודה tasks.metadata JSONB +
האופרטורים ->> דורשים PG, לא SQLite). ה-session לא עושה commit אף פעם —
rollback ב-teardown מנקה כל נתון שנוצר. אם אין DB זמין (DATABASE_URL לא
מוגדר / חיבור נכשל) — הטסט מדלג, לא נכשל.
"""

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.db.session import AsyncSessionLocal


@pytest_asyncio.fixture
async def db():
    session = AsyncSessionLocal()
    try:
        # בדיקת זמינות DB — אם אין, מדלגים על הטסט (לא כישלון).
        try:
            await session.execute(text("SELECT 1"))
        except Exception as exc:  # noqa: BLE001 — כל כשל חיבור → skip
            await session.close()
            pytest.skip(f"DB not available: {exc}")
        yield session
    finally:
        await session.rollback()
        await session.close()
