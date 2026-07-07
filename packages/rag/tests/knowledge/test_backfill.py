"""Unit tests for backfill_lexical_index.py idempotency (feature 014 — hybrid search)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from rag.knowledge.backfill_lexical_index import _parse_args, _run
from rag.knowledge.lexical_store import SQLiteLexicalStore
from rag.knowledge.vector_store import ChromaVectorStore


def _fixture_chroma_data() -> dict:
    return {
        "ids": ["doc1_0000", "doc1_0001"],
        "metadatas": [
            {"doc_id": "doc1", "scope": "global", "campaign_id": "", "access_level": "player_visible", "original_text": "Karma text one"},
            {"doc_id": "doc1", "scope": "global", "campaign_id": "", "access_level": "player_visible", "original_text": "Karma text two"},
        ],
    }


def _make_args(tmp_lexical_url: str, dry_run: bool = False) -> object:
    class _Args:
        pass

    args = _Args()
    args.campaign_id = None
    args.dry_run = dry_run
    args.chroma_path = "./data/chroma"
    return args


@pytest.mark.asyncio
async def test_backfill_twice_produces_same_row_count(tmp_path: object) -> None:
    db_file = f"{tmp_path}/{uuid.uuid4().hex}.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"

    with (
        patch.object(ChromaVectorStore, "get_all", new=AsyncMock(return_value=_fixture_chroma_data())),
        patch.object(ChromaVectorStore, "list_collection_names", new=AsyncMock(return_value=["knowledge_global"])),
        patch("rag.knowledge.backfill_lexical_index.SQLiteLexicalStore", lambda: SQLiteLexicalStore(database_url=db_url)),
    ):
        await _run(_make_args(db_url))
        await _run(_make_args(db_url))

    store = SQLiteLexicalStore(database_url=db_url)
    rows = await store.get_all(scope="global")
    assert len(rows) == 2, f"Expected 2 rows after two backfill runs, got {len(rows)}"


@pytest.mark.asyncio
async def test_dry_run_writes_zero_rows(tmp_path: object) -> None:
    db_file = f"{tmp_path}/{uuid.uuid4().hex}.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"

    with (
        patch.object(ChromaVectorStore, "get_all", new=AsyncMock(return_value=_fixture_chroma_data())),
        patch.object(ChromaVectorStore, "list_collection_names", new=AsyncMock(return_value=["knowledge_global"])),
        patch("rag.knowledge.backfill_lexical_index.SQLiteLexicalStore", lambda: SQLiteLexicalStore(database_url=db_url)),
    ):
        await _run(_make_args(db_url, dry_run=True))

    store = SQLiteLexicalStore(database_url=db_url)
    rows = await store.get_all(scope="global")
    assert rows == []


@pytest.mark.asyncio
async def test_invalid_campaign_id_exits_1() -> None:
    class _Args:
        campaign_id = "not-a-uuid"
        dry_run = False
        chroma_path = "./data/chroma"

    with pytest.raises(SystemExit) as exc_info:
        await _run(_Args())
    assert exc_info.value.code == 1


def test_parse_args_defaults(monkeypatch: object) -> None:
    import sys

    argv = ["backfill_lexical_index.py"]
    with patch.object(sys, "argv", argv):
        args = _parse_args()
    assert args.campaign_id is None
    assert args.dry_run is False
    assert args.chroma_path == "./data/chroma"
