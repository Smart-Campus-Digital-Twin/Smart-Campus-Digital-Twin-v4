"""
SQLAlchemy 2.x async engine + session factory.

The engine is created once at startup (lifespan) and reused.
All repos receive an AsyncSession — never use sync methods in async context.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from api.core.config import settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def create_engine() -> AsyncEngine:
    """Create and return the async engine (call once at startup)."""
    global _engine, _session_factory
    _engine = create_async_engine(
        settings.database_url,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
        echo=False,
    )
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


async def dispose_engine() -> None:
    """Dispose connection pool (call at shutdown)."""
    if _engine:
        await _engine.dispose()


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    """Yield a transactional AsyncSession; rolls back on exception."""
    if _session_factory is None:
        raise RuntimeError("DB engine not initialised — call create_engine() first")
    async with _session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def session_dep() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency — yields one session per request."""
    async with get_session() as session:
        yield session
