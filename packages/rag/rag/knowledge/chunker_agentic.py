"""AgenticChunker: LLM proposition-boundary chunking strategy.

DEPRECATED(012): AgenticChunker is superseded by DoclingIngestor + HybridChunker for the active
PDF ingestion path (extraction_mode="docling", feature 012, spike PR #19).
AgenticChunker is retained for the legacy text and vision extraction paths.
"""

from __future__ import annotations

import logging
from typing import cast

from core.config import settings as _cfg

from pydantic import BaseModel, ValidationError

from rag.knowledge.chunker import BaseChunker, HeadingChunker
from rag.knowledge.chunker import estimate_tokens as _estimate_tokens

_log = logging.getLogger(__name__)

_DEFAULT_MAX_TOKENS = 800
_DEFAULT_BATCH_SECTIONS = 3
_DEFAULT_AGENTIC_SKIP_TOKENS = 400

_DEFAULT_SYSTEM_PROMPT = (
    "You are an expert document chunker for a tabletop RPG rulebook. "
    "Your goal is to produce self-contained, retrievable chunks where each chunk "
    "answers exactly one question a player or GM might ask about the game."
)

# Multi-section prompt: the LLM sees N sections at once and decides both where to split
# within sections and whether adjacent sections should be merged into a single chunk.
# Returning no boundary between section k and section k+1 merges them — critical for RPG
# rulebooks where two short adjacent sections often describe a single mechanic together.
_DEFAULT_BATCH_USER_PROMPT_TEMPLATE = (
    "Given the following sections from a tabletop RPG rulebook, identify where new chunks "
    "should begin. Each chunk must be independently useful to someone asking a specific "
    "question about the game.\n\n"
    "MERGE (do NOT split) when:\n"
    "- A heading section is followed by short sub-sections (< 5 sentences each) that "
    "elaborate on the same concept — keep parent and all children together\n"
    "- A race, discipline, or creature description (prose) is followed by its Game "
    "Information block (attribute values, movement rate, karma modifier, racial traits, "
    "abilities) — ALWAYS keep these in one chunk\n"
    "- A table or stat block appears without its own descriptive heading — merge it with "
    "the closest preceding heading or prose that labels it\n"
    "- Sequential sub-sections each describe one aspect of a shared parent topic (e.g. "
    "Dexterity, Strength, Toughness under Attributes) and each is too short to answer "
    "a question on its own\n\n"
    "SPLIT when:\n"
    "- A clearly distinct top-level topic begins (a different race, a different "
    "discipline, a different game system such as combat, magic, or character creation)\n"
    "- A section is a complete self-contained reference that answers one standalone "
    "question (a full gear table, a complete spell description, a full combat rule)\n\n"
    "Return ONLY a JSON object with key 'chunks' containing chunk start positions. "
    "Each position: {{\"section\": i, \"start_sentence\": j}} (both 0-based). "
    "Omit section=0/start_sentence=0. "
    'Return {{"chunks": []}} if no splits are needed.\n\n'
    "{sections_text}"
)


def _get_system_prompt() -> str:
    return _cfg.knowledge_agentic_system_prompt.strip() or _DEFAULT_SYSTEM_PROMPT


def _get_user_prompt_template() -> str:
    override = _cfg.knowledge_agentic_user_prompt_prefix.strip()
    if override:
        return override + "\n\n{sections_text}"
    return _DEFAULT_BATCH_USER_PROMPT_TEMPLATE


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
        _log.warning(
            "AgenticChunker is deprecated (feature 012). "
            "Use extraction_mode='docling' to chunk via HybridChunker instead."
        )
        self._llm_provider = llm_provider
        self._max_tokens = max_tokens or _cfg.knowledge_max_chunk_tokens
        self._batch_sections = batch_sections or _cfg.knowledge_agentic_batch_sections
        self._skip_tokens = skip_tokens or _cfg.knowledge_agentic_skip_tokens
        self._prose_threshold = prose_threshold or _cfg.knowledge_agentic_prose_threshold

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
        prompt = _get_user_prompt_template().format(sections_text=sections_text)

        try:
            result = cast(
                _ChunkBoundaryResponse,
                await llm.generate_structured(  # type: ignore[union-attr]
                    prompt=prompt,
                    response_type=_ChunkBoundaryResponse,
                    system=_get_system_prompt(),
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
        from llm.providers.ollama import OllamaProvider
        return OllamaProvider(model=_cfg.knowledge_enrich_model)
