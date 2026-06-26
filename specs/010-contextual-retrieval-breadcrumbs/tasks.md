# Tasks: Contextual Retrieval, Breadcrumb Injection, Multi-Source Corpus & Per-Category Benchmarking

**Input**: Design documents from `specs/010-contextual-retrieval-breadcrumbs/`

**Tech stack**: Python 3.11+, chromadb, pymupdf4llm, pydantic-ai, OllamaProvider, pytest / ruff / pyright

**Source files**: `packages/rag/rag/knowledge/`, `harness/knowledge_qa/`, `apps/web/services/knowledge.py`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Introduce `IngestionConfig` â€” the new shared type that all preprocessing stories depend on. US1 (per-category benchmarking) is independent and can start immediately in parallel.

- [X] T001 Add `IngestionConfig` dataclass to `packages/rag/rag/knowledge/interface.py` with fields: `source_type: Literal["rulebook","supplement","handwritten_note","novel"] = "rulebook"`, `access_level_default: str | None = None`, `enable_breadcrumbs: bool = True`, `enable_contextual_summaries: bool = False`, `cleaning: bool = True`

---

## Phase 2: Foundational (Blocking Prerequisites for US2, US3, US4)

**Purpose**: Refactor `IngestionPipeline` to accept `IngestionConfig`; extend `Ingestor` with `extract_with_context`; fix the existing bug where `source_type` is not stored in ChromaDB metadata. US1 does **not** depend on this phase and can proceed in parallel.

**âš ï¸ CRITICAL**: US2, US3, and US4 cannot begin until this phase is complete.

- [X] T002 Add `async def extract_with_context(self, file_path: str, config: IngestionConfig) -> tuple[str, list[str]]` to `PdfIngestor` in `packages/rag/rag/knowledge/ingestor.py` â€” runs existing PDF â†’ clean â†’ chunk logic and returns `(full_cleaned_markdown_text, chunks)`; existing `ingest()` and `ingest_async()` remain unchanged
- [X] T003 Add `async def extract_with_context(self, file_path: str, config: IngestionConfig) -> tuple[str, list[str]]` to `MarkdownIngestor` in `packages/rag/rag/knowledge/ingestor.py` â€” reads, optionally cleans, and chunks the file; returns `(full_markdown_text, chunks)`
- [X] T004 Refactor `IngestionPipeline.run()` signature in `packages/rag/rag/knowledge/pipeline.py` to `run(self, doc_id, file_path, format, scope, campaign_id, config: IngestionConfig = IngestionConfig())` â€” remove `access_level_default` and `source_type` as top-level params; rename internal `_extract_chunks` â†’ `_extract` and have it call `ingestor.extract_with_context(file_path, config)` returning `(full_text, chunks)`; thread `config` through to `_build_records`
- [X] T005 Fix `_build_records()` in `packages/rag/rag/knowledge/pipeline.py` to write `"source_type": config.source_type` into the ChromaDB metadata dict (closes existing bug where `source_type` was accepted by `run()` but never stored per chunk)
- [X] T006 Update `_run_pipeline()` in `apps/web/services/knowledge.py` to construct `IngestionConfig(source_type=source_type, access_level_default=access_level_default)` and pass it as the `config` argument to `pipeline.run()`

**Checkpoint**: Pipeline accepts `IngestionConfig`; `source_type` is now stored in ChromaDB metadata for every new ingestion.

---

## Phase 3: User Story 1 â€” Per-Category Benchmark Visibility (Priority: P1) ðŸŽ¯ MVP

**Goal**: The benchmark harness reports MRR, nDCG, and Recall@10 per question category in the terminal and stores them in `benchmark_results.jsonl`. No re-ingestion required.

**Independent Test**: `uv run pytest harness/knowledge_qa/test_gold_standard.py -v -s` â€” terminal output must include a per-category table; the last line of `benchmark_results.jsonl` must contain a `category_scores` field with all five standard categories plus `uncategorized`.

- [X] T007 [P] [US1] Add `CategoryMetrics` Pydantic model to `packages/rag/rag/knowledge/evaluator.py` with fields `mean_mrr: float`, `mean_ndcg: float`, `mean_recall_at_k: float`, `question_count: int`
- [X] T008 [US1] Extend `EvalSummary` in `packages/rag/rag/knowledge/evaluator.py` with `category_scores: dict[str, CategoryMetrics] = {}` (optional field with empty-dict default preserves backward compat with existing JSONL records)
- [X] T009 [US1] Extend `aggregate_results(results: list[RetrievalEvalResult]) -> EvalSummary` in `packages/rag/rag/knowledge/evaluator.py` to group results by `result.category` (defaulting to `"uncategorized"` when empty), compute per-group mean MRR/nDCG/Recall@k and question count, and populate `EvalSummary.category_scores`; ensure all five standard categories (`direct_fact`, `comparison`, `holistic`, `numeric`, `relationship`) are always present with zero scores when no questions fall in a category
- [X] T010 [US1] Update `run_gold_standard_benchmark()` in `harness/knowledge_qa/test_gold_standard.py` to: (a) print a per-category metrics table to stdout after the global summary using the format in `contracts/benchmark-results.md`; (b) include `category_scores` (serialised from `summary.category_scores`) in the JSONL record appended to `benchmark_results.jsonl`

**Checkpoint**: Running the benchmark harness against the current index produces per-category scores in terminal output and in `benchmark_results.jsonl`.

---

## Phase 4: User Story 2 â€” Breadcrumb-Enriched Chunks (Priority: P2)

**Goal**: Every chunk ingested with `enable_breadcrumbs=True` is prefixed with its structural heading path (document â†’ chapter â†’ section). The breadcrumb is visible in `KnowledgeChunk.text` and in the separate `breadcrumb` field.

**Note**: US4 (source-type surface on `KnowledgeChunk`) is bundled here because it touches the same files. US4 tasks are labelled `[US4]`.

**Prerequisite**: Phase 2 complete.

**Independent Test**: Re-ingest one PDF with `IngestionConfig(enable_breadcrumbs=True)`. Retrieve 10 chunks â€” every chunk must have a non-empty `breadcrumb` field and its `text` must start with the same breadcrumb string.

- [X] T011 [US2] Create `packages/rag/rag/knowledge/breadcrumb.py` with `BreadcrumbExtractor` class; implement `extract(md_text: str, chunks: list[str], doc_name: str) -> list[str]` â€” scan `md_text` line-by-line for ATX headings (`# â€¦`, `## â€¦`, `### â€¦`), maintain a depth-keyed heading stack, record `(char_offset, breadcrumb_string)` pairs; for each chunk search `md_text` for the chunk's first 80 characters to determine position, select the last recorded breadcrumb whose offset â‰¤ chunk position; fall back to `doc_name` alone when no heading precedes the chunk or the chunk text cannot be located in `md_text`; breadcrumb format: `"doc_name > H1 > H2"` (deepest heading available)
- [X] T012 [US2] Add `breadcrumb: str = ""` field to `KnowledgeChunk` dataclass in `packages/rag/rag/knowledge/interface.py`
- [X] T013 [US4] Add `source_type: str = "rulebook"` field to `KnowledgeChunk` dataclass in `packages/rag/rag/knowledge/interface.py` (depends on T012 â€” edit same file sequentially)
- [X] T014 [US2] Integrate `BreadcrumbExtractor` into `IngestionPipeline.run()` in `packages/rag/rag/knowledge/pipeline.py` â€” after `_extract(file_path, format, config)` returns `(full_text, chunks)`, call `BreadcrumbExtractor().extract(full_text, chunks, doc_title)` when `config.enable_breadcrumbs=True` (else produce `[""] * len(chunks)`); store result as `all_breadcrumbs`; slice into `batch_breadcrumbs` per batch and pass to `_build_records`
- [X] T015 [US2] Update `_build_records()` signature in `packages/rag/rag/knowledge/pipeline.py` to accept `breadcrumbs: list[str]` and `contextual_summaries: list[str]` (stub empty lists for now); assemble `original_text` as `f"{breadcrumb}\n\n{raw_text}"` when `breadcrumb` is non-empty; add `"breadcrumb": breadcrumb` to the metadata dict; build compound text per the format table in `contracts/ingestion-pipeline.md` (breadcrumbs-on / summaries-off path for now)
- [X] T016 [P] [US2] Update `ChromaKnowledgeRetriever.search()` in `packages/rag/rag/knowledge/retriever.py` â€” when constructing `KnowledgeChunk` from metadata, add `breadcrumb=str(meta.get("breadcrumb", ""))` and `source_type=str(meta.get("source_type", "rulebook"))`

**Checkpoint**: Re-ingesting with `enable_breadcrumbs=True` produces chunks with breadcrumb prefixes; retrieved `KnowledgeChunk` objects expose `.breadcrumb` and `.source_type`.

---

## Phase 5: User Story 3 â€” Contextual Summaries for Semantic Retrieval (Priority: P3)

**Goal**: When `enable_contextual_summaries=True`, a 1â€“2 sentence LLM summary is prepended to each chunk's compound text before embedding. Failures fall back gracefully without aborting ingestion.

**Prerequisite**: Phase 2 and Phase 4 complete (breadcrumbs must be available for the summary prompt).

**Independent Test**: Re-ingest with `IngestionConfig(enable_breadcrumbs=True, enable_contextual_summaries=True)`. With `LOG_LEVEL=INFO`, one INFO line per chunk must appear confirming summary generation. Run the benchmark â€” holistic and comparison category scores should improve vs. the pre-feature baseline in `benchmark_results.jsonl`.

- [X] T017 [P] [US3] Add `_CONTEXTUAL_SUMMARY_SYSTEM` and `_CONTEXTUAL_SUMMARY_PROMPT` constants to `packages/rag/rag/knowledge/enricher.py` â€” system: instructs the LLM to write a factual 1â€“2 sentence retrieval context; prompt template: `"Document: {doc_title}\nSection: {breadcrumb}\n\nPassage:\n{chunk_text}\n\nWrite one or two sentences situating this passage within the document for search retrieval."` (see `research.md Â§3` for full wording)
- [X] T018 [US3] Implement `async def generate_contextual_summaries(self, texts: list[str], breadcrumbs: list[str], doc_title: str) -> list[str]` on `ChunkEnricher` in `packages/rag/rag/knowledge/enricher.py` â€” one `self._llm.generate()` call per chunk; on success log at INFO with chunk breadcrumb and `"contextual_summary=ok"`; on any exception (including `ProviderUnavailableError`) log at WARNING with breadcrumb and exception message and return `""` for that chunk; return list of same length as `texts`
- [X] T019 [US3] Integrate `generate_contextual_summaries()` into `IngestionPipeline.run()` in `packages/rag/rag/knowledge/pipeline.py` â€” after `enrich_batch(batch)`, when `config.enable_contextual_summaries=True` call `await enricher.generate_contextual_summaries(batch, batch_breadcrumbs, doc_title)`; else produce `[""] * len(batch)`; pass result as `contextual_summaries` to `_build_records`
- [X] T020 [US3] Update `_build_records()` in `packages/rag/rag/knowledge/pipeline.py` to include the contextual summary slot â€” when `contextual_summary` is non-empty, compound text becomes `f"{breadcrumb}\n\n{contextual_summary}\n\n{headline}\n\n{summary}\n\n{raw_text}"` (full format per `contracts/ingestion-pipeline.md`)

**Checkpoint**: Ingesting with both flags produces INFO logs per chunk; holistic/comparison benchmark scores improve vs. baseline.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T021 [P] Update `README.md` to reflect feature 010 as a delivered milestone â€” add: per-category benchmark output, breadcrumb-enriched chunks, opt-in contextual summaries, `source_type` metadata tag, `IngestionConfig` as the ingestion API; add a note that enabling breadcrumbs or contextual summaries on an existing index requires full re-ingestion
- [X] T022 Run full regression suite and fix any failures: `uv run pytest packages/rag/tests/ harness/knowledge_qa/ -v`, `uv run ruff check packages/rag/ harness/ apps/`, `uv run pyright packages/rag/`; confirm `LOG_LEVEL=DEBUG` surfaces expected log lines without crashing

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies â€” can start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 â€” blocks US2, US3, US4
- **US1 (Phase 3)**: Independent â€” can start immediately (parallel with Phase 1 + 2)
- **US2 + US4 (Phase 4)**: Depends on Phase 2 completion
- **US3 (Phase 5)**: Depends on Phase 2 and Phase 4 completion (needs breadcrumbs for summary prompt)
- **Polish (Phase 6)**: Depends on all story phases complete

### User Story Dependencies

```
Phase 1 â”€â”€â”¬â”€â”€â–¶ Phase 2 â”€â”€â–¶ Phase 4 (US2+US4) â”€â”€â–¶ Phase 5 (US3)
           â”‚                                              â”‚
           â””â”€â”€â–¶ Phase 3 (US1) â—€â”€â”€ independent â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
                                                          â”‚
                                                    Phase 6 (Polish)
```

- **US1**: No dependency on US2/US3/US4 â€” implement and validate independently first (MVP)
- **US2**: Depends on Phase 2 (IngestionConfig + pipeline refactor)
- **US4**: Bundled with US2 (same files, T013 + T016); label kept distinct for traceability
- **US3**: Depends on US2 (breadcrumbs needed as prompt context for summaries)

### Within Each Phase

- T002 â†’ T003 â†’ T004 â†’ T005 â†’ T006 (sequential, mostly same files)
- T007 â†’ T008 â†’ T009 â†’ T010 (sequential, evaluator then harness)
- T011 â†’ T012 â†’ T013 â†’ T014 â†’ T015; T016 after T012 + T013 (retriever reads new fields)
- T017 (parallel with T018 setup) â†’ T018 â†’ T019 â†’ T020

---

## Parallel Opportunities

```
# Phase 1 + US1 can run truly in parallel:
Task A: T001 (IngestionConfig in interface.py)
Task B: T007 â†’ T008 â†’ T009 â†’ T010 (US1 evaluator + harness â€” no pipeline dependency)

# Within Phase 4, after T012 + T013 are done:
Task: T016 (retriever reads breadcrumb + source_type)  â† no conflict with T014/T015

# Phase 5: T017 (add prompt constants) has no blockers within Phase 5:
Task: T017 (prompt constants) in parallel with reviewing T016 output
```

---

## Implementation Strategy

### MVP (Phase 1 + Phase 3 â€” US1 only)

1. Complete Phase 1: T001 â€” add `IngestionConfig` (5 min)
2. Complete US1: T007 â†’ T008 â†’ T009 â†’ T010 â€” evaluator + harness changes only
3. **STOP and VALIDATE**: `uv run pytest harness/knowledge_qa/test_gold_standard.py -v -s`
4. Per-category scores visible immediately â€” no re-ingestion needed

### Incremental Delivery

1. Phase 1 + Phase 3 â†’ **MVP**: per-category benchmarking working
2. Phase 2 (pipeline refactor) â†’ foundation laid; `source_type` bug fixed
3. Phase 4 (US2 + US4) â†’ re-ingest with breadcrumbs; benchmark direct_fact/numeric improves
4. Phase 5 (US3) â†’ re-ingest with summaries; benchmark holistic/comparison improves
5. Phase 6 â†’ README + regression clean

---

## Notes

- `[P]` = no file conflict with other `[P]` tasks in the same phase; safe to implement concurrently
- US1 is deliberately decoupled from the pipeline refactor â€” validate it first before touching the pipeline
- US4 is bundled with US2 (Phase 4) because both add fields to `KnowledgeChunk` and `retriever.py`
- Re-ingestion is required to observe US2/US3 effects on retrieval quality
- Do not add test tasks â€” the spec does not request TDD; the existing harness in `harness/knowledge_qa/` serves as the acceptance test suite

