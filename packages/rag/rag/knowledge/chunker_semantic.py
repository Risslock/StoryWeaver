"""SemanticChunker: embedding-similarity breakpoint chunking strategy.

DEPRECATED(012): SemanticChunker is superseded by DoclingIngestor + HybridChunker for the active
PDF ingestion path (extraction_mode="docling", feature 012, spike PR #19).
SemanticChunker is retained for the legacy text and vision extraction paths.
"""

from __future__ import annotations

import logging
import math
import re

from core.config import settings as _cfg

from rag.knowledge.chunker import BaseChunker
from rag.knowledge.chunker import estimate_tokens as _estimate_tokens

_log = logging.getLogger(__name__)

_DEFAULT_MAX_TOKENS = 800
_DEFAULT_BREAKPOINT_PERCENTILE = 95
_DEFAULT_MIN_CHUNK_TOKENS = 50

# Lines starting with # or | are atomic sentence units (headings / table rows).
_ATOMIC_LINE_RE = re.compile(r"^[#|]")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def _split_sentences(text: str) -> list[str]:
    """Split Markdown text into sentence-level units.

    Heading lines (starting with #) and table rows (starting with |) are
    treated as single atomic units regardless of punctuation.
    """
    lines = text.splitlines()
    sentences: list[str] = []
    pending: list[str] = []

    def _flush() -> None:
        if pending:
            blob = " ".join(pending).strip()
            if blob:
                parts = _SENTENCE_SPLIT_RE.split(blob)
                sentences.extend(p.strip() for p in parts if p.strip())
            pending.clear()

    for line in lines:
        if _ATOMIC_LINE_RE.match(line.strip()):
            _flush()
            stripped = line.strip()
            if stripped:
                sentences.append(stripped)
        else:
            stripped = line.strip()
            if stripped:
                pending.append(stripped)
            else:
                _flush()

    _flush()
    return sentences


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0.0 or mag_b == 0.0:
        return 0.0
    return dot / (mag_a * mag_b)


def _find_breakpoints(similarities: list[float], percentile: int) -> list[int]:
    """Return indices i where similarity[i] (between sentence i and i+1) is below threshold.

    Threshold = the `percentile`-th percentile of all similarity values
    (i.e., the bottom (100-percentile)% most dissimilar pairs become split points).
    """
    if not similarities:
        return []
    sorted_sims = sorted(similarities)
    idx = max(0, int(len(sorted_sims) * (100 - percentile) / 100) - 1)
    threshold = sorted_sims[idx]
    return [i for i, s in enumerate(similarities) if s <= threshold]


class SemanticChunker(BaseChunker):
    """Split Markdown using embedding-similarity breakpoints between adjacent sentences.

    Batch-embeds all sentences in one call, finds low-similarity breakpoints,
    groups sentences into chunks, merges/splits to token budget, enforces table atomicity.
    """

    @property
    def strategy_name(self) -> str:
        return "semantic"

    def __init__(
        self,
        embed_fn: object = None,
        max_tokens: int | None = None,
        breakpoint_percentile: int | None = None,
        min_chunk_tokens: int | None = None,
    ) -> None:
        _log.warning(
            "SemanticChunker is deprecated (feature 012). "
            "Use extraction_mode='docling' to chunk via HybridChunker instead."
        )
        self._embed_fn = embed_fn
        self._max_tokens = max_tokens or _cfg.knowledge_max_chunk_tokens
        self._breakpoint_percentile = breakpoint_percentile or _cfg.knowledge_semantic_breakpoint_percentile
        self._min_chunk_tokens = min_chunk_tokens or _cfg.knowledge_semantic_min_chunk_tokens

    def chunk(self, text: str) -> list[str]:
        """Synchronous chunk — runs the async version in a new event loop."""
        import asyncio
        return asyncio.run(self.async_chunk(text))

    async def async_chunk(self, text: str) -> list[str]:
        if not text.strip():
            return []

        sentences = _split_sentences(text)
        if not sentences:
            return []
        if len(sentences) == 1:
            return [sentences[0]] if sentences[0].strip() else []

        embed_fn = self._embed_fn or self._get_default_embed_fn()
        embeddings: list[list[float]] = await embed_fn.embed(sentences)

        similarities = [
            _cosine_similarity(embeddings[i], embeddings[i + 1])
            for i in range(len(embeddings) - 1)
        ]

        breakpoints = set(_find_breakpoints(similarities, self._breakpoint_percentile))

        groups: list[list[str]] = []
        current: list[str] = []
        for i, sent in enumerate(sentences):
            current.append(sent)
            if i in breakpoints and i < len(sentences) - 1:
                groups.append(current)
                current = []
        if current:
            groups.append(current)

        raw_chunks = [" ".join(g) for g in groups if g]
        merged = self._merge_small_chunks(raw_chunks)
        split = self._split_large_chunks(merged)
        return self._enforce_table_atomicity(split)

    def _get_default_embed_fn(self) -> object:
        from rag.knowledge.embedder import get_embed_fn
        return get_embed_fn()

    def _merge_small_chunks(self, chunks: list[str]) -> list[str]:
        """Merge chunks below min_chunk_tokens with their neighbour."""
        if not chunks:
            return []
        result: list[str] = [chunks[0]]
        for chunk in chunks[1:]:
            if _estimate_tokens(result[-1]) < self._min_chunk_tokens:
                result[-1] = result[-1] + " " + chunk
            else:
                result.append(chunk)
        return result

    def _split_large_chunks(self, chunks: list[str]) -> list[str]:
        """Split chunks above max_tokens at sentence boundaries."""
        result: list[str] = []
        for chunk in chunks:
            if _estimate_tokens(chunk) <= self._max_tokens:
                result.append(chunk)
                continue
            sentences = _SENTENCE_SPLIT_RE.split(chunk)
            current: list[str] = []
            size = 0
            for sent in sentences:
                s = _estimate_tokens(sent)
                if size + s > self._max_tokens and current:
                    result.append(" ".join(current))
                    current = []
                    size = 0
                current.append(sent)
                size += s
            if current:
                result.append(" ".join(current))
        return result

    def _enforce_table_atomicity(self, chunks: list[str]) -> list[str]:
        """Merge a table chunk with the preceding heading chunk if they were split apart."""
        if len(chunks) <= 1:
            return chunks
        result: list[str] = []
        i = 0
        while i < len(chunks):
            chunk = chunks[i]
            lines = chunk.strip().splitlines()
            if lines and lines[0].startswith("|") and result:
                prev_lines = result[-1].strip().splitlines()
                if prev_lines and prev_lines[-1].startswith("#"):
                    result[-1] = result[-1].rstrip() + "\n" + chunk
                    i += 1
                    continue
            result.append(chunk)
            i += 1
        return result
