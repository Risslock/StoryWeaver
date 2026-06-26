"""BreadcrumbExtractor: deterministic ATX-heading scan to produce per-chunk breadcrumb paths."""

from __future__ import annotations

import re

_ATX_HEADING = re.compile(r"^(#{1,3})\s+(.*)")


class BreadcrumbExtractor:
    """Produce a parallel list of breadcrumb strings for a list of text chunks.

    The extractor scans the full cleaned Markdown text for ATX headings (# / ## / ###),
    maintains a depth-keyed heading stack, and assigns each chunk the last heading whose
    character offset is ≤ the chunk's position in the text.

    Falls back to doc_name alone when:
    - No heading precedes the chunk's position (preamble content).
    - The chunk's first 80 characters cannot be located in the full text (agentic rewrites).
    """

    def extract(self, md_text: str, chunks: list[str], doc_name: str) -> list[str]:
        """Return a list of breadcrumb strings, one per chunk."""
        heading_timeline: list[tuple[int, str]] = self._build_heading_timeline(md_text, doc_name)
        return [self._breadcrumb_for_chunk(chunk, md_text, heading_timeline, doc_name) for chunk in chunks]

    # ── private ──────────────────────────────────────────────────────────────

    def _build_heading_timeline(self, md_text: str, doc_name: str) -> list[tuple[int, str]]:
        """Return a list of (char_offset, breadcrumb_string) pairs in document order."""
        timeline: list[tuple[int, str]] = []
        stack: dict[int, str] = {}  # depth → heading text

        offset = 0
        for line in md_text.splitlines(keepends=True):
            m = _ATX_HEADING.match(line.rstrip("\n").rstrip("\r"))
            if m:
                depth = len(m.group(1))
                title = m.group(2).strip()
                # Pop entries at same or deeper depth before pushing the new heading
                for d in list(stack.keys()):
                    if d >= depth:
                        del stack[d]
                stack[depth] = title
                crumb = self._format_breadcrumb(doc_name, stack)
                timeline.append((offset, crumb))
            offset += len(line)

        return timeline

    def _format_breadcrumb(self, doc_name: str, stack: dict[int, str]) -> str:
        parts = [doc_name]
        for depth in sorted(stack):
            parts.append(stack[depth])
        return " > ".join(parts)

    def _breadcrumb_for_chunk(
        self,
        chunk: str,
        md_text: str,
        timeline: list[tuple[int, str]],
        doc_name: str,
    ) -> str:
        if not timeline:
            return doc_name

        probe = chunk[:80]
        pos = md_text.find(probe)

        if pos == -1:
            # Chunk not locatable (agentic rewrite); use last heading or doc_name
            return timeline[-1][1] if timeline else doc_name

        # Select the last heading whose offset is ≤ chunk position
        breadcrumb = doc_name
        for offset, crumb in timeline:
            if offset <= pos:
                breadcrumb = crumb
            else:
                break

        return breadcrumb
