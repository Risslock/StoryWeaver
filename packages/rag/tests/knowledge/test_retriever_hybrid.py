"""Unit tests for weighted-RRF hybrid fusion in ChromaKnowledgeRetriever.search() (feature 014)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from rag.knowledge.enricher import ChunkEnricher
from rag.knowledge.lexical_store import SQLiteLexicalStore
from rag.knowledge.retriever import ChromaKnowledgeRetriever
from rag.knowledge.vector_store import ChromaVectorStore


def _chroma_result(ids: list[str], texts: list[str]) -> dict:
    return {
        "ids": [ids],
        "metadatas": [[{"doc_id": "doc1", "scope": "global", "campaign_id": "", "access_level": "player_visible"} for _ in ids]],
        "documents": [texts],
    }


@pytest.fixture(autouse=True)
def _patch_enricher():
    """No query expansion, identity reranking — isolates the fusion math under test."""
    with (
        patch.object(ChunkEnricher, "expand_query", new=AsyncMock(return_value=[])),
        patch.object(
            ChunkEnricher, "rerank",
            new=AsyncMock(side_effect=lambda question, chunks: list(range(len(chunks)))),
        ),
    ):
        yield


@pytest.fixture(autouse=True)
def _patch_embed():
    with patch.object(
        ChromaKnowledgeRetriever, "_embed_query", new=AsyncMock(return_value=[0.1, 0.2, 0.3])
    ):
        yield


async def _run_search(monkeypatch, *, hybrid_enabled: bool, keyword_weight: float = 1.0, vector_weight: float = 1.0):
    from core.config import settings as _cfg

    monkeypatch.setattr(_cfg, "hybrid_search_enabled", hybrid_enabled)
    monkeypatch.setattr(_cfg, "hybrid_search_keyword_weight", keyword_weight)
    monkeypatch.setattr(_cfg, "hybrid_search_vector_weight", vector_weight)

    vector_result = _chroma_result(["chunk_A", "chunk_C"], ["text A", "text C"])
    lexical_result = [
        ("chunk_B", {"doc_id": "doc1", "scope": "global", "campaign_id": "", "access_level": "player_visible", "original_text": "text B"}, "text B"),
        ("chunk_C", {"doc_id": "doc1", "scope": "global", "campaign_id": "", "access_level": "player_visible", "original_text": "text C"}, "text C"),
    ]

    with (
        patch.object(ChromaVectorStore, "query", new=AsyncMock(return_value=vector_result)),
        patch.object(SQLiteLexicalStore, "query", new=AsyncMock(return_value=lexical_result)) as mock_lexical_query,
    ):
        retriever = ChromaKnowledgeRetriever()
        results = await retriever.search(query="test query", campaign_id="", role="gm", top_k=10)

    return results, mock_lexical_query


class TestDisabledPathMatchesVectorOnlyBaseline:
    @pytest.mark.asyncio
    async def test_disabled_output_matches_hand_computed_vector_only(self, monkeypatch) -> None:
        results, mock_lexical_query = await _run_search(monkeypatch, hybrid_enabled=False)

        mock_lexical_query.assert_not_called()

        by_id = {c.chunk_id: c for c in results}
        assert set(by_id) == {"chunk_A", "chunk_C"}

        from core.config import settings as _cfg

        rrf_k = _cfg.knowledge_rrf_k
        expected_a = 1.0 / (rrf_k + 0 + 1)
        expected_c = 1.0 / (rrf_k + 1 + 1)

        assert by_id["chunk_A"].rrf_score == pytest.approx(expected_a)
        assert by_id["chunk_C"].rrf_score == pytest.approx(expected_c)
        assert by_id["chunk_A"].matched_signals == ["vector"]
        assert by_id["chunk_C"].matched_signals == ["vector"]

        # chunk_A ranks above chunk_C (higher RRF score → earlier in output)
        ids_in_order = [c.chunk_id for c in results]
        assert ids_in_order.index("chunk_A") < ids_in_order.index("chunk_C")

    @pytest.mark.asyncio
    async def test_disabled_output_matches_frozen_pre_014_snapshot(self, monkeypatch) -> None:
        """Regression snapshot: literal expected values, not the production formula re-derived.

        rrf_k is pinned to 30 so this test's expected floats stay fixed regardless of
        local .env overrides (KNOWLEDGE_RRF_K defaults to 30 but dev .env sets 10).
        """
        from core.config import settings as _cfg

        monkeypatch.setattr(_cfg, "knowledge_rrf_k", 30)
        results, _ = await _run_search(monkeypatch, hybrid_enabled=False)
        by_id = {c.chunk_id: c for c in results}

        assert by_id["chunk_A"].rrf_score == pytest.approx(0.032258064516129034)
        assert by_id["chunk_C"].rrf_score == pytest.approx(0.03125)
        assert by_id["chunk_A"].matched_signals == ["vector"]
        assert by_id["chunk_C"].matched_signals == ["vector"]
        assert [c.chunk_id for c in results] == ["chunk_A", "chunk_C"]


class TestHybridEnabledFusion:
    @pytest.mark.asyncio
    async def test_lexical_only_chunk_tagged_lexical(self, monkeypatch) -> None:
        results, _ = await _run_search(monkeypatch, hybrid_enabled=True)
        by_id = {c.chunk_id: c for c in results}
        assert by_id["chunk_B"].matched_signals == ["lexical"]

    @pytest.mark.asyncio
    async def test_chunk_in_both_lists_tagged_both_signals(self, monkeypatch) -> None:
        results, _ = await _run_search(monkeypatch, hybrid_enabled=True)
        by_id = {c.chunk_id: c for c in results}
        assert set(by_id["chunk_C"].matched_signals) == {"vector", "lexical"}

    @pytest.mark.asyncio
    async def test_vector_only_chunk_unaffected_by_lexical_signal(self, monkeypatch) -> None:
        results, _ = await _run_search(monkeypatch, hybrid_enabled=True)
        by_id = {c.chunk_id: c for c in results}
        assert by_id["chunk_A"].matched_signals == ["vector"]

    @pytest.mark.asyncio
    async def test_increasing_keyword_weight_raises_lexical_only_rank(self, monkeypatch) -> None:
        # At default (1.0/1.0) weights, chunk_B (lexical-only, rank 0) and chunk_A
        # (vector-only, rank 0) score identically — a tie, not a clear rank relationship.
        results_default, _ = await _run_search(monkeypatch, hybrid_enabled=True, keyword_weight=1.0)
        by_id_default = {c.chunk_id: c for c in results_default}
        assert by_id_default["chunk_A"].rrf_score == pytest.approx(by_id_default["chunk_B"].rrf_score)

        # Raising keyword_weight must push chunk_B's score above chunk_A's fixed baseline.
        results_boosted, _ = await _run_search(monkeypatch, hybrid_enabled=True, keyword_weight=3.0)
        by_id_boosted = {c.chunk_id: c for c in results_boosted}
        assert by_id_boosted["chunk_B"].rrf_score > by_id_boosted["chunk_A"].rrf_score
