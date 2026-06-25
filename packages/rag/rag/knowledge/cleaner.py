"""Corpus pre-processing and cleaning — sits between PDF extraction and chunking."""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Literal

__all__ = [
    "SourceType",
    "PageText",
    "CleaningReport",
    "CleanedDocument",
    "CleaningRuleProfile",
    "CorpusCleaner",
]

_log = logging.getLogger(__name__)

SourceType = Literal["rulebook", "supplement", "novel", "handwritten"]

_VALID_SOURCE_TYPES: frozenset[str] = frozenset({"rulebook", "supplement", "novel", "handwritten"})

# Earthdawn 4E stat block keywords — ≥3 of these in consecutive short lines triggers reconstruction.
_STAT_KEYWORDS: frozenset[str] = frozenset({
    "DEX", "STR", "TOU", "PER", "WIL", "CHA",
    "Initiative", "Wounds", "Unconsciousness", "Death",
    "Armor", "Mystic", "Physical", "Step",
    "Action", "Attacks", "Damage",
})

# TOC line: text followed by dot-leaders/spaces/tab then a page number.
_TOC_LINE_RE = re.compile(r"^.{1,100}(?:[.\s]{2,}|\t)\s*\d+\s*$")

# TOC section heading.
_TOC_HEADING_RE = re.compile(
    r"^#{1,6}\s*(?:Table of Contents|Contents|TOC)\s*$",
    re.IGNORECASE,
)

# De-hyphenation: join when alphabetic char surrounds the hyphen-newline.
# Matches both single-\n (within page) and double-\n\n (page-join boundary).
_DEHYPHEN_RE = re.compile(r"([a-zA-Z])-\n{1,2}([a-zA-Z])")

# Front matter patterns matched against page text.
_FRONTMATTER_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"©|Copyright\b|All rights reserved", re.IGNORECASE), "copyright block"),
    (re.compile(r"Dedicated to\b|^For\s+\w|In memory of\b", re.IGNORECASE | re.MULTILINE), "dedication block"),
    (re.compile(r"\bISBN\b|Printed in\b", re.IGNORECASE), "publisher/ISBN block"),
]


@dataclass
class PageText:
    """Per-page Markdown text produced by pymupdf4llm page_chunks=True."""
    page_num: int   # 0-indexed
    text: str


@dataclass
class CleaningReport:
    """Summary of transformations applied during one ingestion run."""
    hyphens_rejoined: int = 0
    toc_lines_removed: int = 0
    frontmatter_pages_removed: int = 0
    stat_blocks_reconstructed: int = 0
    multicolumn_pages_reconstructed: int = 0
    warnings: list[str] = field(default_factory=list)


@dataclass
class CleanedDocument:
    """Output of CorpusCleaner — ready for the chunker."""
    text: str
    source_type: SourceType
    report: CleaningReport


@dataclass
class CleaningRuleProfile:
    """Active cleaning rules for a given source type."""
    multicolumn_reconstruction: bool
    stat_block_reconstruction: bool
    dehyphenation: bool
    toc_stripping: bool
    frontmatter_stripping: bool


_PROFILES: dict[str, CleaningRuleProfile] = {
    "rulebook": CleaningRuleProfile(
        multicolumn_reconstruction=True,
        stat_block_reconstruction=True,
        dehyphenation=True,
        toc_stripping=True,
        frontmatter_stripping=True,
    ),
    "supplement": CleaningRuleProfile(
        multicolumn_reconstruction=True,
        stat_block_reconstruction=True,
        dehyphenation=True,
        toc_stripping=True,
        frontmatter_stripping=True,
    ),
    "novel": CleaningRuleProfile(
        multicolumn_reconstruction=False,
        stat_block_reconstruction=False,
        dehyphenation=True,
        toc_stripping=False,
        frontmatter_stripping=True,
    ),
    "handwritten": CleaningRuleProfile(
        multicolumn_reconstruction=False,
        stat_block_reconstruction=False,
        dehyphenation=True,
        toc_stripping=False,
        frontmatter_stripping=False,
    ),
}


class CorpusCleaner:
    """Pure text → text transformer; stateless and thread-safe."""

    def clean_pages(
        self,
        pages: list[PageText],
        source_type: SourceType,
        *,
        doc_name: str = "",
        frontmatter_threshold: int | None = None,
    ) -> CleanedDocument:
        """PDF ingestion path: page-aware cleaning then join.

        Args:
            pages: Per-page Markdown from pymupdf4llm page_chunks=True.
            source_type: Document category governing which rules are active.
            doc_name: Used in log messages for traceability.
            frontmatter_threshold: Pages with index < this are examined for front matter.
                Defaults to KNOWLEDGE_CLEANING_FRONTMATTER_PAGES env var (default 10).
        """
        if not pages:
            raise ValueError("clean_pages: pages must not be empty")
        if source_type not in _VALID_SOURCE_TYPES:
            raise ValueError(
                f"clean_pages: invalid source_type {source_type!r}; "
                f"must be one of {sorted(_VALID_SOURCE_TYPES)}"
            )

        if frontmatter_threshold is None:
            frontmatter_threshold = int(
                os.environ.get("KNOWLEDGE_CLEANING_FRONTMATTER_PAGES", "10")
            )

        profile = _PROFILES[source_type]
        warnings: list[str] = []

        # ── Page-level rules (applied before join) ────────────────────────
        if profile.frontmatter_stripping:
            pages, fm_removed = self._strip_frontmatter(pages, doc_name, frontmatter_threshold, warnings)
        else:
            fm_removed = 0

        if profile.toc_stripping:
            toc_scope = frontmatter_threshold + 10
            pages, toc_removed = self._strip_toc(pages, doc_name, toc_scope, warnings)
        else:
            toc_removed = 0

        # ── Join remaining pages ──────────────────────────────────────────
        joined = "\n\n".join(p.text for p in pages)

        # ── String-level rules (applied on joined text) ───────────────────
        if profile.dehyphenation:
            joined, hyphens = self._dehyphenate(joined, doc_name, warnings)
        else:
            hyphens = 0

        if profile.stat_block_reconstruction:
            joined, stat_count = self._reconstruct_stat_blocks(joined, doc_name, warnings)
            self._preserve_creature_blocks(joined)
        else:
            stat_count = 0

        report = CleaningReport(
            hyphens_rejoined=hyphens,
            toc_lines_removed=toc_removed,
            frontmatter_pages_removed=fm_removed,
            stat_blocks_reconstructed=stat_count,
            multicolumn_pages_reconstructed=0,  # set by ingestor before calling cleaner
            warnings=warnings,
        )
        return CleanedDocument(text=joined, source_type=source_type, report=report)  # type: ignore[arg-type]

    def clean_text(
        self,
        text: str,
        source_type: SourceType,
        *,
        doc_name: str = "",
        frontmatter_threshold: int | None = None,
    ) -> CleanedDocument:
        """Markdown ingestion path and unit-test entry point.

        Wraps text in a single PageText(page_num=0) and delegates to clean_pages.
        Empty text returns a CleanedDocument with empty text (does not raise).
        """
        if not text:
            return CleanedDocument(
                text="",
                source_type=source_type,  # type: ignore[arg-type]
                report=CleaningReport(),
            )
        return self.clean_pages(
            [PageText(page_num=0, text=text)],
            source_type,
            doc_name=doc_name,
            frontmatter_threshold=frontmatter_threshold,
        )

    # ── Private rule implementations ──────────────────────────────────────────

    def _strip_frontmatter(
        self,
        pages: list[PageText],
        doc_name: str,
        threshold: int,
        warnings: list[str],
    ) -> tuple[list[PageText], int]:
        """Remove entire page chunks recognised as front matter within the threshold."""
        kept: list[PageText] = []
        removed = 0
        for page in pages:
            if page.page_num >= threshold:
                kept.append(page)
                continue

            reason = self._frontmatter_reason(page.text)
            if reason:
                msg = (
                    f"[corpus-cleaner] Removed front matter page {page.page_num} "
                    f"({reason}) in '{doc_name}'"
                )
                _log.warning(msg)
                warnings.append(msg)
                removed += 1
            else:
                kept.append(page)
        return kept, removed

    def _frontmatter_reason(self, text: str) -> str | None:
        """Return a short reason string if text looks like front matter, else None."""
        for pat, label in _FRONTMATTER_PATTERNS:
            if pat.search(text):
                return label

        # Title-only page: every non-empty line is a Markdown heading (starts with #).
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if lines and all(ln.startswith("#") for ln in lines):
            return "title-only page"

        return None

    def _strip_toc(
        self,
        pages: list[PageText],
        doc_name: str,
        scope_pages: int,
        warnings: list[str],
    ) -> tuple[list[PageText], int]:
        """Strip TOC blocks from pages within scope_pages."""
        result: list[PageText] = []
        total_removed = 0
        for page in pages:
            if page.page_num >= scope_pages:
                result.append(page)
                continue
            cleaned_text, removed = self._strip_toc_from_text(page.text, doc_name, warnings)
            total_removed += removed
            result.append(PageText(page_num=page.page_num, text=cleaned_text))
        return result, total_removed

    def _strip_toc_from_text(
        self,
        text: str,
        doc_name: str,
        warnings: list[str],
    ) -> tuple[str, int]:
        """Remove TOC blocks (≥5 consecutive dot-leader lines) from a single page's text."""
        lines = text.splitlines()
        out: list[str] = []
        i = 0
        total_removed = 0
        while i < len(lines):
            j = i
            while j < len(lines) and _TOC_LINE_RE.match(lines[j]):
                j += 1
            run_len = j - i
            if run_len >= 5:
                # Strip a preceding TOC heading if present.
                if out and _TOC_HEADING_RE.match(out[-1]):
                    out.pop()
                    total_removed += 1
                total_removed += run_len
                msg = (
                    f"[corpus-cleaner] Stripped TOC section ({run_len} lines) in '{doc_name}'"
                )
                _log.warning(msg)
                warnings.append(msg)
                i = j
            else:
                out.append(lines[i])
                i += 1
        return "\n".join(out), total_removed

    def _dehyphenate(
        self,
        text: str,
        doc_name: str,
        warnings: list[str],
    ) -> tuple[str, int]:
        """Rejoin line-break hyphenation: word-\\ncontinuation → wordcontinuation."""
        matches = _DEHYPHEN_RE.findall(text)
        count = len(matches)
        if count > 0:
            text = _DEHYPHEN_RE.sub(r"\1\2", text)
            msg = (
                f"[corpus-cleaner] Rejoined {count} hyphenated line-breaks in '{doc_name}'"
            )
            _log.warning(msg)
            warnings.append(msg)
        return text, count

    def _reconstruct_stat_blocks(
        self,
        text: str,
        doc_name: str,
        warnings: list[str],
    ) -> tuple[str, int]:
        """Detect Earthdawn 4E stat blocks (≥3 consecutive keyword lines) and normalise."""
        lines = text.splitlines()
        out: list[str] = []
        i = 0
        blocks_found = 0

        while i < len(lines):
            line = lines[i]
            if len(line) <= 80 and self._has_stat_keyword(line):
                # Collect contiguous short keyword lines.
                block_lines = [line]
                j = i + 1
                while j < len(lines) and len(lines[j]) <= 80 and self._has_stat_keyword(lines[j]):
                    block_lines.append(lines[j])
                    j += 1
                if len(block_lines) >= 3:
                    table_rows = ["| Attribute | Value |", "| --- | --- |"]
                    for bl in block_lines:
                        m = re.match(r"^([^:]+):\s*(.+)$", bl.strip())
                        if m:
                            table_rows.append(f"| {m.group(1).strip()} | {m.group(2).strip()} |")
                        else:
                            table_rows.append(f"| {bl.strip()} | |")
                    out.extend(table_rows)
                    blocks_found += 1
                    msg = (
                        f"[corpus-cleaner] Reconstructed stat block "
                        f"({len(block_lines)} lines) in '{doc_name}'"
                    )
                    _log.warning(msg)
                    warnings.append(msg)
                    i = j
                    continue
            out.append(line)
            i += 1

        return "\n".join(out), blocks_found

    @staticmethod
    def _has_stat_keyword(line: str) -> bool:
        return any(kw in line for kw in _STAT_KEYWORDS)

    def _preserve_creature_blocks(self, text: str) -> str:
        """Log recognised creature example blocks (prose + stat lines); text unchanged."""
        sections = re.split(r"(?m)^#{1,6}\s+", text)
        for section in sections:
            lines = section.splitlines()
            has_prose = sum(1 for ln in lines if len(ln.split()) >= 8) >= 2
            has_stat = any(self._has_stat_keyword(ln) for ln in lines)
            if has_prose and has_stat:
                _log.debug(
                    "[corpus-cleaner] No pattern matched for block — passing through unchanged"
                )
        return text
