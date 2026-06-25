# Contract: CorpusCleaner Public API

**Feature**: `008-corpus-cleaning`
**Module**: `packages/rag/rag/knowledge/cleaner.py`
**Date**: 2026-06-25

---

## Purpose

The `CorpusCleaner` is the single public interface for all corpus pre-processing rules.
Callers pass raw Markdown text (plus source type) and receive a `CleanedDocument` whose
`text` field is ready for the chunker. The cleaner has no awareness of vector stores, LLMs,
or embeddings — it is a pure text → text transformer.

---

## Public Types

```python
from typing import Literal
from dataclasses import dataclass

SourceType = Literal["rulebook", "supplement", "novel", "handwritten"]

@dataclass
class CleaningReport:
    hyphens_rejoined: int
    toc_lines_removed: int
    frontmatter_pages_removed: int
    stat_blocks_reconstructed: int
    multicolumn_pages_reconstructed: int
    warnings: list[str]

@dataclass
class CleanedDocument:
    text: str
    source_type: SourceType
    report: CleaningReport

@dataclass
class PageText:
    page_num: int   # 0-indexed
    text: str
```

---

## Public Methods

### `CorpusCleaner.clean_pages`

```python
def clean_pages(
    self,
    pages: list[PageText],
    source_type: SourceType,
) -> CleanedDocument
```

**For PDF ingestion**. Accepts a list of per-page Markdown segments (from
`pymupdf4llm.to_markdown(page_chunks=True)`) with page-number context. Applies rules
page-by-page where page awareness matters (front matter, TOC scoping), then joins all
remaining page texts and applies string-level rules (de-hyphenation, stat block patterns).
Returns a `CleanedDocument` with the joined, cleaned text.

**Contract**:
- `pages` must not be empty; raises `ValueError` if empty.
- `source_type` must be one of the four valid literals; raises `ValueError` otherwise.
- Every page in `pages` is either included in `CleanedDocument.text` or logged at WARNING
  with the reason for exclusion. No page is silently dropped.
- If all cleaning rules produce no changes, `CleanedDocument.text` equals
  `"\n\n".join(p.text for p in pages)` (the raw join).
- `CleaningReport` counters reflect the actual number of transformations applied;
  zero-count fields are valid and expected when no transformations fire.

---

### `CorpusCleaner.clean_text`

```python
def clean_text(
    self,
    text: str,
    source_type: SourceType,
) -> CleanedDocument
```

**For Markdown ingestion and unit tests**. Wraps `text` in `[PageText(page_num=0, text=text)]`
and delegates to `clean_pages`. Identical rule application; page-scoped rules treat the entire
text as page 0 (always within any front matter threshold ≥ 1).

**Contract**:
- `text` may be empty; returns `CleanedDocument(text="", source_type=..., report=...)` with
  all report counters at 0. Does not raise.
- All other contracts from `clean_pages` apply.

---

## Environment Variables

| Variable | Default | Effect |
|----------|---------|--------|
| `KNOWLEDGE_CLEANING_ENABLED` | `"true"` | When `"false"`, bypass check in `IngestionPipeline._extract_chunks()` skips the cleaner entirely; raw text reaches the chunker unchanged. |
| `KNOWLEDGE_CLEANING_FRONTMATTER_PAGES` | `"10"` | Maximum page index (exclusive) examined for front matter patterns. Pages at index ≥ this value are never stripped. |

These variables are read at the **call site** in `IngestionPipeline._extract_chunks()`, not
inside `CorpusCleaner`. The cleaner itself is always deterministic given the same inputs.

---

## Rule Profile per Source Type

| Rule | rulebook | supplement | novel | handwritten |
|------|----------|------------|-------|-------------|
| Multi-column reconstruction | ✅ | ✅ | ❌ | ❌ |
| Stat block reconstruction | ✅ | ✅ | ❌ | ❌ |
| De-hyphenation | ✅ | ✅ | ✅ | ✅ |
| TOC stripping | ✅ | ✅ | ❌ | ❌ |
| Front matter stripping | ✅ | ✅ | ✅ | ❌ |

The `CleaningRuleProfile` mapping is a module-level constant in `cleaner.py`. Changes to this
table require updating `cleaner.py` and re-running the full unit test suite.

---

## Logging Contract

All WARNING-level log messages emitted by `CorpusCleaner` follow this format:

```
[corpus-cleaner] {transformation} in '{doc_name}': {detail}
```

Examples:
- `"[corpus-cleaner] Removed front matter page 2 (copyright block) in 'ED4-Players-Guide'"`
- `"[corpus-cleaner] Stripped TOC section (34 lines) in 'ED4-Players-Guide'"`
- `"[corpus-cleaner] Rejoined 41 hyphenated line-breaks in 'ED4-Players-Guide'"`
- `"[corpus-cleaner] Reconstructed stat block (8 lines, page 47) in 'ED4-Players-Guide'"`
- `"[corpus-cleaner] Reconstructed multi-column layout (page 12, 3 columns) in 'ED4-Players-Guide'"`

DEBUG-level log for unrecognised/passthrough content:
```
"[corpus-cleaner] No pattern matched for block at page {N} — passing through unchanged"
```

The `doc_name` is passed by the ingestor caller (not by the cleaner itself); the cleaner
accepts an optional `doc_name: str = ""` parameter for log enrichment.

---

## Guarantees & Non-Guarantees

**Guarantees**:
- No exception is raised on unrecognised patterns; unrecognised content always passes through (FR-011).
- `CleanedDocument.text` is always a valid Markdown string (may be empty for empty input).
- `CleaningReport.warnings` contains the text of every WARNING message logged during that call.
- The cleaner is stateless; the same input always produces the same output.
- Thread-safe: no shared mutable state.

**Non-guarantees**:
- The cleaner does not guarantee pixel-perfect fidelity for complex multi-column layouts with
  merged cells, diagonal text, or overlapping bounding boxes.
- The cleaner does not validate that its output is "better" than the input — that is measured
  by the gold standard harness (FR-013, SC-003/004).
