# Research: Corpus Pre-Processing & Cleaning

**Feature**: `008-corpus-cleaning`
**Date**: 2026-06-25
**Status**: Complete

---

## Decision 1 — Extraction vs. Post-Extraction: Hybrid Approach

**Decision**: Use a **hybrid** approach:

- **Extraction layer** (upstream of cleaning): Switch `PdfIngestor._convert_to_markdown()` from
  single-string mode to `pymupdf4llm.to_markdown(file_path, page_chunks=True)`, which returns a
  `list[dict]` of per-page chunks. Each chunk carries `metadata["page"]` (0-indexed page number)
  and `text` (the Markdown for that page). Additionally, use PyMuPDF (`fitz`) directly alongside
  pymupdf4llm to extract block bounding boxes, enabling coordinate-based multi-column column
  detection before text conversion.
- **Cleaning layer** (post-extraction, post-text-join): A `CorpusCleaner` class receives the
  assembled per-page text segments with page-number context and applies rule-based transformations:
  de-hyphenation, TOC stripping, front matter stripping, and stat block normalisation.

**Why `page_chunks=True` is worth the refactoring effort**:
- Front matter detection becomes exact: the page index from `metadata["page"]` bounds the
  detection window to pages 0–(N-1) with no heuristic counting of `-----` separators.
- TOC detection can be scoped to the document's early pages, reducing false-positive risk in
  later chapters.
- Per-page text lets the cleaner remove entire page chunks before join, rather than pattern-
  matching across concatenated text boundaries.

**Why fitz block coordinates for multi-column**:
- `page_chunks=True` exposes page text but not block bounding boxes. Column detection from
  text alone (post-extraction) is unreliable because the left-to-right top-to-bottom read order
  interleaves column content. Using `fitz.Page.get_text("dict")["blocks"]` gives each block's
  `x0, y0, x1, y1` coordinates before any text conversion, enabling true column detection.
- Cost: one additional `fitz.open()` pass alongside pymupdf4llm. Both use the same underlying
  PyMuPDF engine; no new library dependency (`fitz` is already present via `pymupdf4llm`).

**Interface change**:
- `PdfIngestor._convert_to_markdown()` is refactored to return a `list[PageText]` (a local
  dataclass: `page_num: int, text: str`) instead of `str`. The cleaner receives this list,
  applies its rules page-by-page, and returns a `CleanedDocument` whose `text` field is the
  final joined string passed to the chunker.
- `MarkdownIngestor` is unaffected; it continues to read a plain string. The cleaner exposes
  a `clean_text(text: str, source_type: str) -> CleanedDocument` convenience method for the
  Markdown path and for unit tests (FR-012).
- The `_extract_chunks` method in `IngestionPipeline` calls `source_type`-aware ingestors;
  the rest of the pipeline is unchanged.

**Alternatives considered**:
- Single-string mode with `-----` separator counting — rejected in favour of `page_chunks`
  now that the user has confirmed the refactoring cost is acceptable.
- Switch to pdfplumber / camelot / tabula — rejected; requires OS-level deps (Ghostscript,
  Poppler, Java) that violate Principle IV and introduce packaging complexity. fitz is already
  a transitive dependency of pymupdf4llm.
- LLM-based layout reconstruction — rejected; violates FR-012 (independently testable without
  an LLM) and adds per-page LLM calls during ingestion.

---

## Decision 2 — Cleaner Module Location

**Decision**: The `CorpusCleaner` class and its supporting data types live in a new module
`packages/rag/rag/knowledge/cleaner.py`. No new package is created.

**Rationale**:
- Cleaning rules are specific to the knowledge ingestion domain; they have no use outside
  `packages/rag/rag/knowledge/`.
- A new package would require a new `pyproject.toml`, workspace entry, and cross-package
  dependency — unjustified complexity (Principle III).
- FR-012 testability is satisfied by `clean_text(text: str, source_type: str) → CleanedDocument`:
  unit tests pass a plain Markdown string in and assert a plain Markdown string out, with no
  vector store, LLM, or embedder required.

**Alternatives considered**:
- New `packages/cleaning/` package — rejected; no cross-package consumers; adds workspace
  overhead without boundary benefit.

---

## Decision 3 — De-Hyphenation Algorithm

**Decision**: Apply `re.sub(r'([a-zA-Z])-\n([a-zA-Z])', r'\1\2', text)` on the joined Markdown
text after all page texts have been assembled.

**Why at join time, not per-page**: A hyphen-break can span a page boundary
(`word-\n` at end of page N, `continuation` at start of page N+1). By running de-hyphenation
on the joined string, cross-page breaks are caught without special-casing.

**Pattern correctness**:
- Matches only `<word-char>-\n<word-char>`: requires alphabetic chars on both sides of the
  hyphen-newline. Excludes:
  - Standalone dashes `" - "` (no adjacent word chars)
  - List markers `"- item"` (hyphen at line start, no preceding word char)
  - Em-dashes `"—"` (different character)
  - Mid-word hyphens not at line-end: `"one-shot"` (no newline after the hyphen)
- The replacement removes the hyphen and newline, joining the two word fragments.
- Edge case: `"step-\nbased"` → `"stepbased"` — an intentional compound broken at a column edge.
  This is an accepted limitation of pure regex; the spec (FR-005) only requires removing
  line-break hyphenation, not preserving compound-word hyphens. A dictionary lookup would
  catch this but adds dependency and complexity not justified by the spec.

**Alternatives considered**:
- Dictionary lookup for compound-word preservation — rejected as out-of-spec scope.
- Per-page de-hyphenation — rejected; misses cross-page breaks.

---

## Decision 4 — TOC Detection Algorithm

**Decision**: A TOC section is identified as a block of ≥ 5 consecutive lines matching either:
- `r'^.{1,100}[.\s]{2,}\s*\d+\s*$'` — text followed by dots or spaces then a page number
- `r'^.{1,100}\t\d+\s*$'` — text followed by tab then a page number

If a heading immediately preceding the block matches `Table of Contents`, `Contents`, or `TOC`
(case-insensitive), the heading is also stripped. The entire contiguous matching block is removed.

**Scoping with page_chunks**: TOC detection is applied only within the first
`KNOWLEDGE_CLEANING_FRONTMATTER_PAGES + 10` pages (default: 20) to prevent false removal of
prose sections in later chapters.

**Why ≥ 5 lines**: RPG rulebook TOCs are densely packed (15–60 entries). A 5-line minimum
avoids removing prose lists that incidentally end in numbers (e.g., spell step-dice tables:
"Circle 1: 8, Circle 2: 10, Circle 3: 12").

**Alternatives considered**:
- Line-by-line removal regardless of block membership — rejected; too aggressive, can remove
  legitimate numbered content.

---

## Decision 5 — Front Matter Detection & Page Bounding

**Decision**: With `page_chunks=True`, front matter detection uses exact `metadata["page"]`
(0-indexed) values. Detection is applied to page chunks 0 through
`KNOWLEDGE_CLEANING_FRONTMATTER_PAGES - 1` (default: pages 0–9). Content on page ≥ threshold
is never examined for front matter patterns.

**Recognised front matter patterns** applied per page text:
1. **Copyright block**: page contains `©` or a line starting `Copyright` or `All rights reserved`.
2. **Dedication block**: page contains `Dedicated to`, `For ` (at sentence start), or `In memory of`.
3. **Publisher / ISBN block**: page contains `ISBN`, `Printed in`, or a publisher address
   (city + country following a company name on consecutive short lines).
4. **Title-only page**: page consists only of heading lines (no paragraph of ≥ 20 words).

Each matching page chunk within the threshold is removed entirely and logged at WARNING:
`"Removed front matter page {N} ({pattern}) from {doc}"`.

**Rationale**: Exact page numbers eliminate the `-----` separator counting heuristic from
Decision 1 single-string draft. Conservative patterns ensure no legitimate content is removed
(FR-011: unrecognised content passes through unchanged).

**Edge case (20-page introductions)**: A configurable threshold covers this. The threshold
applies to the *detection window* — content at page ≥ threshold passes through regardless
of its appearance.

**Alternatives considered**:
- Single-string mode with `-----` counting — replaced by page_chunks approach.
- Remove all content before the first non-front-matter heading — too aggressive.

---

## Decision 6 — Structured Layout (Stat Block & Multi-Column) Reconstruction

### Multi-Column Tables (fitz coordinate-based)

**Decision**: For PDF ingestion, use `fitz.Page.get_text("dict")["blocks"]` to detect when a
page has two or more horizontal column bands, then extract each column's text independently and
interleave rows. The result replaces the page's raw pymupdf4llm text before the cleaning pass.

**Algorithm sketch**:
1. For each page, collect block bounding boxes from fitz.
2. Cluster blocks by their x0 (left edge) into candidate column groups. If ≥ 2 distinct x0
   clusters exist with significant gap (> 20% of page width), treat as multi-column.
3. Sort blocks within each cluster by y0 (top edge) to get column-order reading.
4. Interleave columns row by row (matching blocks by overlapping y-ranges) to produce a
   column-correct reading order.
5. Reconstruct as a Markdown table if the content is tabular (headers + rows of comparable
   length) or as sequential paragraphs if prose.

**Scope**: active for `rulebook` and `supplement` source types only.

**Logged at WARNING**: `"Reconstructed multi-column layout (page {N}, {K} columns) in {doc}"`.

**What it handles**: racial attribute tables, talent/skill comparison tables, spell lists.
**What it does NOT handle**: complex nested tables, merged cells, diagonal/rotated text.
These pass through unchanged with a DEBUG log.

### Stat Block Reconstruction (post-extraction text cleaning)

**Decision**: Pattern-based detection on Markdown text. A stat block is a group of ≥ 3
consecutive short lines (≤ 80 chars) containing known Earthdawn 4E attribute keywords:
`DEX`, `STR`, `TOU`, `PER`, `WIL`, `CHA`, `Initiative`, `Wounds`, `Unconsciousness`,
`Death`, `Armor`, `Mystic`, `Physical`, `Step`, `Action`, `Attacks`, `Damage`.

**Reconstruction**: Detected lines are normalised into a Markdown key-value list:
`| Attribute | Value |` table rows, preserving original text. The block is flagged and logged
at WARNING: `"Reconstructed stat block (N lines) in {doc}"`.

**Scope**: `rulebook` and `supplement` source types only.

### Creature Example Blocks

**Decision**: A creature example block is identified when a Markdown section (content between
two heading markers) contains both prose paragraphs (≥ 2 sentences) and ≥ 1 embedded stat-block
pattern. Such sections are preserved contiguously — no internal splitting is applied — and marked
with a DEBUG log to confirm they were recognized.

**Scope**: `rulebook` and `supplement` source types only.

**Alternatives considered**:
- LLM reconstruction of stat blocks — rejected (violates FR-012, adds latency).
- pdfplumber table extraction — rejected (Decision 1: OS-level dependencies).

---

## Decision 7 — source_type Propagation

**Decision**: `source_type: str = "rulebook"` flows as a parameter through the call chain:

```
Gradio dropdown (FR-014)
  → knowledge.submit_document(source_type=...)
  → KnowledgeDocument.source_type column (new, String(20), server_default="rulebook")
  → pipeline.run(source_type=...)
  → PdfIngestor.ingest_async(source_type=...) / MarkdownIngestor.ingest_async(source_type=...)
  → CorpusCleaner.clean_pages(pages, source_type) / clean_text(text, source_type)
```

Stored in SQLite for auditability. A new Alembic migration adds `source_type STRING(20) NOT NULL
DEFAULT "rulebook"` to `knowledge_documents`. Valid literals: `"rulebook"`, `"supplement"`,
`"handwritten"`, `"novel"`.

**Rule profile matrix** (FR-008):

| Rule | rulebook | supplement | novel | handwritten |
|------|----------|------------|-------|-------------|
| Multi-column reconstruction | ✅ | ✅ | ❌ | ❌ |
| Stat block reconstruction | ✅ | ✅ | ❌ | ❌ |
| De-hyphenation | ✅ | ✅ | ✅ | ✅ |
| TOC stripping | ✅ | ✅ | ❌ | ❌ |
| Front matter stripping | ✅ | ✅ | ✅ | ❌ |

---

## Decision 8 — Bypass Mechanism

**Decision**: `KNOWLEDGE_CLEANING_ENABLED` env var (default: `"true"`). Checked in
`IngestionPipeline._extract_chunks()` before invoking the cleaner. When `"false"`, the raw
extracted text (joined page texts without cleaning) is passed directly to the chunker with a
single INFO log message. No code changes required to toggle.

---

## Decision 9 — Spec 007 Agentic-Chunker Baseline

The required benchmark baseline for SC-003 and SC-004:

| Strategy | MRR | nDCG | Recall@10 | Notes |
|----------|-----|------|-----------|-------|
| Heading | 0.5046 | 0.5890 | 0.8674 | Pre-spec-007 default |
| Semantic | 0.5607 | 0.6186 | 0.8660 | breakpoint_percentile=80 |
| Agentic | 0.5625 | 0.6227 | 0.8881 | batch_sections=1 |
| **Agentic (winner)** | **0.5767** | **0.6413** | **0.8966** | batch_sections=3, max_tokens=2000 — **current default** |

Pre-processing must not reduce MRR or Recall@10 below the agentic winner row (SC-003), and must
improve at least one of {MRR, nDCG, Recall@10} above it (SC-004). Verified by re-running
`harness/knowledge_qa/test_gold_standard.py` after full re-ingestion with `KNOWLEDGE_CLEANING_ENABLED=true`.
