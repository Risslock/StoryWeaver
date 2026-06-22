"""Live-Ollama integration tests for the RAG knowledge pipeline.

Three flows are tested end-to-end against a real Ollama instance:
  1. TestIngestionFlow   — MD file → chunker → enricher → embedder → ChromaDB
  2. TestRetrievalFlow   — query text → embed → ChromaDB search → KnowledgeChunks
  3. TestEndToEndQA      — ask_question() → retriever + LLM synthesis → cited answer
  4. TestFixtureBattery  — SC-004: ≥4 of 5 fixture questions return at least one citation

All tests are module-scoped: ingestion runs once; retrieval and QA reuse the same
ChromaDB session.  If Ollama is unreachable the entire module is skipped (SC-008).
"""

from __future__ import annotations

import os
import urllib.error
import urllib.request
import uuid
from functools import partial
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE_RULES = FIXTURES / "sample_rules.md"

# ── Module-level fixtures ──────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def ollama_available() -> None:
    """Skip the entire module if Ollama is not reachable (SC-008 auto-skip semantics)."""
    base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    try:
        with urllib.request.urlopen(f"{base_url}/api/tags", timeout=5):
            pass
    except (urllib.error.URLError, OSError):
        pytest.skip(f"Ollama not reachable at {base_url} — skipping integration tests")


@pytest.fixture(scope="module")
def tmp_chroma(tmp_path_factory: pytest.TempPathFactory) -> str:
    """Fresh ChromaDB directory per test session — never touches ./data/chroma."""
    return str(tmp_path_factory.mktemp("chroma"))


@pytest.fixture(scope="module")
def test_doc_id() -> str:
    """Fixed document UUID for the test KnowledgeDocument row."""
    return str(uuid.uuid4())


# ── T039: Ingestion flow ───────────────────────────────────────────────────────


class TestIngestionFlow:
    """MD → chunker → enricher → embedder → ChromaDB upsert (SC-002 flow, global scope)."""

    @pytest.mark.asyncio
    async def test_md_to_chunks_to_db(
        self,
        ollama_available: None,
        tmp_chroma: str,
        test_doc_id: str,
    ) -> None:
        from rag.knowledge.pipeline import IngestionPipeline
        from rag.knowledge.vector_store import GLOBAL_COLLECTION, ChromaVectorStore

        with (
            patch(
                "rag.knowledge.pipeline.IngestionPipeline._get_doc_title",
                new=AsyncMock(return_value="Sample Rules"),
            ),
            patch(
                "rag.knowledge.pipeline.IngestionPipeline._set_status",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "rag.knowledge.pipeline.IngestionPipeline._set_progress",
                new=AsyncMock(return_value=None),
            ),
        ):
            pipeline = IngestionPipeline(chroma_path=tmp_chroma)
            await pipeline.run(
                doc_id=test_doc_id,
                file_path=str(SAMPLE_RULES),
                format="markdown",
                access_level_default=None,
                scope="global",
                campaign_id=None,
            )

        store = ChromaVectorStore(chroma_path=tmp_chroma)
        col = store.collection(GLOBAL_COLLECTION)
        count = col.count()
        assert count >= 1, f"Expected ≥1 chunk after ingestion, got {count}"

        result = col.get(include=["metadatas", "documents"])
        for meta, doc in zip(result["metadatas"], result["documents"], strict=False):
            for key in ("doc_id", "doc_title", "headline", "summary", "topic", "access_level"):
                assert key in meta, f"Chunk metadata missing key: {key!r}"
            assert meta["access_level"] in (
                "gm_only",
                "player_visible",
            ), f"Invalid access_level: {meta['access_level']!r}"
            assert meta["headline"], "headline must not be empty"
            assert doc, "stored document text must not be empty"


# ── T040: Retrieval flow ───────────────────────────────────────────────────────


class TestRetrievalFlow:
    """Query text → OllamaEmbedFn → ChromaDB cosine search → ranked KnowledgeChunks."""

    @pytest.mark.asyncio
    async def test_query_returns_relevant_chunks(
        self,
        ollama_available: None,
        tmp_chroma: str,
    ) -> None:
        from rag.knowledge.retriever import ChromaKnowledgeRetriever

        retriever = ChromaKnowledgeRetriever(chroma_path=tmp_chroma)
        chunks = await retriever.search(
            query="How does combat initiative work?",
            campaign_id="test",
            role="gm",
            top_k=4,
        )

        assert len(chunks) >= 1, (
            "Retriever must return at least one chunk for a question about combat initiative"
        )
        assert chunks[0].rrf_score > 0, "Top chunk must have a positive RRF score"

        # Oracle: sample_rules.md §Combat Initiative contains "DEX step" somewhere in results
        all_text = " ".join(c.text.lower() for c in chunks)
        assert "dex" in all_text, (
            f"Expected DEX mention in retrieved chunks for initiative query. "
            f"Got top chunk: {chunks[0].text[:200]!r}"
        )

    @pytest.mark.asyncio
    async def test_player_role_filter_respected(
        self,
        ollama_available: None,
        tmp_chroma: str,
    ) -> None:
        """Player queries must only return player_visible chunks (SC-005)."""
        from rag.knowledge.retriever import ChromaKnowledgeRetriever

        retriever = ChromaKnowledgeRetriever(chroma_path=tmp_chroma)
        chunks = await retriever.search(
            query="How does combat initiative work?",
            campaign_id="test",
            role="player",
            top_k=4,
        )
        for chunk in chunks:
            assert chunk.access_level == "player_visible", (
                f"Player query returned gm_only chunk: {chunk.chunk_id}"
            )


# ── T041: End-to-end LLM synthesis ────────────────────────────────────────────


class TestEndToEndQA:
    """ask_question() → retriever + LLM synthesis → cited answer (SC-001 flow)."""

    @pytest.mark.asyncio
    async def test_llm_synthesises_answer(
        self,
        ollama_available: None,
        tmp_chroma: str,
    ) -> None:
        from rag.knowledge.retriever import ChromaKnowledgeRetriever

        # Patch at the definition site so both lazy imports in services.knowledge see it
        with patch(
            "rag.knowledge.retriever.ChromaKnowledgeRetriever",
            side_effect=partial(ChromaKnowledgeRetriever, chroma_path=tmp_chroma),
        ):
            from services.knowledge import ask_question

            answer, chunks = await ask_question(
                question="What step is used for initiative?",
                campaign_id=uuid.uuid4(),
                role="gm",
            )

        assert len(answer) > 0, "LLM must return a non-empty answer"
        assert "couldn't find" not in answer.lower(), (
            "FR-011 message must not fire when relevant content exists"
        )
        assert len(chunks) >= 1, "Answer must include at least one citation"
        assert chunks[0].doc_title, "Citation must have a non-empty doc_title"


# ── T042: SC-004 fixture battery ───────────────────────────────────────────────


class TestFixtureBattery:
    """SC-004: ≥4 of 5 fixture questions against sample_rules.md return ≥1 citation."""

    QUESTIONS = [
        "How does combat initiative work?",
        "What is a Talent?",
        "How do you use a Talent in combat?",
        "What are Difficulty Numbers?",
        "How does Karma work?",
    ]

    @pytest.mark.asyncio
    async def test_sc004_four_of_five_questions_cited(
        self,
        ollama_available: None,
        tmp_chroma: str,
    ) -> None:
        from rag.knowledge.retriever import ChromaKnowledgeRetriever

        retriever = ChromaKnowledgeRetriever(chroma_path=tmp_chroma)
        cited = 0
        details: list[str] = []

        for question in self.QUESTIONS:
            chunks = await retriever.search(
                query=question,
                campaign_id="test",
                role="gm",
                top_k=3,
            )
            if chunks:
                cited += 1
                details.append(f"  ✓ {question!r} → {len(chunks)} chunk(s)")
            else:
                details.append(f"  ✗ {question!r} → 0 chunks")

        summary = "\n".join(details)
        assert cited >= 4, (
            f"SC-004 requires ≥4 of 5 fixture questions to return citations.\n"
            f"Got {cited}/5:\n{summary}"
        )
