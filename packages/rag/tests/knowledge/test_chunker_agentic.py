"""Unit tests for prose-density appendage merging in AgenticChunker.

All tests are pure/unit-level — no LLM or Ollama required.
"""

from __future__ import annotations

import logging
import os

import pytest

from rag.knowledge.chunker_agentic import AgenticChunker, _prose_ratio


# ── _prose_ratio() ─────────────────────────────────────────────────────────────


class TestProseRatio:
    def test_all_short_attribute_lines_returns_zero(self) -> None:
        # T007: all content lines have ≤7 words → ratio 0.0
        section = "## Game Information\nDEX: 11\nSTR: 10\nMovement Rate: 12"
        assert _prose_ratio(section) == 0.0

    def test_prose_sentences_returns_high_ratio(self) -> None:
        # T008: multiple full prose sentences (≥8 words each) → ratio ≥ 0.5
        section = (
            "## About T'skrang\n"
            "T'skrang are a reptilian race with elongated bodies and shimmering scales.\n"
            "They are known for their acrobatic prowess and daring personalities in combat."
        )
        assert _prose_ratio(section) >= 0.5

    def test_heading_only_section_returns_zero(self) -> None:
        # T009: heading line + no content → no content lines → 0.0
        section = "## Game Information"
        assert _prose_ratio(section) == 0.0

    def test_table_rows_excluded_from_denominator(self) -> None:
        # T010: table rows excluded from both prose count and denominator
        section = "## Stats\n| DEX | 11 |\n| STR | 10 |\n| CON | 12 |"
        assert _prose_ratio(section) == 0.0


# ── _merge_appendage_sections() ────────────────────────────────────────────────


class TestMergeAppendageSections:
    def test_stat_block_merged_into_preceding_prose_section(self) -> None:
        # T011: low-prose stat block merged into race description
        chunker = AgenticChunker(prose_threshold=0.3)
        sections = [
            "## T'skrang\nT'skrang are a reptilian race with elongated bodies and scales that glitter.\nThey are known for their acrobatic prowess and daring personalities.",
            "## Game Information\nDEX: 11\nSTR: 10\nMovement Rate: 12",
        ]
        result = chunker._merge_appendage_sections(sections)
        assert len(result) == 1
        assert "T'skrang" in result[0]
        assert "DEX" in result[0]

    def test_first_appendage_section_emitted_as_is(self) -> None:
        # T012: first section is appendage with no preceding → emitted standalone
        chunker = AgenticChunker(prose_threshold=0.3)
        sections = ["## Game Information\nDEX: 11\nSTR: 10"]
        result = chunker._merge_appendage_sections(sections)
        assert len(result) == 1
        assert result[0] == sections[0]

    def test_oversized_appendage_emitted_standalone(self) -> None:
        # T013: merge would exceed max_tokens * 4 → appendage stays standalone
        # max_tokens=5 → cap = 20 tokens → cap char limit ≈ 80 chars
        chunker = AgenticChunker(max_tokens=5, prose_threshold=0.3)
        preceding = "## T'skrang\nT'skrang are a reptilian race known for their daring nature."
        appendage = "## Stats\nDEX: 11\nSTR: 10"
        sections = [preceding, appendage]
        result = chunker._merge_appendage_sections(sections)
        # combined would exceed cap → both sections emitted separately
        assert len(result) == 2
        assert result[0] == preceding
        assert result[1] == appendage


# ── US2: Generalization across books ───────────────────────────────────────────


class TestGeneralizationAcrossBooks:
    def test_creature_statistics_heading_merged_as_appendage(self) -> None:
        # T014: non-ED4 heading "Creature Statistics" → classified by content, not name
        chunker = AgenticChunker(prose_threshold=0.3)
        sections = [
            "## Cave Troll\nCave Trolls are large brutish creatures that dwell in damp underground places.",
            "## Creature Statistics\nDEX: 8\nSTR: 18\nCarrying Capacity: 200",
        ]
        result = chunker._merge_appendage_sections(sections)
        assert len(result) == 1
        assert "Cave Troll" in result[0]
        assert "DEX" in result[0]

    def test_racial_abilities_heading_with_prose_not_merged(self) -> None:
        # T015: "Racial Abilities" heading but prose-heavy → NOT merged
        chunker = AgenticChunker(prose_threshold=0.3)
        sections = [
            "## T'skrang\nT'skrang are a reptilian race with elongated bodies and scales that glitter.",
            "## Racial Abilities\nT'skrang possess a natural ability to climb nearly any surface with ease.\nThey can also hold their breath for extended periods, allowing underwater movement.\nThis makes them exceptional scouts in aquatic or subterranean environments.",
        ]
        result = chunker._merge_appendage_sections(sections)
        assert len(result) == 2

    def test_two_consecutive_appendages_both_merged_into_preceding(self) -> None:
        # T016: two consecutive appendage sections both merged into growing preceding section
        chunker = AgenticChunker(prose_threshold=0.3)
        sections = [
            "## T'skrang\nT'skrang are a reptilian race with elongated bodies and beautiful scales.",
            "## Game Information\nDEX: 11\nSTR: 10",
            "## Additional Stats\nCON: 12\nWIS: 8",
        ]
        result = chunker._merge_appendage_sections(sections)
        assert len(result) == 1
        assert "T'skrang" in result[0]
        assert "DEX" in result[0]
        assert "CON" in result[0]


# ── US3: Threshold tuning via env/param ────────────────────────────────────────

_SECTION_40PCT_PROSE = (
    "## Mixed Stats\n"
    "This line contains eight or more whitespace separated words for the test.\n"
    "Another long prose line with at least eight words in it too.\n"
    "short\n"
    "DEX: 11\n"
    "STR: 10"
)

_PRECEDING_PROSE = (
    "## Background\n"
    "This creature has a long and storied history in the world of Earthdawn."
)


class TestLogging:
    def test_merge_event_logged_at_info(self, caplog: pytest.LogCaptureFixture) -> None:
        # M1 / FR-009 / SC-005: every merge must emit an INFO log line
        chunker = AgenticChunker(prose_threshold=0.3)
        sections = [
            "## T'skrang\nT'skrang are a reptilian race with elongated bodies and scales.",
            "## Game Information\nDEX: 11\nSTR: 10",
        ]
        with caplog.at_level(logging.INFO, logger="rag.knowledge.chunker_agentic"):
            chunker._merge_appendage_sections(sections)
        assert any(
            "Merged appendage" in r.message and r.levelno == logging.INFO
            for r in caplog.records
        )


class TestThresholdTuning:
    def test_high_threshold_merges_forty_percent_prose_section(self) -> None:
        # T017: prose_threshold=0.5 → ratio 0.4 < 0.5 → appendage → merged
        chunker = AgenticChunker(prose_threshold=0.5)
        result = chunker._merge_appendage_sections([_PRECEDING_PROSE, _SECTION_40PCT_PROSE])
        assert len(result) == 1
        assert "DEX" in result[0]
        assert "Background" in result[0]

    def test_low_threshold_does_not_merge_forty_percent_prose_section(self) -> None:
        # T018: prose_threshold=0.1 → ratio 0.4 > 0.1 → not appendage → NOT merged
        chunker = AgenticChunker(prose_threshold=0.1)
        result = chunker._merge_appendage_sections([_PRECEDING_PROSE, _SECTION_40PCT_PROSE])
        assert len(result) == 2

    def test_default_threshold_is_point_three(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # T019: no args, no env var → prose_threshold defaults to 0.3
        monkeypatch.delenv("KNOWLEDGE_AGENTIC_PROSE_THRESHOLD", raising=False)
        chunker = AgenticChunker()
        assert chunker._prose_threshold == pytest.approx(0.3)
