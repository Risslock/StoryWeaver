"""Unit tests for SQLiteLexicalStore (feature 014 — hybrid search)."""

from __future__ import annotations

import uuid

import pytest
from rag.knowledge.lexical_store import SQLiteLexicalStore


def _tmp_store(tmp_path: object) -> SQLiteLexicalStore:
    db_file = f"{tmp_path}/{uuid.uuid4().hex}.db"
    url = f"sqlite+aiosqlite:///{db_file}"
    return SQLiteLexicalStore(database_url=url)


@pytest.mark.asyncio
async def test_ensure_table_is_idempotent(tmp_path: object) -> None:
    store = _tmp_store(tmp_path)
    await store.ensure_table()
    await store.ensure_table()  # must not raise


@pytest.mark.asyncio
async def test_upsert_and_query_round_trip(tmp_path: object) -> None:
    store = _tmp_store(tmp_path)
    await store.ensure_table()

    await store.upsert(
        ids=["doc1_0000"],
        texts=["The Second Wind talent restores Karma."],
        metadatas=[{
            "doc_id": "doc1", "scope": "global", "campaign_id": "",
            "access_level": "player_visible",
        }],
    )

    results = await store.query("Second Wind", scope="global", role="gm", top_k=10)
    assert len(results) == 1
    chunk_id, meta, text = results[0]
    assert chunk_id == "doc1_0000"
    assert "Second Wind" in text


@pytest.mark.asyncio
async def test_upsert_replaces_existing_chunk_id(tmp_path: object) -> None:
    store = _tmp_store(tmp_path)
    await store.ensure_table()

    meta = {"doc_id": "doc1", "scope": "global", "campaign_id": "", "access_level": "player_visible"}
    await store.upsert(ids=["doc1_0000"], texts=["original text about Karma"], metadatas=[meta])
    await store.upsert(ids=["doc1_0000"], texts=["updated text about Karma Points"], metadatas=[meta])

    results = await store.query("Karma", scope="global", role="gm", top_k=10)
    assert len(results) == 1
    assert "updated" in results[0][2]


@pytest.mark.asyncio
async def test_query_filters_by_scope(tmp_path: object) -> None:
    store = _tmp_store(tmp_path)
    await store.ensure_table()

    campaign_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
    await store.upsert(
        ids=["doc1_0000", "doc2_0000"],
        texts=["Karma in the global rulebook", "Karma house rule for this campaign"],
        metadatas=[
            {"doc_id": "doc1", "scope": "global", "campaign_id": "", "access_level": "player_visible"},
            {"doc_id": "doc2", "scope": campaign_id, "campaign_id": campaign_id, "access_level": "player_visible"},
        ],
    )

    global_results = await store.query("Karma", scope="global", role="gm", top_k=10)
    assert {r[0] for r in global_results} == {"doc1_0000"}

    campaign_results = await store.query("Karma", scope=campaign_id, role="gm", top_k=10)
    assert {r[0] for r in campaign_results} == {"doc2_0000"}


@pytest.mark.asyncio
async def test_query_role_player_excludes_gm_only(tmp_path: object) -> None:
    store = _tmp_store(tmp_path)
    await store.ensure_table()

    await store.upsert(
        ids=["doc1_0000", "doc1_0001"],
        texts=["Karma for players", "Karma GM secret"],
        metadatas=[
            {"doc_id": "doc1", "scope": "global", "campaign_id": "", "access_level": "player_visible"},
            {"doc_id": "doc1", "scope": "global", "campaign_id": "", "access_level": "gm_only"},
        ],
    )

    player_results = await store.query("Karma", scope="global", role="player", top_k=10)
    assert {r[0] for r in player_results} == {"doc1_0000"}

    gm_results = await store.query("Karma", scope="global", role="gm", top_k=10)
    assert {r[0] for r in gm_results} == {"doc1_0000", "doc1_0001"}


@pytest.mark.asyncio
async def test_query_empty_scope_returns_empty_list(tmp_path: object) -> None:
    store = _tmp_store(tmp_path)
    await store.ensure_table()
    results = await store.query("anything", scope="global", role="gm", top_k=10)
    assert results == []


@pytest.mark.asyncio
async def test_query_zero_terms_returns_empty_list(tmp_path: object) -> None:
    store = _tmp_store(tmp_path)
    await store.ensure_table()
    await store.upsert(
        ids=["doc1_0000"],
        texts=["Karma"],
        metadatas=[{"doc_id": "doc1", "scope": "global", "campaign_id": "", "access_level": "player_visible"}],
    )
    results = await store.query("!!!", scope="global", role="gm", top_k=10)
    assert results == []


@pytest.mark.asyncio
async def test_delete_by_doc_removes_all_rows(tmp_path: object) -> None:
    store = _tmp_store(tmp_path)
    await store.ensure_table()

    await store.upsert(
        ids=["doc1_0000", "doc1_0001"],
        texts=["Karma one", "Karma two"],
        metadatas=[
            {"doc_id": "doc1", "scope": "global", "campaign_id": "", "access_level": "player_visible"},
            {"doc_id": "doc1", "scope": "global", "campaign_id": "", "access_level": "player_visible"},
        ],
    )

    await store.delete_by_doc("doc1")
    results = await store.query("Karma", scope="global", role="gm", top_k=10)
    assert results == []


@pytest.mark.asyncio
async def test_delete_by_doc_unknown_doc_id_is_noop(tmp_path: object) -> None:
    store = _tmp_store(tmp_path)
    await store.ensure_table()
    await store.delete_by_doc("unknown-doc-id")  # must not raise
