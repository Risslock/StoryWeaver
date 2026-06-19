"""Authentication helpers: hashing, credential validation, user registration."""

from __future__ import annotations

import asyncio
import re
import threading
from collections.abc import Callable

import bcrypt
from storage.interface import StorageBackend
from storage.users import create_user, get_user_by_username_or_email

# Dummy hash for constant-time comparison when username is not found.
_DUMMY_HASH = bcrypt.hashpw(b"__dummy__", bcrypt.gensalt())


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def _verify_bytes(plain: str, hashed: bytes) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed)


def make_auth_callable(backend: StorageBackend) -> Callable[[str, str], bool]:
    """Return a synchronous Gradio auth callable bound to *backend*.

    The returned function is synchronous — Gradio 4.x auth= does not accept
    async callables. Exceptions are swallowed and return False so Gradio never
    sees a crash on the login screen.
    """

    async def _validate(username: str, password: str) -> bool:
        try:
            async with await backend.get_session() as session:
                user = await get_user_by_username_or_email(session, username)
                if user is None:
                    _verify_bytes(password, _DUMMY_HASH)
                    return False
                if not user.is_active:
                    _verify_bytes(password, _DUMMY_HASH)
                    return False
                return verify_password(password, user.hashed_password)
        except Exception:
            return False

    def validate_credentials(username: str, password: str) -> bool:
        # Run async validation in a dedicated thread so this sync callable is
        # safe to call from both sync and async contexts (e.g. pytest-asyncio).
        result: list[bool] = [False]

        def _run() -> None:
            loop = asyncio.new_event_loop()
            try:
                result[0] = loop.run_until_complete(_validate(username, password))
            except Exception:
                result[0] = False
            finally:
                loop.close()

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        t.join()
        return result[0]

    return validate_credentials


async def validate_user(
    backend: StorageBackend,
    identifier: str,
    password: str,
) -> bool:
    """Return True if identifier+password match an active user, False otherwise.

    Always runs a bcrypt comparison (even on miss) to prevent timing attacks.
    """
    try:
        async with await backend.get_session() as session:
            user = await get_user_by_username_or_email(session, identifier)
            if user is None or not user.is_active:
                _verify_bytes(password, _DUMMY_HASH)
                return False
            return verify_password(password, user.hashed_password)
    except Exception:
        return False


_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_]+$")


async def register_user(
    backend: StorageBackend,
    username: str,
    email: str,
    password: str,
) -> tuple[bool, str]:
    """Validate input, hash password, and insert a new User row.

    Returns (True, "") on success or (False, error_message) on failure.
    """
    username = username.strip()
    email = email.lower().strip()

    if not (3 <= len(username) <= 50):
        return False, "Username must be 3–50 characters."
    if not _USERNAME_RE.match(username):
        return (
            False,
            "Username may only contain letters, numbers, and underscores.",
        )
    if "@" not in email or "." not in email.split("@")[-1]:
        return False, "Enter a valid email address."
    if len(password) < 8:
        return False, "Password must be at least 8 characters."

    hashed = hash_password(password)

    try:
        async with await backend.get_session() as session:
            existing = await get_user_by_username_or_email(session, username)
            if existing is not None and existing.username.lower() == username.lower():
                return (
                    False,
                    f"Username '{username}' is already registered. "
                    "Choose a different one.",
                )
            if existing is not None:
                return False, "An account with that email address already exists."

            existing_email = await get_user_by_username_or_email(session, email)
            if existing_email is not None:
                return False, "An account with that email address already exists."

            await create_user(session, username, email, hashed)
            return True, ""
    except Exception:
        return False, "Something went wrong. Please try again."
