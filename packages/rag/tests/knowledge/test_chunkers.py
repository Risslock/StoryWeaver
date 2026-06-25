"""Unit tests for HeadingChunker, SemanticChunker, and AgenticChunker.

All tests use stub embed_fn / stub LLM provider — no Ollama required.
"""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import AsyncMock

import pytest

from rag.knowledge.chunker import HeadingChunker


# ── HeadingChunker ─────────────────────────────────────────────────────────────


class TestHeadingChunker:
    """Invariant tests for HeadingChunker (verifies T003 rename did not break behaviour)."""

    def test_empty_input_returns_empty(self) -> None:
        assert HeadingChunker().chunk("") == []

    def test_whitespace_only_returns_empty(self) -> None:
        assert HeadingChunker().chunk("   \n\n  ") == []

    def test_no_empty_strings_returned(self) -> None:
        text = "## Section A\n\nSome content here.\n\n## Section B\n\nMore content."
        chunks = HeadingChunker().chunk(text)
        assert all(c.strip() for c in chunks), "No chunk should be empty or whitespace-only"

    def test_table_and_heading_stay_together(self) -> None:
        """A table immediately following a heading must remain in the same chunk."""
        text = (
            "## Difficulty Numbers\n"
            "| DN | Description |\n"
            "|----|--------------|\n"
            "| 5  | Easy         |\n"
            "| 10 | Average      |\n"
        )
        chunker = HeadingChunker(max_tokens=800)
        chunks = chunker.chunk(text)
        assert len(chunks) == 1, (
            f"Heading + table should be one chunk, got {len(chunks)}: {chunks}"
        )
        assert "Difficulty Numbers" in chunks[0]
        assert "DN" in chunks[0]

    def test_heading_splits_produce_multiple_chunks(self) -> None:
        text = (
            "## Section A\n\nContent for A.\n\n"
            "## Section B\n\nContent for B.\n\n"
            "## Section C\n\nContent for C."
        )
        chunks = HeadingChunker().chunk(text)
        assert len(chunks) >= 3

    def test_oversized_chunk_is_split(self) -> None:
        long_paragraph = "Word " * 300  # ~1500 tokens at 4 chars/token estimate
        text = f"## Big Section\n\n{long_paragraph}"
        chunks = HeadingChunker(max_tokens=200).chunk(text)
        assert len(chunks) >= 2


# ── Stub helpers for SemanticChunker ──────────────────────────────────────────


class _HighSimilarityEmbedFn:
    """Returns identical vectors → cosine similarity = 1.0 for all pairs → one chunk."""

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0, 0.0]] * len(texts)


class _LowSimilarityEmbedFn:
    """Returns orthogonal vectors → cosine similarity = 0.0 for all pairs → many splits."""

    async def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for i, _ in enumerate(texts):
            v = [0.0, 0.0, 0.0]
            v[i % 3] = 1.0
            vectors.append(v)
        return vectors


# ── SemanticChunker ────────────────────────────────────────────────────────────


class TestSemanticChunker:
    """Unit tests for SemanticChunker using stub EmbedFn (no Ollama required)."""

    def _get_chunker(self, embed_fn: object) -> "Any":
        from rag.knowledge.chunker_semantic import SemanticChunker
        return SemanticChunker(embed_fn=embed_fn)

    def test_empty_input_returns_empty(self) -> None:
        chunker = self._get_chunker(_HighSimilarityEmbedFn())
        assert chunker.chunk("") == []

    def test_whitespace_only_returns_empty(self) -> None:
        chunker = self._get_chunker(_HighSimilarityEmbedFn())
        assert chunker.chunk("   \n\n  ") == []

    @pytest.mark.asyncio
    async def test_no_empty_chunks_returned(self) -> None:
        text = "The quick brown fox. Jumped over the lazy dog. It was a fine day."
        chunker = self._get_chunker(_HighSimilarityEmbedFn())
        chunks = await chunker.async_chunk(text)
        assert all(c.strip() for c in chunks)

    @pytest.mark.asyncio
    async def test_high_similarity_produces_single_chunk(self) -> None:
        """All sentences highly similar → no breakpoints → one chunk."""
        text = (
            "Earthdawn uses a step-based dice system. "
            "Each attribute has a Step number. "
            "The Step number determines which dice to roll."
        )
        chunker = self._get_chunker(_HighSimilarityEmbedFn())
        chunks = await chunker.async_chunk(text)
        assert len(chunks) == 1

    @pytest.mark.asyncio
    async def test_low_similarity_produces_multiple_chunks(self) -> None:
        """Orthogonal embeddings → all pairs are breakpoints → multiple chunks."""
        sentences = [f"Sentence number {i} about topic {i}." for i in range(6)]
        text = " ".join(sentences)
        chunker = self._get_chunker(_LowSimilarityEmbedFn())
        chunker._min_chunk_tokens = 1  # disable merging so splits survive
        chunks = await chunker.async_chunk(text)
        assert len(chunks) >= 2

    @pytest.mark.asyncio
    async def test_table_row_and_heading_stay_together(self) -> None:
        """A Markdown table and its preceding heading must stay in the same chunk."""
        text = (
            "## Difficulty Numbers\n"
            "| DN | Description |\n"
            "|----|--------------|\n"
            "| 5  | Easy         |\n"
        )
        chunker = self._get_chunker(_LowSimilarityEmbedFn())
        chunks = await chunker.async_chunk(text)
        combined = " ".join(chunks)
        assert "Difficulty Numbers" in combined
        assert "DN" in combined
        # Heading and table header should appear in the same chunk
        for chunk in chunks:
            if "Difficulty Numbers" in chunk:
                assert "DN" in chunk, "Heading and table must be in the same chunk"
                break


# ── Stub helpers for AgenticChunker ───────────────────────────────────────────


class _StubLLMProvider:
    """Returns a canned JSON response splitting section 0 at sentence index 2."""

    async def generate(self, prompt: str, system: str = "", **kwargs: object) -> str:
        return '{"chunks": [{"section": 0, "start_sentence": 2}]}'


class _NoSplitBatchProvider:
    """Returns no boundaries — all sections in the batch merge into one chunk."""

    async def generate(self, prompt: str, system: str = "", **kwargs: object) -> str:
        return '{"chunks": []}'


class _Section1SplitProvider:
    """Returns a boundary at section 1 sentence 0 — two chunks, no cross-section merge."""

    async def generate(self, prompt: str, system: str = "", **kwargs: object) -> str:
        return '{"chunks": [{"section": 1, "start_sentence": 0}]}'


class _UnparsableLLMProvider:
    """Returns text that cannot be parsed as the expected JSON schema."""

    async def generate(self, prompt: str, system: str = "", **kwargs: object) -> str:
        return "I cannot process this request."


class _UnreachableLLMProvider:
    """Raises ProviderUnavailableError on every call."""

    async def generate(self, prompt: str, system: str = "", **kwargs: object) -> str:
        from core.errors import ProviderUnavailableError
        raise ProviderUnavailableError("LLM not reachable")


# ── AgenticChunker ─────────────────────────────────────────────────────────────


class TestAgenticChunker:
    """Unit tests for AgenticChunker using stub LLMProvider (no Ollama required)."""

    def _get_chunker(self, llm_provider: object) -> "Any":
        from rag.knowledge.chunker_agentic import AgenticChunker
        return AgenticChunker(llm_provider=llm_provider)

    def test_chunk_raises_not_implemented(self) -> None:
        chunker = self._get_chunker(_StubLLMProvider())
        with pytest.raises(NotImplementedError):
            chunker.chunk("some text")

    @pytest.mark.asyncio
    async def test_valid_llm_response_produces_two_chunks(self) -> None:
        """LLM returns {"splits": [2]} → two chunks from a multi-sentence section."""
        text = (
            "## Combat\n\n"
            "First sentence about combat. "
            "Second sentence about initiative. "
            "Third sentence about damage."
        )
        chunker = self._get_chunker(_StubLLMProvider())
        chunks = await chunker.async_chunk(text)
        assert len(chunks) >= 2

    @pytest.mark.asyncio
    async def test_unparsable_json_returns_full_section(self, caplog: pytest.LogCaptureFixture) -> None:
        """On parse failure the entire section is returned as one chunk, a WARNING is logged."""
        text = "## Talents\n\nA Talent is a special ability. It costs Karma to activate."
        chunker = self._get_chunker(_UnparsableLLMProvider())
        with caplog.at_level(logging.WARNING, logger="rag.knowledge.chunker_agentic"):
            chunks = await chunker.async_chunk(text)
        assert len(chunks) >= 1
        assert any("WARNING" in r.levelname or r.levelno >= logging.WARNING for r in caplog.records)

    @pytest.mark.asyncio
    async def test_provider_unavailable_propagates(self) -> None:
        """ProviderUnavailableError from LLM must propagate out of async_chunk."""
        from core.errors import ProviderUnavailableError
        # Needs multiple sentences so _chunk_section actually calls the LLM.
        text = (
            "## Some Section\n\n"
            "First sentence of content. Second sentence of content. Third sentence of content."
        )
        chunker = self._get_chunker(_UnreachableLLMProvider())
        with pytest.raises(ProviderUnavailableError):
            await chunker.async_chunk(text)

    @pytest.mark.asyncio
    async def test_table_and_heading_stay_together(self) -> None:
        """Table + heading must stay in the same chunk even when LLM splits inside a table."""
        text = (
            "## Difficulty Numbers\n"
            "| DN | Description |\n"
            "|----|--------------|\n"
            "| 5  | Easy         |\n"
        )
        chunker = self._get_chunker(_StubLLMProvider())
        chunks = await chunker.async_chunk(text)
        combined = " ".join(chunks)
        assert "Difficulty Numbers" in combined
        assert "DN" in combined
        for chunk in chunks:
            if "Difficulty Numbers" in chunk:
                assert "DN" in chunk, "Heading and table must be in the same chunk"
                break


# ── AgenticChunker — batch behavior ───────────────────────────────────────────


class TestAgenticChunkerBatch:
    """Tests for batch_sections > 1 behavior: cross-section merging and fallback."""

    _TWO_SECTION_TEXT = (
        "## Overview\n\nCombat is turn-based. Each combatant acts in initiative order.\n\n"
        "## Turn Order\n\nInitiative determines who acts first. Roll your Dexterity step."
    )

    def _get_chunker(self, llm_provider: object, batch_sections: int = 2) -> "Any":
        from rag.knowledge.chunker_agentic import AgenticChunker
        return AgenticChunker(llm_provider=llm_provider, batch_sections=batch_sections)

    @pytest.mark.asyncio
    async def test_no_boundary_merges_adjacent_sections(self) -> None:
        """LLM returns no boundaries → both sections merge into a single chunk."""
        chunker = self._get_chunker(_NoSplitBatchProvider(), batch_sections=2)
        chunks = await chunker.async_chunk(self._TWO_SECTION_TEXT)
        assert len(chunks) == 1, f"Expected 1 merged chunk, got {len(chunks)}: {chunks}"
        assert "Overview" in chunks[0] or "Turn Order" in chunks[0]

    @pytest.mark.asyncio
    async def test_section_boundary_keeps_sections_separate(self) -> None:
        """LLM returns boundary at section 1 sentence 0 → two separate chunks."""
        chunker = self._get_chunker(_Section1SplitProvider(), batch_sections=2)
        chunks = await chunker.async_chunk(self._TWO_SECTION_TEXT)
        assert len(chunks) >= 2, f"Expected at least 2 chunks, got {len(chunks)}: {chunks}"

    @pytest.mark.asyncio
    async def test_parse_failure_returns_one_chunk_per_section(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """On unparseable LLM response for a batch of 2, fallback yields one chunk per section."""
        chunker = self._get_chunker(_UnparsableLLMProvider(), batch_sections=2)
        with caplog.at_level(logging.WARNING, logger="rag.knowledge.chunker_agentic"):
            chunks = await chunker.async_chunk(self._TWO_SECTION_TEXT)
        assert len(chunks) == 2, (
            f"Batch fallback should yield one chunk per section, got {len(chunks)}"
        )
        assert any(r.levelno >= logging.WARNING for r in caplog.records)
