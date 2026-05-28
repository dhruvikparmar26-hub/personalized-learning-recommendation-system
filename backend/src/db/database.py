"""
Async SQLAlchemy database connection.

Primary target is PostgreSQL via asyncpg, but local/test environments can
fall back to SQLite when that driver is unavailable.
"""

import logging

from sqlalchemy.ext.asyncio import (
    create_async_engine,
    async_sessionmaker,
    AsyncSession,
)
from sqlalchemy.orm import DeclarativeBase

from src.config import settings

logger = logging.getLogger(__name__)


def _create_engine():
    """Create the async engine, falling back to SQLite for local testing."""
    try:
        is_postgres = settings.DATABASE_URL.startswith("postgresql")
        engine_args = {
            "echo": settings.APP_ENV == "development",
        }
        if is_postgres:
            engine_args.update({
                "pool_size": 10,
                "max_overflow": 20,
                "pool_pre_ping": True,
            })
        
        return create_async_engine(
            settings.DATABASE_URL,
            **engine_args
        )
    except ModuleNotFoundError as exc:
        if "asyncpg" not in str(exc):
            raise

        logger.warning(
            "asyncpg is unavailable; falling back to local SQLite for development/testing."
        )
        return create_async_engine(
            "sqlite+aiosqlite:///./backend_dev.db",
            echo=(settings.APP_ENV == "development"),
            connect_args={"check_same_thread": False},
        )


# ── Engine ──────────────────────────────────────────────────────
# Using asyncpg driver for async PostgreSQL access.
# For Supabase pooled connections (port 6543), disable prepared statements.
# For direct connections (port 5432), default settings work fine.
engine = _create_engine()

# ── Session Factory ─────────────────────────────────────────────
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# ── Base Model ──────────────────────────────────────────────────
class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass


# ── Dependency ──────────────────────────────────────────────────
async def get_db() -> AsyncSession:
    """
    FastAPI dependency that yields an async database session.
    Automatically closes the session when the request is done.
    
    Usage:
        @app.get("/items")
        async def get_items(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


# ── Lifecycle ───────────────────────────────────────────────────
async def init_db():
    """Create all tables. Called during app startup."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db():
    """Dispose engine connections. Called during app shutdown."""
    await engine.dispose()
