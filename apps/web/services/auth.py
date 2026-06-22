"""Authentication helpers: hashing, credential validation, user registration."""

from __future__ import annotations

import hashlib
import re

from storage.interface import StorageBackend
from storage.users import create_user, get_user_by_username_or_email


def hash_password(plain: str) -> str:
    return hashlib.sha256(plain.encode()).hexdigest()


def verify_password(plain: str, hashed: str) -> bool:
    return hashlib.sha256(plain.encode()).hexdigest() == hashed


async def validate_user(
    backend: StorageBackend,
    identifier: str,
    password: str,
) -> bool:
    """Return True if identifier+password match an active user, False otherwise."""
    try:
        async with await backend.get_session() as session:
            user = await get_user_by_username_or_email(session, identifier)
            if user is None or not user.is_active:
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