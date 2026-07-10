"""
meta:
  purpose: Alembic async env. Migration URL resolution order:
           ALEMBIC_DATABASE_URL (tests) > code/.env DATABASE_URL (dev).
  contract: target_metadata = shiboleth.db.models.Base.metadata; async engine
            (asyncpg) with run_sync bridge; offline mode supported.
  deps: alembic, sqlalchemy[asyncio], shiboleth.config, shiboleth.db.models.
"""

import asyncio
import os

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from shiboleth.config import Settings
from shiboleth.db.models import Base

config = context.config
target_metadata = Base.metadata


def get_url() -> str:
    override = os.environ.get("ALEMBIC_DATABASE_URL")
    if override:
        return override
    return Settings.from_env(None).database_url


def run_migrations_offline() -> None:
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_async_engine(get_url())
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
