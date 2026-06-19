"""Unit tests for services/auth.py."""

from __future__ import annotations

import pytest
import pytest_asyncio
from core.models import User
from services.auth import (
    hash_password,
    make_auth_callable,
    register_user,
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


def test_hash_password_produces_bcrypt_hash():
    hashed = hash_password("mypassword")
    assert hashed.startswith("$2b$") or hashed.startswith("$2a$")
    assert hashed != "mypassword"


def test_verify_password_correct():
    hashed = hash_password("correct")
    assert verify_password("correct", hashed) is True


def test_verify_password_wrong():
    hashed = hash_password("correct")
    assert verify_password("wrong", hashed) is False


# ── make_auth_callable ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_make_auth_callable_valid_user(seeded_backend):
    ok, _ = await register_user(seeded_backend, "alice", "alice@example.com", "password123")
    assert ok

    validate = make_auth_callable(seeded_backend)
    assert validate("alice", "password123") is True


@pytest.mark.asyncio
async def test_make_auth_callable_wrong_password(seeded_backend):
    await register_user(seeded_backend, "bob", "bob@example.com", "password123")

    validate = make_auth_callable(seeded_backend)
    assert validate("bob", "wrongpassword") is False


@pytest.mark.asyncio
async def test_make_auth_callable_inactive_user(seeded_backend):
    await register_user(seeded_backend, "inactive", "inactive@example.com", "password123")

    # Manually deactivate the user
    async with await seeded_backend.get_session() as session:
        from sqlalchemy import select
        result = await session.execute(
            select(User).where(User.username == "inactive")
        )
        user = result.scalar_one()
        user.is_active = False
        await session.commit()

    validate = make_auth_callable(seeded_backend)
    assert validate("inactive", "password123") is False


@pytest.mark.asyncio
async def test_make_auth_callable_unknown_username(seeded_backend):
    validate = make_auth_callable(seeded_backend)
    assert validate("nobody", "whatever") is False


@pytest.mark.asyncio
async def test_make_auth_callable_db_exception():
    # Backend pointing at a non-existent path — simulates DB failure
    bad_backend = SQLiteBackend("sqlite+aiosqlite:///nonexistent_dir/bad.db")
    validate = make_auth_callable(bad_backend)
    assert validate("user", "pass") is False


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
