# Tasks: Smart Chunking Strategy & Gold Standard Eval

**Input**: Design documents from `specs/007-chunking-strategy-gold-standard/`

**Organization**: Tasks are grouped by user story to enable independent implementation and
testing of each story. The foundational phase must complete before any user story work begins.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no shared dependencies)
- **[Story]**: Maps to user stories from spec.md (US1 = Gold Standard Harness,
  US2 = Adopt Winning Chunker, US3 = Research & Decision)

---

## Phase 1: Setup

**Purpose**: Repository housekeeping before any code changes.

- [X] T001 Add `harness/knowledge_qa/benchmark_results.jsonl` to `.gitignore` (append-only benchmark run history must not be committed)

---

## Phase 2: Foundational — BaseChunker Abstraction

**Purpose**: Extract the `BaseChunker` ABC and wire the factory + pipeline. Every user story
depends on this scaffolding — no US work can begin until this phase is complete.

**⚠️ CRITICAL**: Blocks all user stories. Complete sequentially.

- [X] T002 In `packages/rag/rag/knowledge/chunker.py`: add `BaseChunker(ABC)` with abstract `chunk(text: str) -> list[str]`, abstract `strategy_name: str` property, and default `async def async_chunk(text)` that runs `chunk()` in `asyncio.get_event_loop().run_in_executor(None, self.chunk, text)`
- [X] T003 In `packages/rag/rag/knowledge/chunker.py`: rename `MarkdownChunker` class to `HeadingChunker(BaseChunker)` — copy all existing logic verbatim, set `strategy_name = "heading"`; keep `MarkdownChunker = HeadingChunker` alias at module level emitting `DeprecationWarning` on instantiation
- [X] T004 In `packages/rag/rag/knowledge/chunker.py`: add `create_chunker(embed_fn=None, llm_provider=None) -> BaseChunker` factory that reads `KNOWLEDGE_CHUNKING_STRATEGY` env var (default `"heading"`), returns `HeadingChunker()` for `"heading"`, `SemanticChunker(embed_fn)` for `"semantic"`, `AgenticChunker(llm_provider)` for `"agentic"`, raises `ValueError` for unknown values
- [X] T005 In `packages/rag/rag/knowledge/ingestor.py`: update `PdfIngestor.__init__` parameter from `chunker: MarkdownChunker | None` to `chunker: BaseChunker | None`; default to `create_chunker()`; extract PDF→Markdown as `_convert_to_markdown(file_path) -> str`; add `async def ingest_async(file_path: str) -> list[str]` that calls `await self._chunker.async_chunk(self._convert_to_markdown(file_path))`; keep existing `ingest()` for backward compatibility
- [X] T006 In `packages/rag/rag/knowledge/ingestor.py`: update `MarkdownIngestor.__init__` parameter from `chunker: MarkdownChunker | None` to `chunker: BaseChunker | None`; default to `create_chunker()`; add `async def ingest_async(file_path: str) -> list[str]` that reads file then calls `await self._chunker.async_chunk(content)`; keep existing `ingest()` for backward compatibility
- [X] T007 In `packages/rag/rag/knowledge/pipeline.py`: change `_extract_chunks` from sync to `async def _extract_chunks(self, file_path: str, format: str) -> list[str]` calling `ingest_async()`; update `run()` to `chunks = await self._extract_chunks(...)`; add `_log.info("Ingestion started — chunking strategy: %s, doc_id: %s", create_chunker().strategy_name, doc_id)` after the first `await self._set_status(doc_id, "processing")`

**Checkpoint**: Run `uv run pytest packages/rag/tests/` — all existing tests must still pass. `ingest()` sync path is unchanged.

---

## Phase 3: User Story 1 — Gold Standard Harness (Priority: P1) 🎯 MVP

**Goal**: Reproducible benchmark harness that loads `rag_gold_standard.jsonl`, calls the
retriever with `scope="global"` and `role="gm"`, computes MRR / nDCG / Recall@10 per question,
and appends a `ChunkBenchmarkResult` record to `benchmark_results.jsonl`.

**Independent Test**: Run `uv run pytest harness/knowledge_qa/test_gold_standard.py -v -s`
against a populated knowledge base; confirm 118 questions are scored and a record is appended
to `benchmark_results.jsonl`.

- [X] T008 [US1] Create `harness/knowledge_qa/test_gold_standard.py`: define `GOLD_STANDARD_PATH = os.environ.get("GOLD_STANDARD_PATH", str(Path(__file__).parent / "rag_gold_standard.jsonl"))` and `BENCHMARK_RESULTS_PATH = Path(__file__).parent / "benchmark_results.jsonl"`; implement `run_gold_standard_benchmark(k: int = 10) -> EvalSummary` that (1) loads questions via existing `load_test_questions(GOLD_STANDARD_PATH)`, (2) skips via `pytest.skip` if Ollama is unreachable using the same pattern as `test_integration.py`, (3) calls `ChromaKnowledgeRetriever.search(query, campaign_id="", role="gm", top_k=k)` with `scope="global"` for each question, (4) calls `evaluate_question()` and `aggregate_results()` from `rag.knowledge.evaluator`, (5) appends a JSON line to `benchmark_results.jsonl` with fields: `strategy`, `timestamp` (ISO UTC), `gold_standard_path`, `k`, `total_questions`, `mean_mrr`, `mean_ndcg`, `mean_recall_at_k`, `notes`
- [X] T009 [US1] In `harness/knowledge_qa/test_gold_standard.py`: add `def test_gold_standard_recall_sanity()` that calls `run_gold_standard_benchmark()` and asserts `summary.mean_recall_at_k >= 0.40` (sanity gate — corpus populated and retriever working, not a performance comparison gate)
- [X] T010 [US1] Run the gold standard benchmark with `KNOWLEDGE_CHUNKING_STRATEGY=heading` (baseline): execute `uv run pytest harness/knowledge_qa/test_gold_standard.py::test_gold_standard_recall_sanity -v -s`, then copy the resulting `mean_mrr`, `mean_ndcg`, `mean_recall_at_k` from `benchmark_results.jsonl` into the Benchmark Score Table in `specs/007-chunking-strategy-gold-standard/research.md` (heading row)

**Checkpoint**: `benchmark_results.jsonl` contains one record for the heading strategy. Baseline scores are recorded in `research.md`.

---

## Phase 4: User Story 2 — SemanticChunker (Priority: P1)

**Goal**: `SemanticChunker` splits Markdown text using embedding-similarity breakpoints between
adjacent sentences, preserves table atomicity, and passes the `BaseChunker` invariant tests.

**Independent Test**: `uv run pytest packages/rag/tests/knowledge/test_chunkers.py -k semantic -v`
passes with stub embed_fn (no Ollama required).

- [X] T011 [US2] Create `packages/rag/tests/knowledge/test_chunkers.py`: write unit tests for `HeadingChunker` invariants (returns `[]` for empty input; no empty strings returned; table + heading stay together) using the existing `MarkdownChunker` test patterns as reference — these tests verify T003 (rename) did not break existing behavior
- [X] T012 [P] [US2] Create `packages/rag/rag/knowledge/chunker_semantic.py`: implement `_split_sentences(text: str) -> list[str]` using regex `(?<=[.!?])\s+` sentence splitter (same pattern as `_split_long_paragraph` in `HeadingChunker`), extended to handle Markdown heading lines and table rows as atomic sentence units (a line starting with `#` or `|` is its own "sentence")
- [X] T013 [US2] In `packages/rag/rag/knowledge/chunker_semantic.py`: implement `_cosine_similarity(a: list[float], b: list[float]) -> float` using `math.sqrt` and dot product (no numpy required); implement `_find_breakpoints(similarities: list[float], percentile: int) -> list[int]` that returns indices where similarity is below the `percentile`-th percentile of the similarity distribution
- [X] T014 [US2] In `packages/rag/rag/knowledge/chunker_semantic.py`: implement `SemanticChunker(BaseChunker)` with constructor `(embed_fn=None, max_tokens=None, breakpoint_percentile=None, min_chunk_tokens=None)` reading env vars as defaults; implement `chunk(text: str) -> list[str]` that (1) splits into sentences, (2) batch-embeds all sentences in one call via `embed_fn.embed(sentences)`, (3) computes pairwise cosine similarities, (4) finds breakpoints, (5) groups sentences into candidate chunks at breakpoints, (6) merges chunks below `min_chunk_tokens`, (7) splits chunks above `max_tokens` at sentence boundaries, (8) applies table atomicity (merges a table with its preceding heading chunk if they were split apart); set `strategy_name = "semantic"`
- [X] T015 [P] [US2] In `packages/rag/tests/knowledge/test_chunkers.py`: add `SemanticChunker` unit tests using a stub `EmbedFn` that returns deterministic vectors: (a) empty input returns `[]`; (b) no empty chunks returned; (c) high similarity between adjacent sentences → single chunk; (d) low similarity between adjacent sentences → two chunks; (e) table row and its heading stay in the same chunk regardless of similarity
- [X] T016 [US2] Re-ingest the Earthdawn rulebook PDF with `KNOWLEDGE_CHUNKING_STRATEGY=semantic` (clear ChromaDB first or use a separate collection), then run `uv run pytest harness/knowledge_qa/test_gold_standard.py::test_gold_standard_recall_sanity -v -s`; copy resulting scores from `benchmark_results.jsonl` into `research.md` semantic row

**Checkpoint**: Semantic unit tests pass without Ollama. Semantic benchmark scores recorded in `research.md`.

---

## Phase 5: User Story 2 — AgenticChunker (Priority: P1)

**Goal**: `AgenticChunker` splits heading sections using LLM proposition-boundary detection,
raises `NotImplementedError` on `chunk()` (always use `async_chunk()`), and propagates
`ProviderUnavailableError` on LLM failure.

**Independent Test**: `uv run pytest packages/rag/tests/knowledge/test_chunkers.py -k agentic -v`
passes with a stub LLM provider (no Ollama required).

- [X] T017 [P] [US2] Create `packages/rag/rag/knowledge/chunker_agentic.py`: implement `AgenticChunker(BaseChunker)` with constructor `(llm_provider=None, max_tokens=None, batch_sections=None)` reading env vars as defaults; `chunk()` raises `NotImplementedError("AgenticChunker requires async_chunk() — call await chunker.async_chunk(text) instead")`; `strategy_name = "agentic"`
- [X] T018 [US2] In `packages/rag/rag/knowledge/chunker_agentic.py`: implement `async def async_chunk(self, text: str) -> list[str]` that (1) splits text at heading boundaries using `HeadingChunker._split_by_headings(text)` logic to get N sections, (2) for each section sends one LLM call with system prompt `"You are a document chunker for a tabletop RPG knowledge base."` and user prompt asking for JSON `{"splits": [sentence_index, ...]}` indicating where new chunks start within the section, (3) parses the JSON response — on parse failure or LLM refusal, treats the entire section as one chunk and logs a WARNING, (4) reconstructs chunks from the split indices, (5) enforces table atomicity and max_tokens cap on each resulting chunk
- [X] T019 [US2] In `packages/rag/rag/knowledge/chunker_agentic.py`: add error handling — wrap each LLM call in try/except; raise `ProviderUnavailableError` (from `core.errors`) when the LLM is unreachable (propagates to `IngestionPipeline`, surfaces to UI per Principle VII); log each section at `DEBUG` level with section index and character count
- [X] T020 [P] [US2] In `packages/rag/tests/knowledge/test_chunkers.py`: add `AgenticChunker` unit tests using a stub `LLMProvider`: (a) `chunk()` raises `NotImplementedError`; (b) stub LLM returns valid `{"splits": [2]}` → two chunks produced; (c) stub LLM returns unparseable JSON → full section returned as single chunk (warning logged, no exception); (d) stub LLM raises `ProviderUnavailableError` → exception propagates from `async_chunk()`; (e) table + heading stay in the same chunk even when LLM splits inside a table
- [X] T021 [US2] Re-ingest the Earthdawn rulebook PDF with `KNOWLEDGE_CHUNKING_STRATEGY=agentic`, then run `uv run pytest harness/knowledge_qa/test_gold_standard.py::test_gold_standard_recall_sanity -v -s`; copy resulting scores from `benchmark_results.jsonl` into `research.md` agentic row

**Checkpoint**: Agentic unit tests pass without Ollama. All three strategy rows in `research.md` score table now have real values.

---

## Phase 6: User Story 3 — Research Decision (Priority: P2)

**Goal**: `research.md` contains all three strategy benchmark scores and a written recommendation
with rationale. The winning strategy is identified and justified.

**Independent Test**: Read `research.md` — the Benchmark Score Table has numeric values in all
three rows, and the Recommendation section names the winner with at least three sentences of
rationale covering quality, cost, and the MRR-as-tiebreaker rule.

- [X] T022 [P] [US3] In `specs/007-chunking-strategy-gold-standard/research.md`: complete the Benchmark Score Table — verify all three rows have real `mean_mrr`, `mean_ndcg`, `mean_recall_at_k` values from the runs in T010, T016, T021; add a `Date` for each row
- [X] T023 [US3] In `specs/007-chunking-strategy-gold-standard/research.md`: replace the placeholder Recommendation text with a concrete winner declaration: name the winning strategy (highest mean MRR per SC-003/004 rule), state the actual improvement over baseline (even if below 10%), and justify the decision covering quality signal, ingestion cost, and any edge cases observed during the benchmark runs

**Checkpoint**: `research.md` is complete and the winning strategy is committed in writing.

---

## Phase 7: User Story 2 — Adopt Winner (Priority: P1)

**Goal**: The winning strategy is the default for all new ingestion runs. Documentation and
configuration reflect the decision. The gold standard sanity test passes against a knowledge
base ingested with the winning strategy.

**Independent Test**: With `KNOWLEDGE_CHUNKING_STRATEGY` unset (or set to winner), run
`uv run pytest harness/knowledge_qa/test_gold_standard.py -v` — sanity gate passes, and
`benchmark_results.jsonl` record matches the strategy confirmed in `research.md`.

- [X] T024 [US2] Update `create_chunker()` factory default in `packages/rag/rag/knowledge/chunker.py` from `"heading"` to the winning strategy name (confirmed in T023); update the docstring to name the new default
- [X] T025 [P] [US2] Update `.env.example` (or equivalent environment template in the repo) to document `KNOWLEDGE_CHUNKING_STRATEGY` with allowed values (`heading`, `semantic`, `agentic`) and the current default; note that changing it requires re-ingesting all documents
- [X] T026 [US2] Re-ingest all existing documents in the knowledge base using the winning strategy (clear the ChromaDB global collection, then re-run ingestion for each document); run `uv run pytest harness/knowledge_qa/test_gold_standard.py::test_gold_standard_recall_sanity -v -s` to confirm the sanity gate passes with the now-default strategy

**Checkpoint**: The application ingests all new documents using the winning strategy by default. The gold standard sanity test passes.

---

## Phase 8: Polish & Cross-Cutting Concerns

- [X] T027 [P] Run `uv run ruff check packages/rag/rag/knowledge/chunker.py packages/rag/rag/knowledge/chunker_semantic.py packages/rag/rag/knowledge/chunker_agentic.py packages/rag/rag/knowledge/ingestor.py packages/rag/rag/knowledge/pipeline.py` — fix all lint errors
- [X] T028 [P] Run `uv run pyright packages/rag/rag/knowledge/` — fix all type errors (pay attention to `BaseChunker` import paths in `ingestor.py` and `pipeline.py`)
- [X] T029 Run the full existing test suite: `uv run pytest packages/rag/tests/ harness/knowledge_qa/test_evaluator.py harness/knowledge_qa/test_eval_service.py -v` — verify no regressions from the `MarkdownChunker → HeadingChunker` rename or `ingestor.py` changes
- [X] T030 Verify `DeprecationWarning` fires correctly: write a one-line check `python -c "import warnings; warnings.simplefilter('always'); from rag.knowledge.chunker import MarkdownChunker; MarkdownChunker()"` — confirm warning is emitted
- [X] T031 Run the quickstart.md validation end-to-end: follow steps 1–7 in `specs/007-chunking-strategy-gold-standard/quickstart.md` and confirm `benchmark_results.jsonl` contains the expected three strategy rows

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately
- **Phase 2 (Foundational)**: Depends on Phase 1 — BLOCKS all user stories
- **Phase 3 (US1 — Harness)**: Depends on Phase 2 (needs `async_chunk` pipeline)
- **Phase 4 (US2 — Semantic)**: Depends on Phase 2 and Phase 3 (needs baseline score from T010)
- **Phase 5 (US2 — Agentic)**: Depends on Phase 2 and Phase 3; can run in parallel with Phase 4
- **Phase 6 (US3 — Research)**: Depends on Phases 4 and 5 (needs all three strategy scores)
- **Phase 7 (US2 — Adopt)**: Depends on Phase 6 (needs the winner from research.md)
- **Phase 8 (Polish)**: Depends on Phase 7 — run all cleanup after adoption is confirmed

### User Story Dependencies

- **US1 (Harness)**: Unblocked after Phase 2 — independently testable
- **US2 (Chunkers)**: Unblocked after Phase 2; full adoption (Phase 7) blocked on US3
- **US3 (Research)**: Blocked on US1 (needs harness) and US2 chunker implementations (needs scores from T016, T021)

### Within Each Phase

- T002 → T003 → T004 (sequential: ABC first, then rename, then factory that references both)
- T005 and T006 can run in parallel (different classes in ingestor.py)
- T007 depends on T005 and T006
- T012 and T017 can run in parallel (different files)
- T015 and T020 can run in parallel (same file, different test classes — merge carefully)

### Parallel Opportunities

```
Phase 2 (within):    T005 ∥ T006,  then T007
Phase 4 ∥ Phase 5:  SemanticChunker and AgenticChunker implementations can be worked in parallel
Phase 4 (within):   T012 ∥ T011 (different files)
Phase 5 (within):   T017 ∥ T020 (implementation ∥ test stubs in different files)
Phase 8 (within):   T027 ∥ T028 ∥ T030
```

---

## Implementation Strategy

### MVP First (US1 Only)

1. Complete Phase 1: Setup (T001)
2. Complete Phase 2: Foundational (T002–T007)
3. Complete Phase 3: US1 Gold Standard Harness (T008–T010)
4. **STOP and VALIDATE**: Baseline scores in `benchmark_results.jsonl` and `research.md`
5. The team now has a working measurement tool — value delivered even before new chunkers

### Incremental Delivery

1. Phase 1 + 2 → Foundation ready (T001–T007)
2. Phase 3 → Harness + baseline scores (T008–T010) — measurement tool live
3. Phase 4 → Semantic chunker + scores (T011–T016)
4. Phase 5 → Agentic chunker + scores (T017–T021) — can overlap with Phase 4
5. Phase 6 → Research decision committed (T022–T023)
6. Phase 7 → Winner adopted as default (T024–T026)
7. Phase 8 → Polish (T027–T031)

---

## Notes

- `[P]` tasks operate on different files or independent concerns — safe to parallelise
- Benchmark runs (T010, T016, T021) require a populated ChromaDB and running Ollama — these are the only tasks that depend on external services
- Unit tests (T011–T015, T017–T020) use stub embed_fn and stub LLM — run without Ollama
- The `MarkdownChunker` alias (T003) must remain functional throughout this feature; it is removed in a future cleanup spec
- The `benchmark_results.jsonl` file is gitignored (T001) — developers manually copy scores into `research.md`
- `ingest()` sync paths (T005, T006) must not be removed — the existing unit tests in `packages/rag/tests/` use them directly

---

## Phase 9: Convergence — AgenticChunker Batch + Cross-Section Merge

**Purpose**: Close the gap between the `KNOWLEDGE_AGENTIC_BATCH_SECTIONS` env-var contract and
its actual effect. The field is stored but never read; this phase wires it up and adds the
cross-section merging capability that makes it valuable for RPG rulebooks where adjacent
sections frequently describe a single mechanic.

- [X] T032 Fix `async_chunk()` in `packages/rag/rag/knowledge/chunker_agentic.py` to actually use `self._batch_sections` — replace the one-at-a-time `for idx, section in enumerate(sections)` loop with a grouping loop that collects consecutive sections into batches of `self._batch_sections` size and passes each batch to a new `_chunk_batch()` method; remove the now-unused `_chunk_section()` call per plan: corrected batch design (partial)
- [X] T033 Implement `async def _chunk_batch(self, llm, sections: list[str]) -> list[str]` in `packages/rag/rag/knowledge/chunker_agentic.py` — replace `_chunk_section()` and `_USER_PROMPT_TEMPLATE`; new prompt presents sections as a numbered list (`[Section 0]\n...\n[Section 1]\n...`) and requests `{"chunks": [{"section": <int>, "start_sentence": <int>}, ...]}` where each entry marks the start of a new chunk; adjacent sections with no boundary entry between them are concatenated into a single chunk, enabling cross-section merging for RPG multi-section dynamics per plan: corrected batch design (missing)
- [X] T034 In `_chunk_batch()`, implement safe fallback — on `json.JSONDecodeError`, missing `"chunks"` key, or any `ValueError` during reconstruction, log `WARNING` with batch size and section lengths and return one chunk per section in the batch (not one monolithic block); `ProviderUnavailableError` from the LLM MUST still propagate uncaught per existing contract per plan: corrected batch design (missing)
- [X] T035 [P] Add `AgenticChunker` batch unit tests in `packages/rag/tests/knowledge/test_chunkers.py`: (a) `batch_sections=2`, stub LLM returns no boundary between section 0 and 1 → single merged chunk produced; (b) `batch_sections=2`, stub LLM places a boundary at `{"section": 1, "start_sentence": 0}` → two chunks; (c) stub LLM returns unparseable JSON for a batch of 2 sections → WARNING logged, 2 fallback chunks returned (one per section) per T020 (missing)
- [X] T036 [P] Update `specs/007-chunking-strategy-gold-standard/contracts/chunker-strategy.md` LLM prompt contract section (lines ~113–119) to document the multi-section prompt format and `{"chunks": [{"section": int, "start_sentence": int}]}` response schema; remove the old `{"splits": [...]}` example per plan: corrected batch design (partial)
