"""AgenticChunker: LLM proposition-boundary chunking strategy."""

from __future__ import annotations

import logging
import os
from typing import cast

from pydantic import BaseModel, ValidationError

from rag.knowledge.chunker import BaseChunker, HeadingChunker
from rag.knowledge.chunker import estimate_tokens as _estimate_tokens

_log = logging.getLogger(__name__)

_DEFAULT_MAX_TOKENS = 800
_DEFAULT_BATCH_SECTIONS = 3
_DEFAULT_AGENTIC_SKIP_TOKENS = 400

_SYSTEM_PROMPT = "You are a document chunker for a tabletop RPG knowledge base."

# Multi-section prompt: the LLM sees N sections at once and decides both where to split
# within sections and whether adjacent sections should be merged into a single chunk.
# Returning no boundary between section k and section k+1 merges them — critical for RPG
# rulebooks where two short adjacent sections often describe a single mechanic together.
_BATCH_USER_PROMPT_TEMPLATE = (
    "Given the following sections from a tabletop RPG rulebook, identify where new chunks "
    "should begin. Sections that together describe a single mechanic or rule should be "
    "merged — do not place a boundary between them. Return ONLY a JSON object with a "
    "single key 'chunks' containing a list of chunk start positions. Each position is an "
    "object with 'section' (0-based section index) and 'start_sentence' (0-based sentence "
    "index within that section). Do not include position section=0 / start_sentence=0 — "
    "the first chunk always starts there implicitly. If a section continues the prior "
    "topic, omit its start position so it merges with the previous chunk. "
    'If no splits are needed return {{"chunks": []}}.\n\n'
    "{sections_text}"
)


class _ChunkBoundary(BaseModel):
    section: int
    start_sentence: int


class _ChunkBoundaryResponse(BaseModel):
    chunks: list[_ChunkBoundary]


def _is_table_line(line: str) -> bool:
    return line.strip().startswith("|")


def _is_heading_line(line: str) -> bool:
    return line.strip().startswith("#")


def _prose_ratio(section: str) -> float:
    """Return fraction of content lines (non-heading, non-table) with ≥8 tokens."""
    prose = 0
    total = 0
    for line in section.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("|"):
            continue
        total += 1
        if len(stripped.split()) >= 8:
            prose += 1
    return prose / total if total > 0 else 0.0


def _split_into_sentences(text: str) -> list[str]:
    """Split text into sentence units for proposition indexing."""
    import re
    raw = re.split(r"(?<=[.!?])\s+", text)
    return [s.strip() for s in raw if s.strip()]


def _enforce_table_atomicity(chunks: list[str]) -> list[str]:
    """Merge a table chunk with the preceding heading chunk if they were split apart."""
    if len(chunks) <= 1:
        return chunks
    result: list[str] = []
    for chunk in chunks:
        lines = chunk.strip().splitlines()
        if lines and _is_table_line(lines[0]) and result:
            prev_lines = result[-1].strip().splitlines()
            if prev_lines and _is_heading_line(prev_lines[-1]):
                result[-1] = result[-1].rstrip() + "\n" + chunk
                continue
        result.append(chunk)
    return result


def _split_large(chunk: str, max_tokens: int) -> list[str]:
    """Split an oversized chunk at sentence boundaries."""
    import re
    if _estimate_tokens(chunk) <= max_tokens:
        return [chunk]
    sentences = re.split(r"(?<=[.!?])\s+", chunk)
    result: list[str] = []
    current: list[str] = []
    size = 0
    for sent in sentences:
        s = _estimate_tokens(sent)
        if size + s > max_tokens and current:
            result.append(" ".join(current))
            current = []
            size = 0
        current.append(sent)
        size += s
    if current:
        result.append(" ".join(current))
    return result or [chunk]


class AgenticChunker(BaseChunker):
    """Split Markdown using LLM proposition-boundary detection, batching N sections per call.

    KNOWLEDGE_AGENTIC_BATCH_SECTIONS controls how many consecutive heading sections are
    packed into a single LLM call. The LLM may merge adjacent sections into one chunk by
    omitting a boundary between them — essential for RPG rulebooks where multi-section
    sequences describe a single mechanic.

    chunk() raises NotImplementedError — always call async_chunk() instead.
    ProviderUnavailableError propagates on LLM failure.
    """

    @property
    def strategy_name(self) -> str:
        return "agentic"

    def __init__(
        self,
        llm_provider: object = None,
        max_tokens: int | None = None,
        batch_sections: int | None = None,
        skip_tokens: int | None = None,
        prose_threshold: float | None = None,
    ) -> None:
        self._llm_provider = llm_provider
        self._max_tokens = max_tokens or int(
            os.environ.get("KNOWLEDGE_MAX_CHUNK_TOKENS", str(_DEFAULT_MAX_TOKENS))
        )
        self._batch_sections = batch_sections or int(
            os.environ.get("KNOWLEDGE_AGENTIC_BATCH_SECTIONS", str(_DEFAULT_BATCH_SECTIONS))
        )
        self._skip_tokens = skip_tokens or int(
            os.environ.get("KNOWLEDGE_AGENTIC_SKIP_TOKENS", str(_DEFAULT_AGENTIC_SKIP_TOKENS))
        )
        self._prose_threshold = prose_threshold or float(
            os.environ.get("KNOWLEDGE_AGENTIC_PROSE_THRESHOLD", "0.3")
        )

    def _merge_appendage_sections(self, sections: list[str]) -> list[str]:
        result: list[str] = []
        for section in sections:
            ratio = _prose_ratio(section)
            is_appendage = ratio < self._prose_threshold
            if is_appendage and result:
                merged = result[-1] + "\n\n" + section
                if _estimate_tokens(merged) <= self._max_tokens * 4:
                    first_line = section.splitlines()[0][:80] if section.strip() else ""
                    _log.info(
                        "[agentic-chunker] Merged appendage section into preceding (prose ratio: %.0f%%, first: '%s')",
                        ratio * 100,
                        first_line,
                    )
                    result[-1] = merged
                    continue
                else:
                    _log.info("[agentic-chunker] Skipping merge — size cap would be exceeded")
            result.append(section)
        return result

    def chunk(self, text: str) -> list[str]:
        raise NotImplementedError(
            "AgenticChunker requires async_chunk() — "
            "call await chunker.async_chunk(text) instead."
        )

    async def async_chunk(self, text: str) -> list[str]:
        if not text.strip():
            return []

        heading_chunker = HeadingChunker(max_tokens=self._max_tokens * 4)
        sections = heading_chunker.split_by_headings(text)
        if not sections:
            sections = [text]
        sections = self._merge_appendage_sections(sections)

        llm = self._llm_provider or self._get_default_llm()

        all_chunks: list[str] = []
        batch_size = self._batch_sections
        for batch_start in range(0, len(sections), batch_size):
            batch = sections[batch_start : batch_start + batch_size]
            # Fast-path: sections already below KNOWLEDGE_AGENTIC_SKIP_TOKENS are
            # single cohesive units — splitting them further creates noise, not precision.
            # Sections above this threshold still go to the LLM so proposition
            # boundaries can be found within them.
            if all(_estimate_tokens(sec) <= self._skip_tokens for sec in batch):
                _log.info(
                    "[agentic-chunker] Skipping LLM for sections %d-%d of %d (all within token limit)",
                    batch_start + 1,
                    batch_start + len(batch),
                    len(sections),
                )
                all_chunks.extend(sec for sec in batch if sec.strip())
                continue
            _log.info(
                "[agentic-chunker] Processing sections %d-%d of %d …",
                batch_start + 1,
                batch_start + len(batch),
                len(sections),
            )
            batch_chunks = await self._chunk_batch(llm, batch)
            all_chunks.extend(batch_chunks)

        final = _enforce_table_atomicity(all_chunks)
        return [c for c in final if c.strip()]

    async def _chunk_batch(self, llm: object, sections: list[str]) -> list[str]:
        """Send N sections to the LLM in one call and reconstruct chunks from 2D boundaries.

        The LLM returns {"chunks": [{"section": i, "start_sentence": j}, ...]} where each
        entry marks the start of a new chunk. Adjacent sections with no boundary between
        them are concatenated into a single chunk (cross-section merge). On any parse
        failure, one chunk per section is returned as a safe fallback.
        """
        from core.errors import ProviderUnavailableError

        if not sections:
            return []

        sections_sentences: list[list[str]] = [
            _split_into_sentences(sec) or [sec] for sec in sections
        ]
        total_sentences = sum(len(s) for s in sections_sentences)
        if total_sentences <= 1:
            return [s for s in sections if s.strip()]

        sections_text = "\n\n".join(
            f"[Section {i}]\n{sec}" for i, sec in enumerate(sections)
        )
        prompt = _BATCH_USER_PROMPT_TEMPLATE.format(sections_text=sections_text)

        try:
            result = cast(
                _ChunkBoundaryResponse,
                await llm.generate_structured(  # type: ignore[union-attr]
                    prompt=prompt,
                    response_type=_ChunkBoundaryResponse,
                    system=_SYSTEM_PROMPT,
                ),
            )
        except ProviderUnavailableError:
            raise
        except ValidationError as exc:
            _log.debug(
                "Structured response did not match schema (sections=%d): %s — one chunk per section",
                len(sections),
                exc,
            )
            return list(sections)

        boundary_set: set[tuple[int, int]] = {
            (e.section, e.start_sentence) for e in result.chunks
        }

        current: list[str] = []
        chunks: list[str] = []
        for sec_idx, sentences in enumerate(sections_sentences):
            for sent_idx, sent in enumerate(sentences):
                if (sec_idx, sent_idx) in boundary_set and current:
                    chunks.append(" ".join(current))
                    current = []
                current.append(sent)
        if current:
            chunks.append(" ".join(current))

        expanded: list[str] = []
        for chunk in chunks:
            expanded.extend(_split_large(chunk, self._max_tokens))

        return expanded or list(sections)

    def _get_default_llm(self) -> object:
        from core.config import settings
        from llm.providers.ollama import OllamaProvider
        model = os.environ.get("KNOWLEDGE_ENRICH_MODEL", settings.knowledge_enrich_model)
        return OllamaProvider(model=model)
