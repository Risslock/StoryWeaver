"""Shared fixtures for integration tests."""

from __future__ import annotations

import uuid

import pytest_asyncio
from core.models import User
from services.auth import hash_password
from storage.sqlite.adapter import SQLiteBackend


@pytest_asyncio.fixture
async def test_owner_id(backend: SQLiteBackend) -> uuid.UUID:
    """Create a minimal GM user and return their id for use in campaign fixtures."""
    async with await backend.get_session() as session:
        user = User(
            id=uuid.uuid4(),
            username="testgm",
            email="testgm@example.com",
            hashed_password=hash_password("testpassword"),
        )
        session.add(user)
        await session.commit()
        return user.id
