"""SQLite async storage adapter using aiosqlite via SQLAlchemy."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from core.models import Base
from storage.interface import StorageBackend


def _ensure_db_dir(database_url: str) -> None:
    parsed = urlparse(database_url)
    db_path = parsed.path.lstrip("/")
    if db_path and db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)


class SQLiteBackend(StorageBackend):
    def __init__(self, database_url: str) -> None:
        _ensure_db_dir(database_url)
        self._engine: AsyncEngine = create_async_engine(database_url, echo=False)
        self._session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
            self._engine, expire_on_commit=False
        )
        self._configure_wal()

    def _configure_wal(self) -> None:
        @event.listens_for(self._engine.sync_engine, "connect")
        def set_wal_mode(dbapi_connection: Any, _connection_record: Any) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()

    async def initialize_db(self) -> None:
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def get_session(self) -> AsyncSession:
        return self._session_factory()

    async def execute(self, statement: Any, params: dict[str, Any] | None = None) -> Any:
        async with self._engine.connect() as conn:
            result = await conn.execute(text(statement) if isinstance(statement, str) else statement, params or {})
            return result