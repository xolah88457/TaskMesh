"""
Async SQLAlchemy session factory.

Set DATABASE_URL in .env to enable persistence, e.g.:
  postgresql+asyncpg://user:password@/agentteam?host=/cloudsql/project:region:instance

When DATABASE_URL is not set, all DB operations are no-ops (dev mode).
"""
import logging
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

_logger = logging.getLogger(__name__)


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
        try:
            await conn.run_sync(Base.metadata.create_all, checkfirst=True)
        except Exception as e:
            err_msg = str(e)
            if "already exists" in err_msg or "duplicate" in err_msg:
                _logger.info("create_tables: schema exists — %s", err_msg)
                await conn.rollback()
            else:
                raise
    # Schema migrations — columns added to existing tables after initial
    # deployment. create_all only creates tables, not new columns on
    # existing tables. These ALTER TABLEs are idempotent (IF NOT EXISTS).
    await _run_migrations()


async def _run_migrations() -> None:
    """Run one-off ALTER TABLE migrations for columns added after initial create_all."""
    if _engine is None:
        return
    from sqlalchemy import text
    async with _engine.begin() as conn:
        # Added 2026-05-22 — per-user agent config (Pro users)
        await conn.execute(text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS config_json TEXT"
        ))
        # Added 2026-05-22 — Paddle customer ID for subscription portal
        await conn.execute(text(
            "ALTER TABLE user_credits ADD COLUMN IF NOT EXISTS customer_id VARCHAR(128)"
        ))
        # Added 2026-05-22 — projects table + run columns
        await conn.execute(text(
            "CREATE TABLE IF NOT EXISTS projects ("
            "  id VARCHAR(36) PRIMARY KEY,"
            "  user_id VARCHAR(128) NOT NULL,"
            "  name VARCHAR(256) NOT NULL,"
            "  slug VARCHAR(256) NOT NULL,"
            "  desc TEXT,"
            "  icon VARCHAR(8),"
            "  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),"
            "  updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()"
            ")"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_projects_user_id ON projects(user_id)"
        ))
        await conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_projects_user_slug ON projects(user_id, slug)"
        ))
        await conn.execute(text(
            "ALTER TABLE runs ADD COLUMN IF NOT EXISTS project_id VARCHAR(36)"
        ))
        try:
            await conn.execute(text(
                "ALTER TABLE runs ADD CONSTRAINT fk_runs_project_id "
                "FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE"
            ))
        except Exception:
            pass  # constraint already exists
        await conn.execute(text(
            "ALTER TABLE runs ADD COLUMN IF NOT EXISTS selected_agents TEXT"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_runs_project_id ON runs(project_id)"
        ))
        # Add future column migrations here with a date comment
