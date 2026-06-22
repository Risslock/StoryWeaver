"""SQLite backend singleton for the web application."""

from __future__ import annotations

from core.config import settings
from storage.sqlite.adapter import SQLiteBackend

_backend = SQLiteBackend(settings.database_url)


def get_backend() -> SQLiteBackend:
    """Return the module-level storage backend singleton."""
    return _backend
