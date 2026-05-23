"""
ניהול session ו-engine ל-PostgreSQL בצורה אסינכרונית.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings


def _create_engine() -> AsyncEngine:
    settings = get_settings()
    return create_async_engine(
        settings.database_url,
        echo=False,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )


engine: AsyncEngine = _create_engine()

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,  # כדי שערכים יהיו זמינים אחרי commit (כלל 5 ב-CLAUDE.md)
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """תלות FastAPI: session לכל בקשה, סגירה אוטומטית בסיום."""
    async with AsyncSessionLocal() as session:
        yield session
