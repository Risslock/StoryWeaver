"""Heading-based Markdown chunker with table-atomic units and configurable size cap."""

from __future__ import annotations

import os
import re

_DEFAULT_MAX_TOKENS = 800
_DEFAULT_OVERLAP_TOKENS = 50
_APPROX_CHARS_PER_TOKEN = 4

_HEADING_RE = re.compile(r"^#{1,3} .+", re.MULTILINE)
_TABLE_ROW_RE = re.compile(r"^\|.+\|", re.MULTILINE)


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // _APPROX_CHARS_PER_TOKEN)


def _is_table_block(text: str) -> bool:
    lines = [l for l in text.splitlines() if l.strip()]
    if len(lines) < 2:
        return False
    return all(_TABLE_ROW_RE.match(l.strip()) for l in lines[:2])


class MarkdownChunker:
    """Split Markdown into semantically coherent chunks.

    Rules:
    - Split at ## and ### heading boundaries.
    - Tables are atomic: a heading immediately before a table stays in the same chunk.
    - Max chunk size capped at max_tokens (approximate, 4 chars ≈ 1 token).
    - Adjacent chunks overlap by overlap_tokens characters at chunk boundaries.
    """

    def __init__(
        self,
        max_tokens: int | None = None,
        overlap_tokens: int | None = None,
    ) -> None:
        self._max_tokens = max_tokens or int(
            os.environ.get("KNOWLEDGE_MAX_CHUNK_TOKENS", str(_DEFAULT_MAX_TOKENS))
        )
        self._overlap_tokens = overlap_tokens or int(
            os.environ.get("KNOWLEDGE_CHUNK_OVERLAP_TOKENS", str(_DEFAULT_OVERLAP_TOKENS))
        )
        self._max_chars = self._max_tokens * _APPROX_CHARS_PER_TOKEN
        self._overlap_chars = self._overlap_tokens * _APPROX_CHARS_PER_TOKEN

    def chunk(self, text: str) -> list[str]:
        """Return a list of text chunks from the given Markdown string."""
        if not text.strip():
            return []

        segments = self._split_by_headings(text)
        raw_chunks: list[str] = []
        for seg in segments:
            raw_chunks.extend(self._enforce_max_size(seg))

        return self._apply_overlap(raw_chunks)

    def _split_by_headings(self, text: str) -> list[str]:
        """Split text at ## and ### boundaries, keeping headings with their content."""
        positions = [m.start() for m in _HEADING_RE.finditer(text)]
        if not positions:
            return [text] if text.strip() else []

        segments: list[str] = []
        if positions[0] > 0:
            pre = text[: positions[0]].strip()
            if pre:
                segments.append(pre)

        for i, start in enumerate(positions):
            end = positions[i + 1] if i + 1 < len(positions) else len(text)
            seg = text[start:end].strip()
            if seg:
                segments.append(seg)

        return segments

    def _enforce_max_size(self, segment: str) -> list[str]:
        """Split an oversized segment at blank-line boundaries, preserving tables atomically."""
        if _estimate_tokens(segment) <= self._max_tokens:
            return [segment]

        # Detect if the segment is a heading followed immediately by a table
        lines = segment.splitlines()
        if len(lines) >= 2 and lines[0].startswith("#") and _TABLE_ROW_RE.match(lines[1].strip()):
            return [segment]

        paragraphs = re.split(r"\n{2,}", segment)
        chunks: list[str] = []
        current_parts: list[str] = []
        current_size = 0

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            para_size = _estimate_tokens(para)

            if _is_table_block(para):
                if current_parts:
                    chunks.append("\n\n".join(current_parts))
                    current_parts = []
                    current_size = 0
                chunks.append(para)
                continue

            if current_size + para_size > self._max_tokens and current_parts:
                chunks.append("\n\n".join(current_parts))
                current_parts = []
                current_size = 0

            if para_size > self._max_tokens:
                chunks.extend(self._split_long_paragraph(para))
            else:
                current_parts.append(para)
                current_size += para_size

        if current_parts:
            chunks.append("\n\n".join(current_parts))

        return chunks if chunks else [segment]

    def _split_long_paragraph(self, text: str) -> list[str]:
        """Hard-split a very long paragraph into max-size pieces at sentence boundaries."""
        sentences = re.split(r"(?<=[.!?])\s+", text)
        chunks: list[str] = []
        current: list[str] = []
        size = 0
        for sent in sentences:
            s = _estimate_tokens(sent)
            if size + s > self._max_tokens and current:
                chunks.append(" ".join(current))
                current = []
                size = 0
            current.append(sent)
            size += s
        if current:
            chunks.append(" ".join(current))
        return chunks if chunks else [text[: self._max_chars]]

    def _apply_overlap(self, chunks: list[str]) -> list[str]:
        """Prepend a short tail from the previous chunk to each subsequent chunk."""
        if len(chunks) <= 1:
            return chunks
        result = [chunks[0]]
        for i in range(1, len(chunks)):
            tail = chunks[i - 1][-self._overlap_chars :]
            result.append(tail.strip() + "\n\n" + chunks[i])
        return result
