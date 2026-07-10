"""
meta:
  purpose: Async SQLAlchemy engine + session factory, built from Settings.
           One engine per process; sessions per request/task.
  contract: get_engine(url) cached per url; session_factory(engine) ->
            async_sessionmaker. No secrets logged.
  deps: sqlalchemy[asyncio] + asyncpg.
"""

from __future__ import annotations

from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)


@lru_cache(maxsize=4)
def get_engine(database_url: str) -> AsyncEngine:
    return create_async_engine(database_url, pool_pre_ping=True)


def session_factory(engine: AsyncEngine) -> async_sessionmaker:
    return async_sessionmaker(engine, expire_on_commit=False)
