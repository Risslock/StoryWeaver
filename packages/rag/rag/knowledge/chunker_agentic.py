"""AgenticChunker: LLM proposition-boundary chunking strategy."""

from __future__ import annotations

import json
import logging
import os

from rag.knowledge.chunker import BaseChunker, HeadingChunker
from rag.knowledge.chunker import estimate_tokens as _estimate_tokens

_log = logging.getLogger(__name__)

_DEFAULT_MAX_TOKENS = 800
_DEFAULT_BATCH_SECTIONS = 1

_SYSTEM_PROMPT = "You are a document chunker for a tabletop RPG knowledge base."
_USER_PROMPT_TEMPLATE = (
    "Given the following section of a rulebook, identify where it should be split into "
    "self-contained propositions. Return ONLY a JSON object with a single key 'splits' "
    "containing a list of sentence indices (0-based) where new chunks should start. "
    'If the section should not be split, return {{"splits": []}}.\n\nSection:\n{section}'
)


def _is_table_line(line: str) -> bool:
    return line.strip().startswith("|")


def _is_heading_line(line: str) -> bool:
    return line.strip().startswith("#")


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
    """Split Markdown using LLM proposition-boundary detection per heading section.

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
    ) -> None:
        self._llm_provider = llm_provider
        self._max_tokens = max_tokens or int(
            os.environ.get("KNOWLEDGE_MAX_CHUNK_TOKENS", str(_DEFAULT_MAX_TOKENS))
        )
        self._batch_sections = batch_sections or int(
            os.environ.get("KNOWLEDGE_AGENTIC_BATCH_SECTIONS", str(_DEFAULT_BATCH_SECTIONS))
        )

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

        llm = self._llm_provider or self._get_default_llm()

        all_chunks: list[str] = []
        for idx, section in enumerate(sections):
            _log.debug(
                "AgenticChunker section %d/%d (%d chars)",
                idx + 1,
                len(sections),
                len(section),
            )
            section_chunks = await self._chunk_section(llm, section)
            all_chunks.extend(section_chunks)

        final = _enforce_table_atomicity(all_chunks)
        return [c for c in final if c.strip()]

    async def _chunk_section(self, llm: object, section: str) -> list[str]:
        from core.errors import ProviderUnavailableError

        sentences = _split_into_sentences(section)
        if len(sentences) <= 1:
            return [section] if section.strip() else []

        try:
            response: str = await llm.generate(  # type: ignore[union-attr]
                prompt=_USER_PROMPT_TEMPLATE.format(section=section),
                system=_SYSTEM_PROMPT,
            )
        except ProviderUnavailableError:
            raise
        except Exception as exc:
            _log.warning("LLM call failed for section (len=%d): %s", len(section), exc)
            return [section]

        try:
            data = json.loads(response)
            raw_splits = data.get("splits", [])
            if not isinstance(raw_splits, list):
                raise ValueError("splits is not a list")
            split_indices: list[int] = [int(v) for v in raw_splits]
        except (json.JSONDecodeError, ValueError, AttributeError, TypeError) as exc:
            _log.warning(
                "Failed to parse LLM split response (len=%d): %s — using full section",
                len(section),
                exc,
            )
            return [section]

        if not split_indices:
            return [section]

        chunks: list[str] = []
        split_set = set(split_indices)
        current: list[str] = []
        for i, sent in enumerate(sentences):
            if i in split_set and current:
                chunks.append(" ".join(current))
                current = []
            current.append(sent)
        if current:
            chunks.append(" ".join(current))

        expanded: list[str] = []
        for chunk in chunks:
            expanded.extend(_split_large(chunk, self._max_tokens))

        return expanded or [section]

    def _get_default_llm(self) -> object:
        from core.config import settings
        from llm.providers.ollama import OllamaProvider
        model = os.environ.get("KNOWLEDGE_ENRICH_MODEL", settings.knowledge_enrich_model)
        return OllamaProvider(model=model)
