"""LLM-powered chunk enrichment and query expansion for the knowledge pipeline."""

from __future__ import annotations

from core.errors import ProviderUnavailableError
from llm.interface import LLMProvider
from pydantic import ValidationError

from rag.knowledge.interface import BatchEnrichment, ChunkEnrichment, QueryExpansion, RankOrder

_ENRICH_SYSTEM = (
    "You are a metadata extraction assistant for a tabletop RPG knowledge base. "
    "Always respond with a single valid JSON object and nothing else."
)

_EXPAND_SYSTEM = (
    "You are a query expansion assistant for a tabletop RPG knowledge base. "
    "Always respond with a single valid JSON object and nothing else."
)

# ── Single-chunk enrichment ────────────────────────────────────────────────────

_ENRICH_PROMPT = """\
Analyse the following text chunk from a tabletop RPG rulebook or lore document.
Return a JSON object with exactly these keys:
- "headline": a short title for this chunk (≤80 characters)
- "summary": a 1–2 sentence plain-language summary
- "topic": a topic label using slash notation (e.g. "combat/initiative", "lore/blood-wood")
- "access_level": either "gm_only" or "player_visible"

Classify as "gm_only" only if the text clearly contains GM secrets, hidden plot information,
or spoilers. Default to "player_visible".

Chunk text:
---
{chunk_text}
---

Respond with ONLY the JSON object."""

_ENRICH_RETRY_PROMPT = """\
Your previous response was not valid JSON or did not match the required schema.
Return ONLY a JSON object with these keys: "headline" (str, ≤80 chars),
"summary" (str, 1–2 sentences), "topic" (str), "access_level" ("gm_only" or "player_visible").

Chunk text (first 500 chars):
---
{chunk_text_short}
---"""

# ── Batch enrichment (all chunks in one call) ─────────────────────────────────

_BATCH_ENRICH_PROMPT = """\
Analyse the following {n} text chunks from a tabletop RPG rulebook or lore document.
Return a JSON object with a single key "chunks" — a list of exactly {n} enrichment objects,
one per chunk in the same order. Each object must have:
- "headline": a short title (≤80 characters)
- "summary": a 1–2 sentence plain-language summary
- "topic": a topic label using slash notation (e.g. "combat/initiative", "lore/blood-wood")
- "access_level": "gm_only" or "player_visible"

Classify as "gm_only" only if the text clearly contains GM secrets or plot spoilers.
Default to "player_visible".

Chunks:
{chunks_block}

Respond with ONLY the JSON object."""

_BATCH_RETRY_PROMPT = """\
Your previous response was not valid JSON or did not match the required schema.
Return ONLY a JSON object: {{"chunks": [list of {n} objects, each with keys headline, summary, topic, access_level]}}.
The list must have exactly {n} items — one per chunk below.

Chunks (first 200 chars each):
{short_block}"""

# ── Re-ranking ────────────────────────────────────────────────────────────────

_RERANK_SYSTEM = (
    "You are a relevance ranking assistant for a tabletop RPG knowledge base. "
    "Always respond with a single valid JSON object and nothing else."
)

_RERANK_PROMPT = """\
Given the question and {n} candidate text chunks below, return a JSON object with one key
"order" — a list of the chunk numbers (1-based) sorted from most to least relevant for
answering the question. Include ALL {n} numbers exactly once.

Question: {question}

Chunks:
{chunks_block}

Respond with ONLY: {{"order": [...]}}"""

_RERANK_RETRY_PROMPT = """\
Your previous response was not valid JSON or did not match the schema.
Return ONLY: {{"order": [list of all {n} integers from 1 to {n}, ordered most to least relevant]}}

Question: {question}"""

# ── Query expansion ────────────────────────────────────────────────────────────

_EXPAND_PROMPT = """\
Generate exactly 3 alternative phrasings of the following question to improve retrieval
from a tabletop RPG knowledge base. The alternatives should vary in vocabulary and phrasing
while preserving the same intent.

Return a JSON object with exactly one key: "alternatives" — a list of 3 strings.

Question: {question}

Respond with ONLY the JSON object."""

_EXPAND_RETRY_PROMPT = """\
Your previous response was not valid JSON or did not match the required schema.
Return ONLY a JSON object with one key: "alternatives" — a list of exactly 3 strings.

Question: {question}"""

_CONTEXTUAL_SUMMARY_SYSTEM = (
    "You are a retrieval assistant. Your task is to write a one or two sentence description "
    "that situates a text passage within its source document, for the purpose of improving "
    "search retrieval. Be factual and concise. Do not repeat the passage text verbatim."
)

_CONTEXTUAL_SUMMARY_PROMPT = """\
Document: {doc_title}
Section: {breadcrumb}

Passage:
{chunk_text}

Write one or two sentences situating this passage within the document for search retrieval."""

_ENRICH_FALLBACK = ChunkEnrichment(
    headline="Untitled section",
    summary="",
    topic="general",
    access_level="player_visible",
)

# Default chunks per LLM call — kept small for local memory-constrained models.
# Override with KNOWLEDGE_ENRICH_BATCH_SIZE env var.
ENRICH_BATCH_SIZE = 5
_BATCH_SIZE = ENRICH_BATCH_SIZE  # kept for internal use


class ChunkEnricher:
    """Enriches text chunks and expands queries using an LLM."""

    def __init__(self, llm: LLMProvider) -> None:
        self._llm = llm

    # ── Public API ─────────────────────────────────────────────────────────────

    async def enrich_chunks(self, texts: list[str]) -> list[ChunkEnrichment]:
        """Enrich all chunks in a single LLM call (batched). Falls back per-chunk on failure.

        This mirrors the reference implementation's approach: one LLM call returns
        structured metadata for every chunk, saving N-1 round-trips for a document.
        """
        if not texts:
            return []
        results: list[ChunkEnrichment] = []
        for batch_start in range(0, len(texts), _BATCH_SIZE):
            batch = texts[batch_start : batch_start + _BATCH_SIZE]
            batch_results = await self.enrich_batch(batch)
            results.extend(batch_results)
        return results

    async def enrich_chunk(self, chunk_text: str) -> ChunkEnrichment:
        """Enrich a single chunk. Use enrich_chunks() for whole-document batches."""
        prompt = _ENRICH_PROMPT.format(chunk_text=chunk_text)
        raw = await self._llm.generate(prompt, system=_ENRICH_SYSTEM)
        try:
            return ChunkEnrichment.model_validate_json(_extract_json(raw))
        except (ValidationError, ValueError):
            pass
        short = chunk_text[:500]
        retry_prompt = _ENRICH_RETRY_PROMPT.format(chunk_text_short=short)
        try:
            raw2 = await self._llm.generate(retry_prompt, system=_ENRICH_SYSTEM)
            return ChunkEnrichment.model_validate_json(_extract_json(raw2))
        except (ValidationError, ValueError, ProviderUnavailableError):
            return _ENRICH_FALLBACK.model_copy()

    async def rerank(self, question: str, chunks: list[str]) -> list[int]:
        """Return 0-based indices ordered most → least relevant. Falls back to identity order."""
        n = len(chunks)
        if n <= 1:
            return list(range(n))
        chunks_block = "\n\n".join(f"[{i + 1}] {c[:300]}" for i, c in enumerate(chunks))
        prompt = _RERANK_PROMPT.format(n=n, question=question, chunks_block=chunks_block)
        raw = await self._llm.generate(prompt, system=_RERANK_SYSTEM)
        try:
            result = RankOrder.model_validate_json(_extract_json(raw))
            if sorted(result.order) == list(range(1, n + 1)):
                return [i - 1 for i in result.order]
        except (ValidationError, ValueError):
            pass
        retry_prompt = _RERANK_RETRY_PROMPT.format(n=n, question=question)
        try:
            raw2 = await self._llm.generate(retry_prompt, system=_RERANK_SYSTEM)
            result = RankOrder.model_validate_json(_extract_json(raw2))
            if sorted(result.order) == list(range(1, n + 1)):
                return [i - 1 for i in result.order]
        except (ValidationError, ValueError, ProviderUnavailableError):
            pass
        return list(range(n))

    async def expand_query(self, question: str) -> list[str]:
        """Return 3 alternative phrasings of the question, falling back to empty list."""
        prompt = _EXPAND_PROMPT.format(question=question)
        raw = await self._llm.generate(prompt, system=_EXPAND_SYSTEM)
        try:
            result = QueryExpansion.model_validate_json(_extract_json(raw))
            return result.alternatives[:3]
        except (ValidationError, ValueError):
            pass
        retry_prompt = _EXPAND_RETRY_PROMPT.format(question=question)
        try:
            raw2 = await self._llm.generate(retry_prompt, system=_EXPAND_SYSTEM)
            result = QueryExpansion.model_validate_json(_extract_json(raw2))
            return result.alternatives[:3]
        except (ValidationError, ValueError, ProviderUnavailableError):
            return []

    async def generate_contextual_summaries(
        self,
        texts: list[str],
        breadcrumbs: list[str],
        doc_title: str,
    ) -> list[str]:
        """Return a 1-2 sentence retrieval context per chunk; falls back to "" on any failure."""
        import logging
        _log = logging.getLogger(__name__)
        results: list[str] = []
        for text, breadcrumb in zip(texts, breadcrumbs, strict=False):
            prompt = _CONTEXTUAL_SUMMARY_PROMPT.format(
                doc_title=doc_title,
                breadcrumb=breadcrumb or doc_title,
                chunk_text=text,
            )
            try:
                summary = await self._llm.generate(prompt, system=_CONTEXTUAL_SUMMARY_SYSTEM)
                _log.info(
                    "contextual_summary=ok breadcrumb=%r doc=%r",
                    breadcrumb or doc_title,
                    doc_title,
                )
                results.append(summary.strip())
            except Exception as exc:
                _log.warning(
                    "contextual_summary=fail breadcrumb=%r doc=%r error=%s",
                    breadcrumb or doc_title,
                    doc_title,
                    exc,
                )
                results.append("")
        return results

    # ── Private helpers ────────────────────────────────────────────────────────

    async def enrich_batch(self, texts: list[str]) -> list[ChunkEnrichment]:
        n = len(texts)
        chunks_block = "\n\n".join(
            f"=== CHUNK {i + 1} ===\n{t}" for i, t in enumerate(texts)
        )
        prompt = _BATCH_ENRICH_PROMPT.format(n=n, chunks_block=chunks_block)
        raw = await self._llm.generate(prompt, system=_ENRICH_SYSTEM)
        try:
            batch = BatchEnrichment.model_validate_json(_extract_json(raw))
            if len(batch.chunks) == n:
                return batch.chunks
        except (ValidationError, ValueError):
            pass

        # Retry with short previews
        short_block = "\n\n".join(
            f"=== CHUNK {i + 1} ===\n{t[:200]}" for i, t in enumerate(texts)
        )
        retry_prompt = _BATCH_RETRY_PROMPT.format(n=n, short_block=short_block)
        try:
            raw2 = await self._llm.generate(retry_prompt, system=_ENRICH_SYSTEM)
            batch = BatchEnrichment.model_validate_json(_extract_json(raw2))
            if len(batch.chunks) == n:
                return batch.chunks
        except (ValidationError, ValueError, ProviderUnavailableError):
            pass

        # Fall back to one-by-one enrichment
        return [await self.enrich_chunk(t) for t in texts]


def _extract_json(text: str) -> str:
    """Extract the first JSON object from LLM output, stripping markdown fences."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        inner: list[str] = []
        in_block = False
        for line in lines:
            if line.startswith("```") and not in_block:
                in_block = True
                continue
            if line.startswith("```") and in_block:
                break
            if in_block:
                inner.append(line)
        text = "\n".join(inner).strip()
    start = text.find("{")
    end = text.rfind("}") + 1
    if start != -1 and end > start:
        return text[start:end]
    return text