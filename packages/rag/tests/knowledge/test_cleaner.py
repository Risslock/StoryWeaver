"""Unit tests for CorpusCleaner — plain Markdown in/out, no Ollama required (FR-012)."""

from __future__ import annotations

import os

import pytest

from rag.knowledge.cleaner import CleanedDocument, CorpusCleaner, PageText


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def cleaner() -> CorpusCleaner:
    return CorpusCleaner()


def _pages(*texts: str) -> list[PageText]:
    return [PageText(page_num=i, text=t) for i, t in enumerate(texts)]


# ══════════════════════════════════════════════════════════════════════════════
# User Story 1 — Structured Layouts (stat blocks, creature blocks)
# ══════════════════════════════════════════════════════════════════════════════

STAT_BLOCK_TEXT = """\
DEX: 6
STR: 8
TOU: 9
PER: 5
WIL: 7
CHA: 4
Initiative: 5
Wounds: 10
Physical Armor: 4
"""

STAT_BLOCK_SHORT = """\
DEX: 6
STR: 8
"""


def test_stat_block_reconstructed_as_markdown_table(cleaner: CorpusCleaner) -> None:
    result = cleaner.clean_text(STAT_BLOCK_TEXT, "rulebook")
    assert "| Attribute | Value |" in result.text
    assert "| --- | --- |" in result.text
    assert "| DEX | 6 |" in result.text
    assert result.report.stat_blocks_reconstructed >= 1


def test_stat_block_not_triggered_below_threshold(cleaner: CorpusCleaner) -> None:
    result = cleaner.clean_text(STAT_BLOCK_SHORT, "rulebook")
    # Only 2 stat lines — should NOT be reconstructed.
    assert result.report.stat_blocks_reconstructed == 0
    assert "| Attribute | Value |" not in result.text


def test_creature_block_preserved_contiguously(cleaner: CorpusCleaner) -> None:
    creature_text = """\
## Windling Thief

The Windling Thief is a nimble aerial scout. She favours hit-and-run tactics
and relies on her small size to avoid detection.

DEX: 8
STR: 4
TOU: 5
Initiative: 7
Wounds: 6
"""
    result = cleaner.clean_text(creature_text, "rulebook")
    # Stat block should be present (possibly reconstructed).
    assert "Windling Thief" in result.text
    # Prose should still be present.
    assert "hit-and-run tactics" in result.text


def test_source_type_novel_skips_stat_block(cleaner: CorpusCleaner) -> None:
    result = cleaner.clean_text(STAT_BLOCK_TEXT, "novel")
    assert result.report.stat_blocks_reconstructed == 0
    # No Markdown table injected.
    assert "| Attribute | Value |" not in result.text


def test_source_type_handwritten_skips_stat_block(cleaner: CorpusCleaner) -> None:
    result = cleaner.clean_text(STAT_BLOCK_TEXT, "handwritten")
    assert result.report.stat_blocks_reconstructed == 0


# ══════════════════════════════════════════════════════════════════════════════
# User Story 2 — De-Hyphenation
# ══════════════════════════════════════════════════════════════════════════════

def test_dehyphen_line_break_joined(cleaner: CorpusCleaner) -> None:
    result = cleaner.clean_text("kar-\nma", "rulebook")
    assert "karma" in result.text
    assert "kar-\nma" not in result.text


def test_dehyphen_multiple_breaks(cleaner: CorpusCleaner) -> None:
    text = "tal-\nent and cha-\nracter and dis-\ncipline"
    result = cleaner.clean_text(text, "rulebook")
    assert "talent" in result.text
    assert "character" in result.text
    assert "discipline" in result.text


def test_dehyphen_count_in_report(cleaner: CorpusCleaner) -> None:
    text = "one-\ntwo three-\nfour five-\nsix"
    result = cleaner.clean_text(text, "rulebook")
    assert result.report.hyphens_rejoined == 3


def test_dehyphen_preserves_intentional_hyphen(cleaner: CorpusCleaner) -> None:
    for term in ("one-shot", "half-magic", "step-based"):
        result = cleaner.clean_text(term, "rulebook")
        assert term in result.text, f"Preserved hyphen lost in: {term!r}"


def test_dehyphen_preserves_list_marker(cleaner: CorpusCleaner) -> None:
    text = "- item one\n- item two\n- item three"
    result = cleaner.clean_text(text, "rulebook")
    assert result.report.hyphens_rejoined == 0
    assert "- item one" in result.text


def test_dehyphen_cross_page_boundary(cleaner: CorpusCleaner) -> None:
    pages = [
        PageText(page_num=0, text="kar-"),
        PageText(page_num=1, text="ma"),
    ]
    result = CorpusCleaner().clean_pages(pages, "rulebook")
    assert "karma" in result.text
    assert result.report.hyphens_rejoined == 1


def test_dehyphen_applies_to_all_source_types(cleaner: CorpusCleaner) -> None:
    text = "kar-\nma"
    for st in ("rulebook", "supplement", "novel", "handwritten"):
        result = cleaner.clean_text(text, st)  # type: ignore[arg-type]
        assert "karma" in result.text, f"De-hyphen failed for source_type={st!r}"


# ══════════════════════════════════════════════════════════════════════════════
# User Story 3 — TOC Stripping
# ══════════════════════════════════════════════════════════════════════════════

_TOC_LINES_8 = "\n".join([
    "Chapter One — Introduction ............... 3",
    "Chapter Two — Races ....................... 15",
    "Chapter Three — Disciplines .............. 47",
    "Chapter Four — Talents ................... 89",
    "Chapter Five — Magic ..................... 123",
    "Chapter Six — Combat ..................... 201",
    "Chapter Seven — Equipment ................ 267",
    "Chapter Eight — Appendix ................. 301",
])

_TOC_LINES_3 = "\n".join([
    "Item one ...... 1",
    "Item two ...... 2",
    "Item three .... 3",
])


def test_toc_block_stripped(cleaner: CorpusCleaner) -> None:
    pages = [PageText(page_num=2, text=_TOC_LINES_8)]
    result = cleaner.clean_pages(pages, "rulebook", frontmatter_threshold=1)
    assert result.report.toc_lines_removed == 8
    assert "Chapter One" not in result.text


def test_toc_heading_stripped_with_block(cleaner: CorpusCleaner) -> None:
    text = "## Contents\n" + _TOC_LINES_8
    pages = [PageText(page_num=2, text=text)]
    result = cleaner.clean_pages(pages, "rulebook", frontmatter_threshold=1)
    # Heading and 8 TOC lines stripped.
    assert result.report.toc_lines_removed >= 8
    assert "Contents" not in result.text or "## Contents" not in result.text


def test_toc_short_list_preserved(cleaner: CorpusCleaner) -> None:
    pages = [PageText(page_num=2, text=_TOC_LINES_3)]
    result = cleaner.clean_pages(pages, "rulebook", frontmatter_threshold=1)
    assert result.report.toc_lines_removed == 0
    assert "Item one" in result.text


def test_toc_scoped_to_early_pages(cleaner: CorpusCleaner) -> None:
    # Page 25 is beyond the toc scope (threshold=10, scope=20).
    pages = [PageText(page_num=25, text=_TOC_LINES_8)]
    result = cleaner.clean_pages(pages, "rulebook", frontmatter_threshold=10)
    assert result.report.toc_lines_removed == 0
    assert "Chapter One" in result.text


def test_source_type_novel_no_toc_rule(cleaner: CorpusCleaner) -> None:
    pages = [PageText(page_num=2, text=_TOC_LINES_8)]
    result = cleaner.clean_pages(pages, "novel", frontmatter_threshold=1)
    assert result.report.toc_lines_removed == 0
    assert "Chapter One" in result.text


# ══════════════════════════════════════════════════════════════════════════════
# User Story 3 — Front Matter Stripping
# ══════════════════════════════════════════════════════════════════════════════

_COPYRIGHT_TEXT = "Copyright © 2019 FASA Games. All rights reserved.\nEarthdawn® Fourth Edition"

_DEDICATION_TEXT = "Dedicated to all the gamers who kept Earthdawn alive."

_TITLE_ONLY = "# Earthdawn Fourth Edition\n## Player's Guide"

_REAL_CONTENT = (
    "The Theran Empire fell when the Horrors broke through the Kaers. "
    "Adepts emerged from their shelters to reclaim the world of Barsaive. "
    "Magic flows through ley lines and concentrates in certain regions. "
    "Characters may follow the Path of the Swordmaster, Elementalist, or Nethermancer. "
    "Talents define the special abilities of each discipline. "
)


def test_frontmatter_copyright_page_stripped(cleaner: CorpusCleaner) -> None:
    pages = [PageText(page_num=0, text=_COPYRIGHT_TEXT)]
    result = cleaner.clean_pages(pages, "rulebook", frontmatter_threshold=10)
    assert result.report.frontmatter_pages_removed == 1
    assert "Copyright" not in result.text


def test_frontmatter_dedication_stripped(cleaner: CorpusCleaner) -> None:
    pages = [PageText(page_num=1, text=_DEDICATION_TEXT)]
    result = cleaner.clean_pages(pages, "rulebook", frontmatter_threshold=10)
    assert result.report.frontmatter_pages_removed == 1


def test_frontmatter_title_only_stripped(cleaner: CorpusCleaner) -> None:
    pages = [PageText(page_num=0, text=_TITLE_ONLY)]
    result = cleaner.clean_pages(pages, "rulebook", frontmatter_threshold=10)
    assert result.report.frontmatter_pages_removed == 1


def test_frontmatter_beyond_threshold_preserved(cleaner: CorpusCleaner) -> None:
    # Copyright text on page 12 (beyond default threshold of 10) must be preserved.
    pages = [PageText(page_num=12, text=_COPYRIGHT_TEXT)]
    result = cleaner.clean_pages(pages, "rulebook", frontmatter_threshold=10)
    assert result.report.frontmatter_pages_removed == 0
    assert "Copyright" in result.text


def test_real_content_not_stripped(cleaner: CorpusCleaner) -> None:
    pages = [PageText(page_num=3, text=_REAL_CONTENT)]
    result = cleaner.clean_pages(pages, "rulebook", frontmatter_threshold=10)
    assert result.report.frontmatter_pages_removed == 0
    assert "Barsaive" in result.text


def test_source_type_handwritten_no_frontmatter(cleaner: CorpusCleaner) -> None:
    pages = [PageText(page_num=0, text=_COPYRIGHT_TEXT)]
    result = cleaner.clean_pages(pages, "handwritten", frontmatter_threshold=10)
    assert result.report.frontmatter_pages_removed == 0
    assert "Copyright" in result.text


# ══════════════════════════════════════════════════════════════════════════════
# Bypass via env var (SC-005)
# ══════════════════════════════════════════════════════════════════════════════

def test_clean_text_empty_input(cleaner: CorpusCleaner) -> None:
    result = cleaner.clean_text("", "rulebook")
    assert result.text == ""
    assert result.report.hyphens_rejoined == 0


def test_clean_pages_raises_on_empty(cleaner: CorpusCleaner) -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        cleaner.clean_pages([], "rulebook")


def test_clean_pages_raises_on_invalid_source_type(cleaner: CorpusCleaner) -> None:
    with pytest.raises(ValueError, match="invalid source_type"):
        cleaner.clean_pages(_pages("text"), "unknown")  # type: ignore[arg-type]


# ══════════════════════════════════════════════════════════════════════════════
# Logging contract — warnings list in report
# ══════════════════════════════════════════════════════════════════════════════

def test_stat_block_warning_in_report(cleaner: CorpusCleaner) -> None:
    result = cleaner.clean_text(STAT_BLOCK_TEXT, "rulebook", doc_name="TestDoc")
    assert any("[corpus-cleaner]" in w for w in result.report.warnings)


def test_dehyphen_warning_in_report(cleaner: CorpusCleaner) -> None:
    result = cleaner.clean_text("kar-\nma", "rulebook", doc_name="TestDoc")
    assert any("Rejoined" in w for w in result.report.warnings)


def test_toc_warning_in_report(cleaner: CorpusCleaner) -> None:
    pages = [PageText(page_num=2, text=_TOC_LINES_8)]
    result = CorpusCleaner().clean_pages(
        pages, "rulebook", doc_name="TestDoc", frontmatter_threshold=1
    )
    assert any("TOC" in w for w in result.report.warnings)


def test_frontmatter_warning_in_report(cleaner: CorpusCleaner) -> None:
    pages = [PageText(page_num=0, text=_COPYRIGHT_TEXT)]
    result = CorpusCleaner().clean_pages(
        pages, "rulebook", doc_name="TestDoc", frontmatter_threshold=10
    )
    assert any("front matter" in w for w in result.report.warnings)


# ══════════════════════════════════════════════════════════════════════════════
# Source type gating — rule profile matrix
# ══════════════════════════════════════════════════════════════════════════════

def test_supplement_same_profile_as_rulebook(cleaner: CorpusCleaner) -> None:
    rb = cleaner.clean_text(STAT_BLOCK_TEXT, "rulebook")
    sup = cleaner.clean_text(STAT_BLOCK_TEXT, "supplement")
    assert rb.report.stat_blocks_reconstructed == sup.report.stat_blocks_reconstructed


def test_novel_only_dehyphen_and_frontmatter(cleaner: CorpusCleaner) -> None:
    # TOC should be preserved for novel.
    pages = [PageText(page_num=2, text=_TOC_LINES_8)]
    result = CorpusCleaner().clean_pages(pages, "novel", frontmatter_threshold=1)
    assert result.report.toc_lines_removed == 0
    # De-hyphenation should still fire for novel.
    result2 = cleaner.clean_text("kar-\nma", "novel")
    assert "karma" in result2.text


def test_handwritten_only_dehyphen(cleaner: CorpusCleaner) -> None:
    pages = [PageText(page_num=0, text=_COPYRIGHT_TEXT)]
    result = CorpusCleaner().clean_pages(pages, "handwritten", frontmatter_threshold=10)
    # No front matter stripping for handwritten.
    assert result.report.frontmatter_pages_removed == 0
    # De-hyphenation still fires.
    result2 = cleaner.clean_text("kar-\nma", "handwritten")
    assert "karma" in result2.text
