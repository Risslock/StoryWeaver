"""Corpus pre-processing and cleaning — sits between PDF extraction and chunking."""

from __future__ import annotations

import logging
from core.config import settings as _cfg
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
# Require "Keyword:" (colon) so common prose words (Step, Action, Damage) are not false-positives.
_STAT_KEYWORDS: frozenset[str] = frozenset({
    "DEX", "STR", "TOU", "PER", "WIL", "CHA",
    "Initiative", "Wounds", "Unconsciousness", "Death",
    "Armor", "Mystic", "Physical", "Step",
    "Action", "Attacks", "Damage",
})
_STAT_KEYWORD_RE = re.compile(
    r"\b(?:DEX|STR|TOU|PER|WIL|CHA|Initiative|Wounds|Unconsciousness|Death"
    r"|Armor|Mystic|Physical|Step|Action|Attacks|Damage)\b\s*:"
)

# TOC line: text followed by dot-leaders (2+ dots), wide whitespace gap (3+ spaces), or tab, then
# a page number. [.\s]{2,} was too broad — two spaces plus a digit matched stat block values.
_TOC_LINE_RE = re.compile(r"^.{1,100}(?:\.{2,}|\s{3,}|\t)\s*\d+\s*$")

# TOC section heading.
_TOC_HEADING_RE = re.compile(
    r"^#{1,6}\s*(?:Table of Contents|Contents|TOC)\s*$",
    re.IGNORECASE,
)

# De-hyphenation: join when alphabetic char surrounds the hyphen-newline.
# Matches both single-\n (within page) and double-\n\n (page-join boundary).
_DEHYPHEN_RE = re.compile(r"([a-zA-Z])-\n{1,2}([a-zA-Z])")

# ── FR-001: Windows-1252 C1 mojibake → correct Unicode ───────────────────────
# PDF text layers sometimes store smart-quote bytes (0x80–0x9F in Win-1252) which
# pymupdf decodes to the matching Latin-1 / Unicode C1 control code points instead
# of the intended printable character.  The map below corrects all 26 affected
# positions.  Integer keys are Unicode ordinals (chr(0x91) == U+0091, etc.).
_WIN1252_MAP = str.maketrans({
    0x80: "€",  # €
    0x82: "‚",  # ‚
    0x83: "ƒ",  # ƒ
    0x84: "„",  # „
    0x85: "…",  # …
    0x86: "†",  # †
    0x87: "‡",  # ‡
    0x88: "ˆ",  # ˆ
    0x89: "‰",  # ‰
    0x8a: "Š",  # Š
    0x8b: "‹",  # ‹
    0x8c: "Œ",  # Œ
    0x8e: "Ž",  # Ž
    0x91: "‘",  # '
    0x92: "’",  # '
    0x93: "“",  # "
    0x94: "”",  # "
    0x95: "•",  # •
    0x96: "–",  # –
    0x97: "—",  # —
    0x98: "˜",  # ˜
    0x99: "™",  # ™
    0x9a: "š",  # š
    0x9b: "›",  # ›
    0x9c: "œ",  # œ
    0x9e: "ž",  # ž
    0x9f: "Ÿ",  # Ÿ
    0xfffd: "",      # U+FFFD bare replacement char → remove
})

# ── FR-002: Drop-cap OCR gap ──────────────────────────────────────────────────
# pymupdf4llm emits a drop-cap letter as an isolated single-char line immediately
# followed by the lowercase remainder.  Only matches at paragraph start (^) to
# avoid mis-joining single-letter words mid-sentence.
_DROPCAP_RE = re.compile(r"(?m)^([A-Z])\n([a-z])")

# ── FR-003: Image placeholder markup ─────────────────────────────────────────
# Two forms observed in ED4_Players_Guide:
#   ==> picture [WxH] intentionally omitted <==   (single line)
#   ----- Start of picture text -----\n...\n----- End of picture text -----
_IMAGE_PLACEHOLDER_RE = re.compile(
    r"==>[ \t]*[^\n]*?<=="
    r"|"
    r"-{3,}[ \t]*Start of picture text[ \t]*-{3,}.*?-{3,}[ \t]*End of picture text[ \t]*-{3,}",
    re.DOTALL | re.IGNORECASE,
)

# ── FR-004: Stranded page-number lines ───────────────────────────────────────
# PDF footer integers that land as isolated digit-only lines in the extracted text.
_PAGE_NUMBER_RE = re.compile(r"(?m)^[ \t]*\d{1,4}[ \t]*$")

# ── FR-005: Back-of-book index page detection ─────────────────────────────────
# A page is classified as an index page when >80% of its non-empty lines match
# the dot-leader pattern (TOC-style) or pipe-delimited table rows.
_INDEX_LINE_RE = re.compile(r"^.{1,120}(?:\.{2,}|\|)\s*\d*\s*$")

# ── FR-006: Backer-list page detection ───────────────────────────────────────
_NAME_TOKEN_RE = re.compile(r"\b[A-Z][a-z]+(?:\s[A-Z][a-z]+){0,2}\b")
_SENTENCE_END_RE = re.compile(r"[.!?](?:\s|$)", re.MULTILINE)

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
    noise_pages_discarded: int = 0
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


def _repair_encoding(text: str) -> str:
    """FR-001: Replace Windows-1252 C1 mojibake with correct Unicode characters."""
    return text.translate(_WIN1252_MAP)


def _repair_dropcap(text: str) -> str:
    """FR-002: Rejoin drop-cap OCR gaps: isolated ^[A-Z]\n[a-z] → concatenated."""
    return _DROPCAP_RE.sub(r"\1\2", text)


def _strip_image_placeholders(text: str) -> str:
    """FR-003: Remove pymupdf4llm image alt-text markup blocks.

    DEPRECATED(012): Docling output does not contain image placeholder markup.
    This rule is a no-op on DoclingIngestor output (feature 012, spike PR #19).
    """
    return _IMAGE_PLACEHOLDER_RE.sub("", text)


def _strip_page_numbers(text: str) -> str:
    """FR-004: Remove isolated digit-only lines (PDF footer page numbers).

    DEPRECATED(012): Docling output does not contain isolated page-number lines.
    This rule is a no-op on DoclingIngestor output (feature 012, spike PR #19).
    """
    return _PAGE_NUMBER_RE.sub("", text)


def _is_index_page(page: str) -> bool:
    """FR-005: Return True when >80% of non-empty lines look like index/TOC rows."""
    lines = [ln for ln in page.splitlines() if ln.strip()]
    if len(lines) < 5:
        return False
    matches = sum(1 for ln in lines if _INDEX_LINE_RE.match(ln.strip()))
    return matches / len(lines) > 0.80


def _is_backer_page(page: str) -> bool:
    """FR-006: Return True when page has dense proper-name tokens and no sentence structure."""
    names = _NAME_TOKEN_RE.findall(page)
    sentences = _SENTENCE_END_RE.findall(page)
    return len(names) > 40 and len(sentences) < 5


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
            frontmatter_threshold = _cfg.knowledge_cleaning_frontmatter_pages

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

        # ── Structural noise detection: back-of-book index & backer-list pages ──
        pages, noise_count = self._strip_noise_pages(pages, doc_name, warnings)

        # ── Stat block reconstruction (per page, before join, to log page numbers) ──
        stat_count = 0
        if profile.stat_block_reconstruction:
            rebuilt: list[PageText] = []
            for page in pages:
                cleaned_text, n = self._reconstruct_stat_blocks(
                    page.text, doc_name, warnings, page_num=page.page_num
                )
                stat_count += n
                rebuilt.append(PageText(page_num=page.page_num, text=cleaned_text))
            pages = rebuilt

        # ── Join remaining pages ──────────────────────────────────────────
        joined = "\n\n".join(p.text for p in pages)

        # ── String-level rules (applied on joined text) ───────────────────
        if profile.dehyphenation:
            joined, hyphens = self._dehyphenate(joined, doc_name, warnings)
        else:
            hyphens = 0

        if profile.stat_block_reconstruction and _log.isEnabledFor(logging.DEBUG):
            self._preserve_creature_blocks(joined)

        # ── Text-level passes (FR-001..FR-004, applied on joined text) ───────
        joined = _repair_encoding(joined)
        joined = _repair_dropcap(joined)
        joined = _strip_image_placeholders(joined)
        joined = _strip_page_numbers(joined)

        report = CleaningReport(
            hyphens_rejoined=hyphens,
            toc_lines_removed=toc_removed,
            frontmatter_pages_removed=fm_removed,
            stat_blocks_reconstructed=stat_count,
            multicolumn_pages_reconstructed=0,  # set by ingestor before calling cleaner
            noise_pages_discarded=noise_count,
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

        # Title-only page: every non-empty line is a Markdown heading AND total word count is
        # small. Chapter-opener pages can have heading-only content with 20+ words — keep those.
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if lines and all(ln.startswith("#") for ln in lines):
            word_count = sum(len(ln.split()) for ln in lines)
            if word_count < 20:
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
        page_num: int | None = None,
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
                    page_tag = f"page {page_num}, " if page_num is not None else ""
                    msg = (
                        f"[corpus-cleaner] Reconstructed stat block "
                        f"({len(block_lines)} lines, {page_tag}"
                        f"first: {block_lines[0]!r}) in '{doc_name}'"
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
        return _STAT_KEYWORD_RE.search(line) is not None

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

    def _strip_noise_pages(
        self,
        pages: list[PageText],
        doc_name: str,
        warnings: list[str],
    ) -> tuple[list[PageText], int]:
        kept: list[PageText] = []
        discarded = 0
        for page in pages:
            if _is_index_page(page.text):
                reason = "back-of-book index"
            elif _is_backer_page(page.text):
                reason = "backer-list"
            else:
                kept.append(page)
                continue
            msg = (
                f"[corpus-cleaner] Discarded structural noise page {page.page_num}"
                f" ({reason}) in '{doc_name}'"
            )
            _log.warning(msg)
            warnings.append(msg)
            discarded += 1
        return kept, discarded
