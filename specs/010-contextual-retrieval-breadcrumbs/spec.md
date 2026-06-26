# Feature Specification: Contextual Retrieval, Breadcrumb Injection, Multi-Source Corpus & Per-Category Benchmarking

**Feature Branch**: `010-contextual-retrieval-breadcrumbs`

**Created**: 2026-06-26

**Status**: Draft

**Input**: User description: "Four interconnected improvements to the RAG ingestion and evaluation pipeline: breadcrumb injection, contextual retrieval (LLM-prepended situating summary), multi-source metadata tagging, and per-category metric aggregation in the eval harness."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Per-Category Benchmark Visibility (Priority: P1)

A developer runs the retrieval benchmark after any ingestion change and immediately sees how each question type has shifted — not just the global average. They can tell whether a change helped direct-fact questions (stat block lookups) while hurting holistic questions (multi-section reasoning), and make targeted decisions about which improvement to pursue next.

**Why this priority**: The five existing question categories (`direct_fact`, `comparison`, `holistic`, `numeric`, `relationship`) are already present in the gold standard. This story requires no re-ingestion, no new LLM calls, and no schema changes — it is a pure eval harness improvement that immediately unlocks diagnostic value for all future iterations, including this very feature.

**Independent Test**: Run the benchmark harness against the current ChromaDB index. Confirm that MRR, nDCG, and Recall@10 are reported for each of the five categories in addition to the global totals, and that these per-category scores are captured in `benchmark_results.jsonl`.

**Acceptance Scenarios**:

1. **Given** the gold standard contains questions tagged with `category`, **When** the benchmark harness runs, **Then** the terminal output shows per-category MRR, nDCG, and Recall@10 alongside the global scores.
2. **Given** a benchmark run completes, **When** results are appended to `benchmark_results.jsonl`, **Then** each result record includes a `category_scores` field containing per-category metrics.
3. **Given** a gold standard question has no `category` field, **When** the benchmark runs, **Then** that question is counted in a catch-all `uncategorized` group and the run does not fail.
4. **Given** a developer compares two consecutive runs with different configurations, **When** they read `benchmark_results.jsonl`, **Then** they can identify which categories improved and which regressed between runs.

---

### User Story 2 - Breadcrumb-Enriched Chunks (Priority: P2)

A GM asks "What is the Movement Rate of a dwarf?" and the retrieved chunk carries its structural location — Player's Guide, Chapter 2, Dwarf — so the answer is grounded and the GM can confirm the source without cross-referencing the original PDF.

**Why this priority**: Breadcrumb injection is a structural change to the ingestion pipeline that enriches every chunk with location context. It is expected to improve `direct_fact` and `numeric` retrieval (where the question already implies a specific location) and does not require an LLM call per chunk, keeping ingestion cost low.

**Independent Test**: Ingest a single PDF chapter with breadcrumb injection enabled. Retrieve chunks for a direct-fact question. Every retrieved chunk must include the document name, chapter, and section in its text.

**Acceptance Scenarios**:

1. **Given** a PDF is ingested, **When** the ingestion pipeline processes a section, **Then** the stored chunk text begins with a breadcrumb that identifies the document, chapter, and section.
2. **Given** a chunk is retrieved for a question, **When** the GM reads the answer source in the UI, **Then** the breadcrumb is visible and accurately reflects the structural location of the passage.
3. **Given** a section spans multiple heading levels (e.g., Chapter > Sub-section > Sub-sub-section), **When** the chunk is stored, **Then** the breadcrumb reflects the deepest heading level available, not just the top-level chapter.
4. **Given** a document section has no heading (e.g., a preamble or continuation paragraph), **When** the chunk is stored, **Then** the breadcrumb uses the nearest ancestor heading or the document name alone, rather than being omitted or left blank.

---

### User Story 3 - Contextual Summaries for Semantic Retrieval (Priority: P3)

A GM asks "Which race is most agile in Earthdawn?" and the system retrieves the T'skrang chunk — even though the word "agile" does not appear anywhere in the stat block — because the chunk was enriched at ingestion time with a summary explaining that it describes the T'skrang race's agility-related attributes.

**Why this priority**: Contextual retrieval addresses vocabulary mismatch — the most common cause of retrieval failure in holistic and comparison questions. It adds one LLM call per chunk at ingestion time (a one-time cost) but significantly expands the semantic surface area of each chunk. Expected to improve `holistic` and `comparison` category scores most.

**Independent Test**: Ingest a document with contextual summaries enabled. For three questions whose keywords do not appear verbatim in the relevant chunk, verify that the correct chunk is nonetheless retrieved within the top-10 results.

**Acceptance Scenarios**:

1. **Given** a chunk is ingested, **When** contextual summaries are enabled, **Then** a 1-2 sentence summary describing the chunk's role and topic is generated and prepended to the chunk text before it is embedded.
2. **Given** a user queries with vocabulary that does not appear in the raw chunk text, **When** the retrieval system searches, **Then** the chunk with the matching contextual summary is returned in the top-10 results.
3. **Given** the LLM fails or is unavailable during ingestion, **When** contextual summary generation fails for a chunk, **Then** the chunk is ingested without a summary (using only breadcrumb + raw text) rather than the ingestion aborting.
4. **Given** contextual summaries are enabled, **When** a batch of chunks is ingested, **Then** summary generation is logged at INFO level per chunk so a developer can monitor progress and cost.

---

### User Story 4 - Source-Type Filtering at Retrieval (Priority: P4)

A GM configures the Q&A system to prefer rulebook chunks when answering rules questions and supplement chunks when answering lore questions — without changing any code.

**Why this priority**: Source-type tagging is a metadata enrichment that enables a new axis of retrieval control. Its primary value is unlocked once multiple source types are indexed together. It does not affect the content of chunks, only their metadata, so it carries low implementation risk.

**Independent Test**: Ingest two documents: one tagged as `rulebook` and one as `supplement`. Run retrieval with a source-type filter set to `rulebook`. Confirm that no `supplement` chunks appear in results.

**Acceptance Scenarios**:

1. **Given** a document is ingested, **When** a `source_type` is specified at ingestion time, **Then** every chunk produced from that document carries the specified `source_type` in its metadata.
2. **Given** no `source_type` is specified at ingestion, **When** the document is processed, **Then** chunks default to `source_type: rulebook` rather than being untagged.
3. **Given** a retrieval request includes a `source_type` filter, **When** the system retrieves chunks, **Then** only chunks matching the specified type are returned.
4. **Given** chunks from multiple source types are indexed, **When** no filter is applied, **Then** retrieval considers all source types and returns the most relevant chunks regardless of type.

---

### Edge Cases

- What if a PDF has no heading structure at all? The breadcrumb must fall back to the document filename as the only available location identifier.
- What if contextual summary generation returns an empty or nonsensical string? The chunk must be stored with raw text only; the failure must be logged at WARNING level so it is detectable.
- What if a gold standard question belongs to a category not present in the current run's result set (e.g., no `holistic` questions were answered)? The per-category report must show zero scores for that category rather than omitting it.
- What if re-ingestion is triggered mid-run while queries are being served? The existing collection must remain readable until re-ingestion completes and the collection is atomically swapped.
- What if the embedding model comparison produces a tie on global MRR? Per-category scores must be used as the tiebreaker axis in the comparison report.

## Requirements *(mandatory)*

### Functional Requirements

**Per-Category Benchmarking**

- **FR-001**: The benchmark harness MUST compute and display MRR, nDCG, and Recall@k separately for each `category` value present in the gold standard file.
- **FR-002**: Per-category scores MUST be appended to `benchmark_results.jsonl` alongside global scores in each result record.
- **FR-003**: Questions without a `category` field MUST be grouped under `uncategorized` and included in the per-category breakdown without causing the run to fail.

**Breadcrumb Injection**

- **FR-004**: Every chunk produced by the ingestion pipeline MUST be prefixed with a structural breadcrumb identifying the document name, chapter, and section before the chunk is stored.
- **FR-005**: The breadcrumb MUST reflect the most specific heading level available for the chunk's location within the document hierarchy.
- **FR-006**: When no heading is available, the breadcrumb MUST use the document filename or title as a fallback rather than being omitted.

**Contextual Summaries**

- **FR-007**: The ingestion pipeline MUST support an opt-in mode where a 1-2 sentence situating summary is generated per chunk and prepended to the chunk text before embedding.
- **FR-008**: Summary generation MUST be skippable per-chunk without aborting the ingestion run — chunks that fail summary generation MUST fall back to breadcrumb + raw text.
- **FR-009**: Each summary generation event MUST be logged at INFO level, including the chunk's breadcrumb and whether the summary succeeded or fell back.

**Multi-Source Metadata**

- **FR-010**: The ingestion pipeline MUST accept a `source_type` parameter with allowed values: `rulebook`, `supplement`, `handwritten_note`, `novel`.
- **FR-011**: When `source_type` is not specified, the pipeline MUST default to `rulebook`.
- **FR-012**: Retrieval MUST support optional filtering by `source_type` so that only chunks of the specified type are returned.
- **FR-013**: When no `source_type` filter is applied, retrieval MUST consider all source types.

**Re-ingestion & Backward Compatibility**

- **FR-014**: The feature documentation MUST explicitly state that adding breadcrumbs or contextual summaries to an existing index requires full re-ingestion — partial updates are not supported.

### Key Entities

- **Breadcrumb**: A structured location prefix attached to each chunk, encoding the document hierarchy (document name → chapter → section). Has no standalone existence — it is part of the chunk text.
- **Contextual Summary**: A 1-2 sentence description of a chunk's role and topic, generated by an LLM at ingestion time and prepended to the chunk before embedding. Stored as part of the embedded text, not as separate metadata.
- **Source Type**: A classification tag (`rulebook`, `supplement`, `handwritten_note`, `novel`) applied to all chunks from a given document at ingestion time. Stored as chunk metadata and used for retrieval filtering.
- **Category Score**: A per-question-category metric bundle (MRR, nDCG, Recall@k) computed during benchmark evaluation and stored in the results record alongside global scores.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After any benchmark run, per-category MRR, nDCG, and Recall@10 are visible in the terminal output for all five categories (`direct_fact`, `comparison`, `holistic`, `numeric`, `relationship`).
- **SC-002**: Every `benchmark_results.jsonl` entry produced after this feature lands includes a `category_scores` field; entries from prior runs are unaffected.
- **SC-003**: After ingestion with breadcrumbs enabled, every retrieved chunk contains the document name and at least one heading level in its visible text — verifiable by spot-checking 10 retrieved chunks for any query.
- **SC-004**: After ingestion with contextual summaries enabled, at least 3 out of 5 holistic or comparison gold standard questions that previously failed to retrieve the correct chunk in the top-10 now succeed — measured by re-running the benchmark.
- **SC-005**: Source-type filtering correctly excludes chunks from unselected types in 100% of filtered retrieval calls — verifiable by ingesting two documents of different types and confirming filter precision.
- **SC-006**: The embedding model comparison run (qwen3-embedding vs current model) produces a side-by-side per-category metric table showing which model wins on each question type.

## Assumptions

- The gold standard file (`harness/knowledge_qa/rag_gold_standard.jsonl`) already contains a `category` field for all 118 questions — no gold standard changes are needed for US1.
- Breadcrumb extraction relies on the heading structure produced by `pymupdf4llm` — documents that produce no headings will fall back to filename-only breadcrumbs.
- Contextual summary generation uses the existing LLM abstraction (`KNOWLEDGE_ENRICH_MODEL`); no new provider is introduced.
- Adding breadcrumbs or summaries changes the embedded text and therefore requires full re-ingestion — this is explicitly acceptable and documented.
- `source_type` defaults to `rulebook` for backward compatibility — all previously ingested documents are implicitly rulebooks.
- The embedding model comparison (`qwen3-embedding:4b` vs `nomic-embed-text`) is scoped to a benchmark matrix run after breadcrumbs and summaries are in place; it does not ship as a persistent configuration change.
- Re-ingestion during active query serving is an operational concern outside this feature's scope — the existing re-ingestion workflow (clear ChromaDB, re-ingest) is the supported path.
