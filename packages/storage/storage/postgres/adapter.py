"""Postgres async storage adapter using asyncpg via SQLAlchemy."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from core.models import Base
from storage.interface import StorageBackend


class PostgresBackend(StorageBackend):
    """StorageBackend implementation backed by Postgres (with pgvector support).

    Requires a DATABASE_URL of the form:
        postgresql+asyncpg://user:password@host:port/dbname
    """

    def __init__(self, database_url: str, *, pool_size: int = 5, max_overflow: int = 10) -> None:
        self._engine: AsyncEngine = create_async_engine(
            database_url,
            echo=False,
            pool_size=pool_size,
            max_overflow=max_overflow,
        )
        self._session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
            self._engine, expire_on_commit=False
        )

    async def initialize_db(self) -> None:
        async with self._engine.begin() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            await conn.run_sync(Base.metadata.create_all)

    async def get_session(self) -> AsyncSession:
        return self._session_factory()

    async def execute(self, statement: Any, params: dict[str, Any] | None = None) -> Any:
        async with self._engine.connect() as conn:
            result = await conn.execute(
                text(statement) if isinstance(statement, str) else statement,
                params or {},
            )
            return result

    async def dispose(self) -> None:
        await self._engine.dispose()