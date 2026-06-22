"""Unit tests for services/auth.py."""

from __future__ import annotations

import pytest
import pytest_asyncio
from core.models import User
from services.auth import (
    hash_password,
    register_user,
    validate_user,
    verify_password,
)
from storage.sqlite.adapter import SQLiteBackend


@pytest.fixture
def backend(tmp_path):
    db_url = f"sqlite+aiosqlite:///{tmp_path}/test.db"
    return SQLiteBackend(db_url)


@pytest_asyncio.fixture
async def seeded_backend(backend):
    await backend.initialize_db()
    return backend


# ── hash_password / verify_password ──────────────────────────────────────────


def test_hash_password_produces_sha256_hex():
    hashed = hash_password("mypassword")
    assert len(hashed) == 64
    assert all(c in "0123456789abcdef" for c in hashed)
    assert hashed != "mypassword"


def test_verify_password_correct():
    hashed = hash_password("correct")
    assert verify_password("correct", hashed) is True


def test_verify_password_wrong():
    hashed = hash_password("correct")
    assert verify_password("wrong", hashed) is False


# ── validate_user ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_validate_user_correct_credentials(seeded_backend):
    ok, _ = await register_user(seeded_backend, "alice", "alice@example.com", "password123")
    assert ok
    assert await validate_user(seeded_backend, "alice", "password123") is True


@pytest.mark.asyncio
async def test_validate_user_wrong_password(seeded_backend):
    await register_user(seeded_backend, "bob", "bob@example.com", "password123")
    assert await validate_user(seeded_backend, "bob", "wrongpassword") is False


@pytest.mark.asyncio
async def test_validate_user_inactive_user(seeded_backend):
    await register_user(seeded_backend, "inactive", "inactive@example.com", "password123")

    async with await seeded_backend.get_session() as session:
        from sqlalchemy import select
        result = await session.execute(
            select(User).where(User.username == "inactive")
        )
        user = result.scalar_one()
        user.is_active = False
        await session.commit()

    assert await validate_user(seeded_backend, "inactive", "password123") is False


@pytest.mark.asyncio
async def test_validate_user_unknown_username(seeded_backend):
    assert await validate_user(seeded_backend, "nobody", "whatever") is False


@pytest.mark.asyncio
async def test_validate_user_db_exception():
    bad_backend = SQLiteBackend("sqlite+aiosqlite:///nonexistent_dir/bad.db")
    assert await validate_user(bad_backend, "user", "pass") is False


# ── register_user ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_register_user_success(seeded_backend):
    ok, msg = await register_user(seeded_backend, "newuser", "new@example.com", "securepass")
    assert ok is True
    assert msg == ""


@pytest.mark.asyncio
async def test_register_user_duplicate_username(seeded_backend):
    await register_user(seeded_backend, "dupuser", "first@example.com", "password123")
    ok, msg = await register_user(seeded_backend, "dupuser", "second@example.com", "password123")
    assert ok is False
    assert "already registered" in msg


@pytest.mark.asyncio
async def test_register_user_duplicate_email(seeded_backend):
    await register_user(seeded_backend, "user1", "shared@example.com", "password123")
    ok, msg = await register_user(seeded_backend, "user2", "shared@example.com", "password123")
    assert ok is False
    assert "email" in msg.lower()


@pytest.mark.asyncio
async def test_register_user_username_too_short(seeded_backend):
    ok, msg = await register_user(seeded_backend, "ab", "x@example.com", "password123")
    assert ok is False
    assert "3" in msg


@pytest.mark.asyncio
async def test_register_user_invalid_username_chars(seeded_backend):
    ok, msg = await register_user(seeded_backend, "bad user!", "x@example.com", "password123")
    assert ok is False
    assert "letters" in msg


@pytest.mark.asyncio
async def test_register_user_password_too_short(seeded_backend):
    ok, msg = await register_user(seeded_backend, "validuser", "x@example.com", "short")
    assert ok is False
    assert "8" in msg
