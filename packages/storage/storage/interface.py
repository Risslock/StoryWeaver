"""StorageBackend ABC — all adapters implement this interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession


class StorageBackend(ABC):
    @abstractmethod
    async def initialize_db(self) -> None:
        """Create tables / run migrations if needed."""

    @abstractmethod
    async def get_session(self) -> AsyncSession:
        """Return an async SQLAlchemy session.

        Callers are responsible for committing/rolling back.
        """

    @abstractmethod
    async def execute(self, statement: Any, params: dict[str, Any] | None = None) -> Any:
        """Execute a raw SQL statement and return the result."""