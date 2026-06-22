"""Harness evals: ingestion produces enriched chunks; embedding provider check; stale detection."""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE_RULES = FIXTURES / "sample_rules.md"
SAMPLE_GM_ONLY = FIXTURES / "sample_gm_only.md"


# ── Eval 1: MD ingest produces enriched chunks ────────────────────────────────

class TestMarkdownIngestionProducesEnrichedChunks:
    """Ingest sample_rules.md and verify chunks have required metadata fields."""

    @pytest.mark.asyncio
    async def test_md_ingest_chunk_count(self) -> None:
        from rag.knowledge.chunker import MarkdownChunker
        from rag.knowledge.ingestor import MarkdownIngestor

        ingestor = MarkdownIngestor(chunker=MarkdownChunker(max_tokens=800))
        chunks = ingestor.ingest(str(SAMPLE_RULES))

        assert len(chunks) >= 1, "Expected at least one chunk from sample_rules.md"

    @pytest.mark.asyncio
    async def test_md_ingest_enrichment_fields(self) -> None:
        """Each chunk must produce non-empty headline, summary, topic, valid access_level."""
        from unittest.mock import AsyncMock

        from rag.knowledge.enricher import ChunkEnricher
        from rag.knowledge.ingestor import MarkdownIngestor

        mock_llm = AsyncMock()
        mock_llm.generate = AsyncMock(
            return_value='{"headline": "Combat Initiative", "summary": "DEX step roll.", '
            '"topic": "combat/initiative", "access_level": "player_visible"}'
        )

        ingestor = MarkdownIngestor()
        enricher = ChunkEnricher(mock_llm)

        chunks = ingestor.ingest(str(SAMPLE_RULES))
        assert chunks, "Expected chunks from sample_rules.md"

        enrichment = await enricher.enrich_chunk(chunks[0])
        assert enrichment.headline, "headline must not be empty"
        assert enrichment.summary, "summary must not be empty"
        assert enrichment.topic, "topic must not be empty"
        assert enrichment.access_level in (
            "gm_only",
            "player_visible",
        ), "access_level must be 'gm_only' or 'player_visible'"

    @pytest.mark.asyncio
    async def test_enrichment_fallback_on_bad_json(self) -> None:
        """Enricher falls back gracefully when LLM returns invalid JSON twice."""
        from rag.knowledge.enricher import ChunkEnricher

        mock_llm = AsyncMock()
        mock_llm.generate = AsyncMock(return_value="not valid json at all")

        enricher = ChunkEnricher(mock_llm)
        result = await enricher.enrich_chunk("Some text.")

        assert result.headline is not None
        assert result.access_level in ("gm_only", "player_visible")


# ── Eval 2: Embedding model check ─────────────────────────────────────────────

class TestEmbeddingModelUnavailable:
    """When nomic-embed-text is unavailable the system raises ProviderUnavailableError."""

    @pytest.mark.asyncio
    async def test_unavailable_embed_model_raises(self) -> None:
        from core.errors import ProviderUnavailableError
        from rag.knowledge.retriever import ChromaKnowledgeRetriever

        retriever = ChromaKnowledgeRetriever()

        with patch.dict(
            os.environ,
            {"KNOWLEDGE_EMBED_MODEL": "nonexistent-model-xyz", "OLLAMA_BASE_URL": "http://127.0.0.1:9"},
        ):
            with pytest.raises(ProviderUnavailableError):
                await retriever.add_chunk(
                    chunk_id="test_0000",
                    text="Some text.",
                    metadata={"doc_id": "test", "doc_title": "Test"},
                    scope="global",
                    campaign_id=None,
                )


# ── Eval 3: Stale processing detection ────────────────────────────────────────

class TestStaleProcessingDetection:
    """Document with status=processing and updated_at >15 min shows stale warning."""

    def test_stale_status_string(self) -> None:
        from pages.gm.knowledge_qa import _format_status
        from core.models import KnowledgeDocument

        stale_doc = KnowledgeDocument()
        stale_doc.ingestion_status = "processing"
        stale_doc.updated_at = datetime.now(UTC) - timedelta(minutes=20)
        stale_doc.error_message = None
        stale_doc.chunk_count = None

        status = _format_status(stale_doc)
        assert "stalled" in status.lower() or "⚠️" in status, (
            f"Expected stale warning for processing doc older than 15 min, got: {status!r}"
        )

    def test_fresh_processing_not_stale(self) -> None:
        from pages.gm.knowledge_qa import _format_status
        from core.models import KnowledgeDocument

        fresh_doc = KnowledgeDocument()
        fresh_doc.ingestion_status = "processing"
        fresh_doc.updated_at = datetime.now(UTC) - timedelta(minutes=5)
        fresh_doc.error_message = None
        fresh_doc.chunk_count = None

        status = _format_status(fresh_doc)
        assert "⏳" in status, f"Expected processing indicator for fresh doc, got: {status!r}"
        assert "stalled" not in status.lower()
