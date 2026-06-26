# Feature Specification: PDF Extraction Quality & Corpus Cleaning v2

**Feature Branch**: `011-pdf-extraction-quality`

**Created**: 2026-06-26

**Status**: Draft

**Input**: User description: "Empirical chunk analysis of ED4_Players_Guide (1206 chunks) revealed seven unsolved problem categories in the pymupdf4llm text-extraction pipeline. Address them with enhanced cleaning rules and evaluate vision LLM extraction as an alternative path for complex RPG PDFs."

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Clean Text Re-ingestion (Priority: P1)

A developer re-ingests the Earthdawn rulebook after this feature lands and observes dramatically cleaner chunks: no more encoding garbage characters, no image placeholder lines, no stranded page numbers, no stub fragments under 150 chars, and no 34k-char narrative chapter crammed into a single vector. The gold standard benchmark improves on direct-fact and numeric categories without re-tuning any prompts.

**Why this priority**: The seven cleaning problems degrade every downstream step — enrichment, embedding, retrieval, and answered quality. Fixing the text pipeline requires no new infrastructure or model, delivers immediate measurable gains across all question categories, and unblocks the fair evaluation of vision extraction in US2.

**Independent Test**: Re-ingest ED4_Players_Guide with `IngestionConfig(extraction_mode="text")`. Run the benchmark. Verify: (a) zero chunks with `�` replacement characters; (b) fewer than 1% of chunks under 150 chars; (c) zero chunks over 15,000 chars; (d) no chunks whose `original_text` contains `==> picture` or starts with a bare integer line; (e) Recall@10 is at least 5 pp above the pre-feature baseline recorded in `benchmark_results.jsonl`.

**Acceptance Scenarios**:

1. **Given** ED4_Players_Guide is ingested, **When** the corpus is inspected after cleaning, **Then** zero chunks contain Unicode replacement characters (`�`) or Windows-1252 mojibake sequences where curly quotes, apostrophes, em-dashes, and minus signs should appear.

2. **Given** a PDF page has a drop-cap first letter (oversized letter in a separate text box), **When** the page is extracted and cleaned, **Then** the resulting text begins with a complete word — the drop cap letter is rejoined with the rest of the word rather than dropped or left as an isolated character.

3. **Given** the PDF contains image placeholder markup (`==> picture … <==`, `--- Start of picture text ---`), **When** cleaning runs, **Then** those markup blocks are stripped from all chunk text.

4. **Given** a PDF page footer embeds a bare page number as a standalone line, **When** cleaning runs, **Then** those orphaned integer lines are removed from chunk text.

5. **Given** the chunker produces a chunk shorter than 150 chars (stub/fragment), **When** the post-chunk quality gate runs, **Then** the stub is merged with the following chunk rather than stored as an independent vector.

6. **Given** the chunker produces a chunk longer than 15,000 chars (entire narrative chapter or index table), **When** the post-chunk quality gate runs, **Then** the chunk is re-split into sub-chunks using the existing semantic chunker, each under the maximum threshold.

7. **Given** the back-of-book index pages (A-Z tables) or backer-list pages are encountered during ingestion, **When** structural noise detection runs, **Then** those pages produce zero chunks — they are detected and skipped regardless of their position in the document.

8. **Given** a heading contains bold or italic markdown markers (e.g., `## **Versatility**`, `## _**Important Attributes:**_`), **When** BreadcrumbExtractor assigns the breadcrumb for chunks under that heading, **Then** the breadcrumb path segment is the plain text of the heading with all markdown markers stripped (e.g., `> Versatility`, not `> **Versatility**`).

---

### User Story 2 — Vision LLM Extraction Path (Priority: P2)

A developer opts in to vision-based extraction for a PDF that has severe drop-cap, multi-column, or complex-table issues. Each page is rendered as an image and described by a local multimodal model, which produces well-formed Markdown that the rest of the pipeline (cleaner, chunker, enricher, BreadcrumbExtractor) processes identically to text-extracted Markdown. Chapter opening sentences are complete; table structure is coherent; drop-cap letters are not lost.

**Why this priority**: Text-layer extraction is fundamentally lossy for decorative typography. Vision extraction reads the rendered page — exactly what a human reader sees — making it robust to drop caps, multi-column reflow, and embedded graphics with caption text. It is an opt-in path because it is slower (one LLM call per page) and requires a vision-capable model in Ollama.

**Independent Test**: Re-ingest ED4_Players_Guide with `IngestionConfig(extraction_mode="vision")`. Spot-check 5 chapter-opening chunks — each must start with a complete sentence (no drop-cap gap). Run the benchmark. Compare per-category scores against the text-path baseline using the comparison tool introduced in US3.

**Acceptance Scenarios**:

1. **Given** `extraction_mode="vision"` is set in `IngestionConfig`, **When** a PDF is ingested, **Then** each page is rendered to an image and passed to the configured vision model via Ollama, which returns Markdown text for that page.

2. **Given** the vision model returns Markdown for a page, **When** the pipeline continues, **Then** that Markdown is processed by the same CorpusCleaner, chunker, BreadcrumbExtractor, and ChunkEnricher as the text-extraction path — no separate branch beyond the page-to-markdown step.

3. **Given** the vision model fails to extract a page (unavailable, timeout, empty response), **When** the extraction step runs, **Then** the pipeline retries up to `KNOWLEDGE_VISION_MAX_RETRIES` times (default 1); if all retries are exhausted, it logs an ERROR with the page number and failure reason and aborts the ingestion — it does NOT fall back to pymupdf4llm text extraction for that page.

4. **Given** `extraction_mode="text"` (the default), **When** a PDF is ingested, **Then** the behaviour is identical to the pre-feature pipeline — no performance regression, no new model calls.

5. **Given** a chunk is ingested, **When** it is stored in ChromaDB, **Then** its metadata includes `"extraction_mode": "text"` or `"extraction_mode": "vision"` so benchmark comparisons can distinguish the source path.

6. **Given** the vision model name is not configured (`KNOWLEDGE_VISION_MODEL` is unset) and `extraction_mode="vision"` is requested, **When** the pipeline starts, **Then** it logs an ERROR with a clear message naming the missing variable and aborts — it does NOT silently fall back to text extraction.

---

### User Story 3 — Benchmark Run Comparison Tool (Priority: P3)

A developer runs the gold standard benchmark twice — once after text-path re-ingestion, once after vision-path re-ingestion — and then runs a comparison command that produces a side-by-side per-category diff table showing delta MRR, delta nDCG, and delta Recall@10 for each of the five question categories. They can tell at a glance whether vision extraction helps holistic questions while hurting numeric ones, or whether it wins across the board.

**Why this priority**: Without a structured comparison tool, comparing two benchmark runs requires manual JSONL diffing. The per-category benchmark introduced in feature 010 produces the data; this story makes it actionable. It is P3 because the cleaning improvements (P1) and vision path (P2) must produce the data before comparison has value.

**Independent Test**: Produce two benchmark JSONL records (any two runs). Run the comparison tool with selectors for both records. The output must include a diff table with one row per category plus a global row, showing before/after metrics and the signed delta for each.

**Acceptance Scenarios**:

1. **Given** two benchmark records exist in `benchmark_results.jsonl` (identified by index, timestamp, or tag), **When** the comparison tool runs with both selectors, **Then** it outputs a side-by-side table with columns: Category, MRR-A, MRR-B, ΔMRR, nDCG-A, nDCG-B, ΔnDCG, Recall-A, Recall-B, ΔRecall — one row per category plus a global row.

2. **Given** the delta for a metric is positive, **When** the table renders, **Then** the delta is displayed with a `+` prefix; negative deltas are displayed as-is.

3. **Given** a selector does not match any JSONL record, **When** the comparison tool runs, **Then** it exits with a clear error message naming the unmatched selector and listing available records.

4. **Given** one record has `category_scores` and the other was produced before feature 010 (no `category_scores` field), **When** comparison runs, **Then** the tool handles the missing field gracefully — missing categories show `N/A` rather than crashing.

---

### Edge Cases

- What if a PDF has no text layer at all (fully scanned image-only)? Text extraction returns empty; the pipeline must detect this and log a WARNING. If `extraction_mode="vision"`, the vision path will handle the page normally. If `extraction_mode="text"`, the pipeline produces no chunks for that page.
- What if drop-cap repair produces a false positive on a legitimate single-letter word (e.g., "I woke")? The heuristic should only trigger when the isolated character is at the very start of a paragraph following a heading — not mid-sentence.
- What if stub merging produces a merged chunk that itself exceeds the maximum size threshold? The merge result must be passed through the re-split gate in the same pass.
- What if a back-of-book index page is detected mid-document (e.g., a mini-index at the end of a chapter)? Structural noise detection must work by content pattern, not by page position alone — a page that is >80% dot-leader or pipe-delimited index lines should be filtered regardless of page number.
- What if the vision model returns malformed Markdown (no headings, single block of prose)? As long as the response is non-empty (≥1 char after stripping), it is valid input for the chunker; BreadcrumbExtractor will fall back to `doc_name` alone. Output quality will be lower but the pipeline does not abort — only truly empty or error responses trigger the retry-then-abort path.
- What if re-ingestion is triggered mid-active query serving? The existing behaviour is preserved: the collection remains readable until re-ingestion completes and chunks are atomically overwritten.
- What if a vision ingestion run aborts mid-document (page 51 of 500 fails after exhausting retries)? Chunks already written to ChromaDB from pages 1–50 are left in place — no rollback. The developer must re-ingest the document after resolving the vision model failure. The next successful ingestion run overwrites the partial chunks via ChromaDB upsert (same chunk IDs). No cleanup step is required.

---

## Requirements *(mandatory)*

### Functional Requirements

**Enhanced Text Cleaning — Encoding & Typography (P1)**

- **FR-001**: CorpusCleaner MUST detect and repair Windows-1252 → UTF-8 encoding artifacts — replace Unicode replacement characters (`�`) and known mojibake sequences for curly quotes (`'`, `'`, `"`, `"`), em-dash (`—`), en-dash (`–`), and minus sign (`−`) with their correct Unicode equivalents.
- **FR-002**: CorpusCleaner MUST detect and repair drop-cap OCR gaps — when a paragraph begins with an isolated uppercase letter on its own text span followed immediately by a lowercase continuation, the isolated character MUST be prepended to the continuation word to restore the complete word.
- **FR-003**: CorpusCleaner MUST strip image placeholder markup: lines matching `==> picture … <==` and fenced blocks between `--- Start of picture text ---` and `--- End of picture text ---` MUST be removed from extracted text.
- **FR-004**: CorpusCleaner MUST strip stranded page-number lines: a line consisting solely of one to four digits (optionally surrounded by whitespace) that appears between two blank lines MUST be removed.

**Enhanced Text Cleaning — Structural Noise (P1 / P4)**

- **FR-005**: Structural noise detection MUST identify and discard back-of-book index pages regardless of page position — a page is classified as structural noise when more than 80% of its non-empty lines match the dot-leader pattern OR the pipe-delimited table-row pattern (`|…|…|`).
- **FR-006**: Structural noise detection MUST identify and discard backer-list pages — a page is classified as backer noise when it contains more than 40 name-like tokens (comma-separated or newline-separated words/names) with no sentence structure (no verb phrases, no punctuation beyond commas and newlines).

**Post-Chunk Quality Gate (P3 / P5)**

- **FR-007**: After chunking, the pipeline MUST enforce a minimum chunk size: any chunk shorter than `KNOWLEDGE_MIN_CHUNK_CHARS` (default 150 chars) MUST be merged with the immediately following chunk before enrichment. If the stub is the last chunk, it MUST be merged with the preceding chunk.
- **FR-008**: After chunking, the pipeline MUST enforce a maximum chunk size: any chunk exceeding `KNOWLEDGE_MAX_CHUNK_CHARS` (default 15,000 chars) MUST be re-split using the existing semantic chunker. The re-split sub-chunks replace the oversized chunk in the batch. The minimum-size gate MUST be re-applied after re-splitting.

**Breadcrumb Quality (P10)**

- **FR-009**: `BreadcrumbExtractor.extract()` MUST strip all markdown formatting characters (`*`, `_`, `#`, `` ` ``) from each heading segment before assembling the breadcrumb path string. The plain-text heading is used in the breadcrumb; the original markdown heading is used only for position matching.

**Vision LLM Extraction Path (P2)**

- **FR-010**: `IngestionConfig` MUST gain a new field `extraction_mode: Literal["text", "vision"] = "text"`. The default `"text"` preserves the existing pymupdf4llm pipeline exactly.
- **FR-011**: When `extraction_mode="vision"`, the pipeline MUST render each PDF page to a PNG image using PyMuPDF and pass it to a local vision-capable model via Ollama with a structured prompt requesting Markdown output for that page.
- **FR-012**: The vision model name MUST be configurable via `KNOWLEDGE_VISION_MODEL` environment variable. When `extraction_mode="vision"` is requested and `KNOWLEDGE_VISION_MODEL` is not set, the pipeline MUST log an ERROR naming the missing variable and abort — it MUST NOT silently fall back to text extraction.
- **FR-013**: When vision extraction fails for an individual page (model unavailable, timeout, empty response), the pipeline MUST retry up to `KNOWLEDGE_VISION_MAX_RETRIES` times (env var, default 1). If all retries are exhausted, the pipeline MUST log an ERROR with the page number and failure reason and abort the ingestion. It MUST NOT fall back to pymupdf4llm text extraction for that page.
- **FR-014**: Vision-extracted Markdown MUST be passed through the same CorpusCleaner, chunker, BreadcrumbExtractor, ChunkEnricher, embedder, and ChromaDB store as text-extracted Markdown — the two paths converge after the page-to-markdown step.
- **FR-015**: Every chunk stored in ChromaDB MUST include `"extraction_mode": "text" | "vision"` in its metadata.

**Benchmark Comparison Tool (P3)**

- **FR-016**: The benchmark harness MUST provide a comparison function that accepts two record selectors (integer index into `benchmark_results.jsonl`, e.g., `-1` for last, `-2` for second-to-last, or an ISO timestamp string) and produces a side-by-side per-category diff table printed to stdout.
- **FR-017**: The diff table MUST include columns: Category, MRR-A, MRR-B, ΔMRR, nDCG-A, nDCG-B, ΔnDCG, Recall-A, Recall-B, ΔRecall — with positive deltas prefixed by `+`.
- **FR-018**: When a selector does not match any record in `benchmark_results.jsonl`, the tool MUST exit with an error message listing available records.

**Documentation**

- **FR-019**: Feature documentation MUST explicitly state that applying new cleaning rules or switching extraction modes requires full re-ingestion of affected documents.

### Key Entities

- **ExtractionMode**: `"text"` or `"vision"` — the strategy used to convert a PDF page into Markdown. Stored as metadata on every chunk so runs can be filtered in benchmark comparisons.
- **ChunkQualityGate**: The minimum/maximum size bounds enforced after chunking. Not stored; a pure pipeline step that merges stubs and re-splits giants before enrichment.
- **StructuralNoisePage**: A page classified as TOC, back-of-book index, or backer list — discarded before chunking, producing zero chunks. Detection is content-pattern-based, not position-based.
- **BenchmarkComparison**: A side-by-side diff of two benchmark runs, keyed by per-category metrics from `benchmark_results.jsonl`.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After re-ingesting ED4_Players_Guide with enhanced text cleaning, zero chunks in the resulting collection contain Unicode replacement characters (`�`).
- **SC-002**: After re-ingesting with enhanced text cleaning, fewer than 1% of chunks are shorter than 150 chars (down from 18.1% in the baseline corpus).
- **SC-003**: After re-ingesting with enhanced text cleaning, zero chunks exceed 15,000 chars (down from 7 oversized chunks in the baseline corpus).
- **SC-004**: After re-ingesting with enhanced text cleaning, zero chunks contain image placeholder markup (`==> picture`) or consist solely of a bare page number.
- **SC-005**: After re-ingesting with enhanced text cleaning, the back-of-book A-Z index pages and Kickstarter backer list pages produce zero chunks (currently they contribute ~20 oversized, noisy chunks).
- **SC-006**: The gold standard Recall@10 after text-path re-ingestion is at least 5 percentage points above the pre-feature baseline recorded in `benchmark_results.jsonl`.
- **SC-007**: After re-ingesting with `extraction_mode="vision"`, at least 8 out of 10 spot-checked chapter-opening sentences are complete — the drop-cap first letter is present rather than missing.
- **SC-008**: The benchmark comparison tool produces a correctly formatted diff table for any two records in `benchmark_results.jsonl` within 2 seconds (no model calls required — reads JSONL only).

---

## Assumptions

- PyMuPDF (`fitz`) is already a project dependency via `pymupdf4llm` and can be used to render PDF pages to PNG images without adding a new package dependency.
- A vision-capable Ollama model (e.g., `llava`, `minicpm-v`, `moondream2`) must be pulled locally by the developer before using `extraction_mode="vision"` — no model is bundled with the project. If `KNOWLEDGE_VISION_MODEL` is not set, the pipeline aborts with an error rather than falling back silently.
- `KNOWLEDGE_VISION_MAX_RETRIES` is a new environment variable (default 1). Setting it to 0 disables retries; on first failure the pipeline aborts. Higher values increase resilience at the cost of longer failure detection time.
- Vision extraction is significantly slower than text extraction (one LLM call per page vs. one call per batch of chunks for enrichment). For a 500-page rulebook this could take 30–90 minutes depending on hardware. This is acceptable for an opt-in, one-time ingestion cost.
- The mojibake repair in FR-001 covers the specific characters observed in the ED4_Players_Guide corpus. Other encoding edge cases may require incremental additions to the repair table.
- Drop-cap repair (FR-002) is heuristic and will not catch all cases. False positives on single-letter words (e.g., "I", "A") are mitigated by restricting the heuristic to paragraph-start positions following a heading boundary.
- Full re-ingestion is required to apply any new cleaning rule or switch extraction mode — partial updates to an existing ChromaDB collection are not supported.
- The benchmark comparison tool reads from `benchmark_results.jsonl` and requires at least two records to produce a diff. It does not re-run any benchmark.
- `KNOWLEDGE_MIN_CHUNK_CHARS` and `KNOWLEDGE_MAX_CHUNK_CHARS` are new environment variables with defaults 150 and 15,000 respectively; they extend the existing `KNOWLEDGE_MAX_CHUNK_TOKENS` which continues to govern the chunker's internal splitting.

---

## Clarifications

### Session 2026-06-26

- Q: Which backer-list name-token threshold should FR-006 canonicalize — 30 or 40? → A: 40 tokens (research.md decision; conservative threshold reduces false positives on NPC-heavy pages)
- Q: When vision extraction fails for a page, should the pipeline fall back to pymupdf4llm, retry, or abort? → A: No fallback to text — retry up to `KNOWLEDGE_VISION_MAX_RETRIES` times (configurable, default 1); abort with ERROR on exhaustion. If `KNOWLEDGE_VISION_MODEL` is not set, also abort immediately with ERROR. Vision mode runs fully committed — no silent degradation.
- Q: On vision ingestion abort, should partial chunks already written to ChromaDB be rolled back? → A: No rollback — leave partial chunks in place; developer re-ingests after fixing the model; next successful run overwrites via upsert.
