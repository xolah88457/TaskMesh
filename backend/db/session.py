"""
Async SQLAlchemy session factory.

Set DATABASE_URL in .env to enable persistence, e.g.:
  postgresql+asyncpg://user:password@/agentteam?host=/cloudsql/project:region:instance

When DATABASE_URL is not set, all DB operations are no-ops (dev mode).
"""
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

DATABASE_URL = os.environ.get("DATABASE_URL", "")

_engine = None
_AsyncSession = None

if DATABASE_URL:
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
    _engine = create_async_engine(DATABASE_URL, pool_pre_ping=True, echo=False)
    _AsyncSession = async_sessionmaker(_engine, expire_on_commit=False, class_=AsyncSession)


@asynccontextmanager
async def get_session() -> AsyncGenerator:
    """Yields an async DB session, or None if DATABASE_URL is not configured."""
    if _AsyncSession is None:
        yield None
        return
    async with _AsyncSession() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def create_tables() -> None:
    """Create all tables if they don't exist. Called once at startup."""
    if _engine is None:
        return
    from .models import Base
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
