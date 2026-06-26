# Data Model: Appendage Section Merging

**Feature**: 009-appendage-section-merge
**Date**: 2026-06-26

This feature introduces no new persistent data models. It operates entirely in memory during the chunking pipeline. The key computational entities are documented below.

---

## Computational Entities

### ProseRatio `float`

A value in `[0.0, 1.0]` representing the fraction of a section's content lines that are prose.

**Computation**:
```
content_lines  = non-heading lines + non-table-row lines
prose_lines    = content_lines where word_count >= 8
prose_ratio    = prose_lines / len(content_lines)   # 0.0 when content_lines is empty
```

**Special case**: A section with zero content lines (heading-only) is always an appendage regardless of the ratio.

---

### AppendageClassification `bool`

The result of evaluating a section against the prose ratio threshold.

| Condition | Classification |
|---|---|
| `len(content_lines) == 0` | Appendage (heading-only) |
| `prose_ratio < threshold` | Appendage |
| `prose_ratio >= threshold` | Self-contained |

---

### MergeCandidate

An (appendage_section, preceding_section) pair evaluated for merging.

**Fields**:
- `preceding`: `str` — text of the section immediately before the appendage
- `appendage`: `str` — text of the section classified as an appendage
- `combined_tokens`: `int` — `estimate_tokens(preceding) + estimate_tokens(appendage)`
- `size_cap`: `int` — `max_tokens * 4`

**Merge outcome**:
- `combined_tokens <= size_cap` → merge: `preceding + "\n\n" + appendage`
- `combined_tokens > size_cap` → emit appendage standalone; log at INFO

---

## Configuration

| Env Var | Type | Default | Description |
|---|---|---|---|
| `KNOWLEDGE_AGENTIC_PROSE_THRESHOLD` | `float` | `0.3` | Prose ratio below which a section is an appendage |
| `KNOWLEDGE_MAX_CHUNK_TOKENS` | `int` | `800` | Used to derive size cap (`* 4`) |

---

## Pipeline Position

```
PDF / Markdown
      │
      ▼
HeadingChunker.split_by_headings()
      │  sections: list[str]
      ▼
AgenticChunker._merge_appendage_sections()   ← this feature
      │  merged sections: list[str]
      ▼
LLM batch loop (_chunk_batch per batch)
      │  chunks: list[str]
      ▼
_enforce_table_atomicity()
      │
      ▼
final chunks: list[str]
```
