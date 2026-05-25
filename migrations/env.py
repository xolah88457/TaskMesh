"""Alembic migration environment for TaskMesh.

Connects to the same async PostgreSQL engine the app uses. DATABASE_URL is
read from the .env file (loaded via dotenv) so `alembic upgrade head` works
both locally and on Render without any extra config.
"""
import asyncio
import os
from logging.config import fileConfig
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Load .env from the project root so DATABASE_URL is available.
_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env")

# Make `import backend.*` work when alembic is invoked from the project root.
import sys
sys.path.insert(0, str(_ROOT))

# Importing every model module registers the tables on Base.metadata.
from backend.db.models import Base  # noqa: E402
from backend.db import models_teams  # noqa: F401,E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Override the URL in alembic.ini with the runtime one.
_db_url = os.environ.get("DATABASE_URL", "")
if _db_url:
    config.set_main_option("sqlalchemy.url", _db_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
