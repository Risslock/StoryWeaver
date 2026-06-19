"""FastAPI ASGI entry-point for StoryWeaver.

Serves the single Gradio app at /:
  /  — StoryWeaver (sign-in/register screen → campaign dashboard → gameplay)

FastAPI is used exclusively as an ASGI routing adapter.
No REST endpoints are defined here. See ADR-006 for rationale.

Usage:
    cd apps/web && uvicorn main:app --port 7860 --reload
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import gradio as gr
from app import create_app
from fastapi import FastAPI
from pages.landing import get_backend


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    # Schema is managed by Alembic — do NOT call initialize_db() here.
    # WAL mode is set via the event listener in SQLiteBackend on every connect.
    db = get_backend()
    if not await db.verify_wal_mode():
        raise RuntimeError(
            "SQLite WAL mode is not active. "
            "Run 'alembic upgrade head' before starting the server, "
            "and ensure the database URL points to a file-based SQLite path."
        )
    yield


fastapi_app = FastAPI(lifespan=lifespan)

main_blocks = create_app()

gr.mount_gradio_app(fastapi_app, main_blocks, path="/")

app = fastapi_app
