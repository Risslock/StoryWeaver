# Tasks: Hybrid Search for Knowledge Retrieval

**Input**: Design documents from `/specs/014-hybrid-search/`

**Prerequisites**: plan.md ✅ | spec.md ✅ | research.md ✅ | data-model.md ✅ | contracts/ ✅ | quickstart.md ✅

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Add the hybrid-search configuration surface that every later phase reads.

- [X] T001 Add `hybrid_search_enabled: bool = False`, `hybrid_search_keyword_weight: float = 1.0`, `hybrid_search_vector_weight: float = 1.0` fields to the `Settings` class in `packages/core/core/config.py`; add a `@model_validator(mode="after")` that raises `ValueError("HYBRID_SEARCH_KEYWORD_WEIGHT must be > 0.0")` / `ValueError("HYBRID_SEARCH_VECTOR_WEIGHT must be > 0.0")` when either weight is `<= 0.0` (per contracts/config-contract.md)
- [X] T002 Add a `# ── Hybrid Search (feature 014) ──` section documenting `HYBRID_SEARCH_ENABLED` / `HYBRID_SEARCH_KEYWORD_WEIGHT` / `HYBRID_SEARCH_VECTOR_WEIGHT` to both `.env.example` and `.env`, mirroring the existing `KNOWLEDGE_*`/`JUDGE_*` section style (completed during planning)
- [X] T003 Create `packages/core/tests/__init__.py` and write unit tests in `packages/core/tests/test_config.py`: default `Settings()` instantiates with `hybrid_search_enabled=False`, `hybrid_search_keyword_weight=1.0`, `hybrid_search_vector_weight=1.0`; `HYBRID_SEARCH_KEYWORD_WEIGHT=0` env var raises `ValueError` on `Settings()` construction; `HYBRID_SEARCH_VECTOR_WEIGHT=-1` raises `ValueError`; a valid override (e.g. `HYBRID_SEARCH_KEYWORD_WEIGHT=1.5`) is accepted (depends on T001)

**Checkpoint**: Config surface exists and is validated. No retrieval behavior has changed yet (settings are unread by any other code so far).

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The lexical index itself and the shared data-model change every user story builds on.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T004 Implement `SQLiteLexicalStore` in `packages/rag/rag/knowledge/lexical_store.py`: `__init__(self, database_url: str | None = None)` (defaults to `core.config.settings.database_url` — same DB as `Campaign`/`KnowledgeDocument`, not a separate file), using its own `create_async_engine`/`async_sessionmaker` (mirroring `packages/rag/rag/evaluation/store.py`'s self-contained-engine pattern). Methods: `ensure_table()` — idempotent `CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_lexical USING fts5(chunk_id UNINDEXED, doc_id UNINDEXED, scope UNINDEXED, campaign_id UNINDEXED, access_level UNINDEXED, text, tokenize='porter unicode61')` executed via raw `sqlalchemy.text()` (FTS5 virtual tables aren't representable as declarative ORM models, same reason `EvaluationStore._migrate()` uses raw `text()`); `upsert(ids, texts, metadatas)` — delete-then-insert by `chunk_id` in one transaction per batch; `query(query_text, scope, role, top_k)` — tokenizes `query_text` into individually double-quoted terms joined with `OR` (avoids FTS5 syntax injection from free-text queries), runs `SELECT chunk_id, doc_id, scope, campaign_id, access_level, text, bm25(knowledge_lexical) AS score FROM knowledge_lexical WHERE knowledge_lexical MATCH :q AND scope = :scope AND (:role != 'player' OR access_level = 'player_visible') ORDER BY score ASC LIMIT :top_k`, returns `[]` for zero query terms or zero matching rows; `delete_by_doc(doc_id)`; `get_all(scope)`. Raise `core.errors.ProviderUnavailableError` on unrecoverable SQLite errors, matching `ChromaVectorStore`'s exception contract (per contracts/lexical-store-interface.md)
- [X] T005 [P] Add `matched_signals: list[str] = field(default_factory=list)` to the `KnowledgeChunk` dataclass in `packages/rag/rag/knowledge/interface.py`; update the `from dataclasses import dataclass` import to `from dataclasses import dataclass, field`
- [X] T006 Write unit tests for `SQLiteLexicalStore` in `packages/rag/tests/knowledge/test_lexical_store.py` (use a temp-file or `:memory:`-per-connection SQLite DB, not the shared dev DB): `ensure_table()` is idempotent (safe to call twice); `upsert()` + `query()` round-trip returns the inserted `chunk_id`; re-`upsert()`-ing an existing `chunk_id` replaces its row (no duplicates on `query()`); `query()` filters by `scope`; `query()` with `role="player"` excludes `access_level="gm_only"` rows; `query()` returns `[]` for a scope with zero rows or a query that tokenizes to zero terms; `delete_by_doc()` removes all rows for a `doc_id` and is a no-op (no error) for an unknown `doc_id` (depends on T004)

**Checkpoint**: Lexical index storage layer is fully implemented and tested in isolation. User story implementation can now begin.

---

## Phase 3: User Story 1 - Exact-Term Queries Return the Right Chunk (Priority: P1) 🎯 MVP

**Goal**: A query containing an exact rule/item/spell name or numeric value reliably surfaces the chunk containing that literal term to the reranker, even when vector-only search would rank a paraphrased chunk higher.

**Independent Test**: Quickstart Scenario 3 — run an exact-term query through `ChromaKnowledgeRetriever.search()` with `HYBRID_SEARCH_ENABLED=true` and confirm the chunk containing the literal term is present with `"lexical"` in `matched_signals`, where it was absent (or unmarked) in a `HYBRID_SEARCH_ENABLED=false` run.

- [X] T007 [US1] Wire lexical sync into ingestion: in `packages/rag/rag/knowledge/pipeline.py`, initialize `self._lexical_store = SQLiteLexicalStore()` in `IngestionPipeline.__init__`; call `await self._lexical_store.ensure_table()` once near the start of `run()`; immediately after the existing `await self._store.upsert(collection_name, ids, embeddings, compound_texts, metadatas)` call (pipeline.py:222), add `await self._lexical_store.upsert(ids, [m["original_text"] for m in metadatas], metadatas)` so both stores are written from the same batch (per research.md Decision 4 — index `original_text`, not the enrichment-augmented `compound` embedding text)
- [X] T008 [US1] Wire lexical delete into retrieval-side deletion: in `packages/rag/rag/knowledge/retriever.py`, initialize `self._lexical_store = SQLiteLexicalStore()` in `ChromaKnowledgeRetriever.__init__`; extend `delete_chunks_by_doc()` (retriever.py:59-67) to also call `await self._lexical_store.delete_by_doc(doc_id)` after the existing Chroma delete
- [X] T009 [US1] Extend `ChromaKnowledgeRetriever.search()` in `packages/rag/rag/knowledge/retriever.py` (retriever.py:88-197): when `core.config.settings.hybrid_search_enabled` is `True`, for each collection in `collections` (retriever.py:119-121), call `await self._lexical_store.query(query, col_scope, role, top_k)` using the **original** `query` string only — not the `alternatives` from `expand_query()` (per research.md Decision 3) — and tag each resulting list with signal `"lexical"`; tag every existing vector result list (retriever.py:131-156) with signal `"vector"`. Extend the RRF accumulation loop (retriever.py:158-167) so each list's contribution is `weight / (rrf_k + rank + 1)` where `weight = settings.hybrid_search_vector_weight` for `"vector"` lists and `settings.hybrid_search_keyword_weight` for `"lexical"` lists; accumulate a `dict[str, set[str]]` of which signals contributed to each `chunk_id`; populate `KnowledgeChunk.matched_signals = sorted(signals[chunk_id])` when building each candidate (retriever.py:170-188). When `hybrid_search_enabled` is `False`, no lexical lists are added and every candidate's `matched_signals == ["vector"]` — output must be identical to pre-014 behavior. Reranking (retriever.py:190-195) and the final `candidates[:top_k]` truncation are unchanged (depends on T004, T005)
- [X] T010 [P] [US1] Write unit tests for weighted fusion in `packages/rag/tests/knowledge/test_retriever_hybrid.py`: mock `ChromaVectorStore.query` and `SQLiteLexicalStore.query`; with `hybrid_search_enabled=False`, output `rrf_score`/ordering is identical to a vector-only baseline computed by hand; with `hybrid_search_enabled=True`, a chunk returned only by the lexical mock appears with `matched_signals == ["lexical"]`; a chunk returned by both mocks has `matched_signals == ["vector", "lexical"]`; increasing `hybrid_search_keyword_weight` raises a lexical-only match's rank relative to a fixed vector-only baseline (depends on T009)
- [X] T011 [US1] Implement `packages/rag/rag/knowledge/backfill_lexical_index.py` per contracts/backfill-cli.md: `argparse` CLI (`if __name__ == "__main__":` entry point, matching `harness/knowledge_qa/eval_runner.py`'s standalone-script convention) with `--campaign-id UUID` (optional), `--dry-run` (flag), `--chroma-path PATH` (default `./data/chroma`); calls `SQLiteLexicalStore.ensure_table()`; always processes `knowledge_global`, plus `knowledge_{campaign_id}` if `--campaign-id` given, else discovers all `knowledge_*` collections present at `--chroma-path`; for each collection calls `ChromaVectorStore.get_all(collection_name)` then `SQLiteLexicalStore.upsert(ids, [meta["original_text"] for meta in metadatas], metadatas)` in batches (skipped entirely under `--dry-run`, which only logs counts); logs INFO per collection (chunks found / chunks written); prints a final summary (collections processed, total chunks backfilled, elapsed time); exits 1 on an unreadable Chroma path or a `--campaign-id` that isn't a parseable UUID (depends on T004)
- [X] T012 [P] [US1] Write unit tests for backfill idempotency in `packages/rag/tests/knowledge/test_backfill.py`: running the backfill twice against the same temp Chroma fixture path produces the same row count in the lexical store (no duplicate rows); `--dry-run` writes zero rows; an invalid `--campaign-id` (not a UUID) exits 1 (depends on T011)
- [X] T013 [US1] Write an integration test (extend `harness/knowledge_qa/test_integration.py` or add `packages/rag/tests/knowledge/test_hybrid_integration.py`, matching the existing real-Ollama-reachability-skip pattern already used in `test_integration.py`): ingest a small fixture document containing a literal exact term via `IngestionPipeline.run()`, then call `ChromaKnowledgeRetriever.search()` with `HYBRID_SEARCH_ENABLED=true` and confirm the chunk containing that term is returned with `"lexical"` in `matched_signals` (depends on T007, T009)

**Checkpoint**: User Story 1 is fully functional and independently testable — literal-term queries reliably surface the matching chunk when hybrid search is enabled, and the lexical index stays in sync through both ingestion and backfill.

---

## Phase 4: User Story 2 - Measurable Retrieval and Answer Quality Improvement (Priority: P1)

**Goal**: A developer runs the existing retrieval eval harness and LLM-as-judge pipeline once with hybrid search disabled and once enabled, over the same gold-standard set, and gets a side-by-side comparison of retrieval metrics and judge scores — including a dedicated exact-term subset.

**Independent Test**: Quickstart Scenarios 3 (exact-term subset via `compare_benchmark_runs()`) and 4 (judge-score comparison via `eval_runner.py`/`judge_runner.py`).

- [X] T014 [P] [US2] Add `exact_term: bool = False` field to `TestQuestion` in `packages/rag/rag/knowledge/test_questions.py`; update `load_test_questions()`'s explicit `TestQuestion(...)` construction to pass `exact_term=bool(data.get("exact_term", False))` (field is optional — existing rows without it default to `False`)
- [X] T015 [US2] Tag the subset of rule/item-name/numeric-value questions in `harness/knowledge_qa/rag_gold_standard.jsonl` with `"exact_term": true`, per contracts/gold-standard-schema.md (depends on T014)
- [X] T016 [P] [US2] In `packages/rag/rag/knowledge/evaluator.py`: add `is_exact_term: bool` field to `RetrievalEvalResult` (populated from `test.exact_term` in `evaluate_question()`); add `exact_term_scores: CategoryMetrics | None = None` field to `EvalSummary`; in `aggregate_results()`, compute `exact_term_scores` by filtering the input `results` list on `is_exact_term` and reusing the existing `CategoryMetrics` mean-computation logic (return `None` when zero exact-term results are present) (depends on T014)
- [X] T017 [P] [US2] Write unit tests for the exact-term subset in `packages/rag/tests/knowledge/test_evaluator.py`: a mixed list of `is_exact_term=True/False` results produces `exact_term_scores` computed only over the `True` subset with the correct `question_count`; an all-`False` list produces `exact_term_scores is None` (depends on T016)
- [X] T018 [US2] Extend `run_gold_standard_benchmark()` in `harness/knowledge_qa/test_gold_standard.py`: add `hybrid_search_enabled`, `hybrid_search_keyword_weight`, `hybrid_search_vector_weight` (read from `core.config.settings`) and `exact_term_scores` (via `.model_dump()`, or `None`) to the `record` dict appended to `benchmark_results.jsonl` (depends on T016)
- [X] T019 [US2] Extend `compare_benchmark_runs()` in `harness/knowledge_qa/test_gold_standard.py`: print each compared run's `hybrid_search_enabled`/weight values alongside the existing timestamp header; add an `exact_term` row to the diff table (reusing the existing `_row()` helper) sourced from each record's `exact_term_scores` instead of `category_scores` (depends on T018)
- [ ] T020 [US2] Run Quickstart Scenario 4 end-to-end: `eval_runner.py` + `judge_runner.py --summary` with `HYBRID_SEARCH_ENABLED=false`, then again with `HYBRID_SEARCH_ENABLED=true`; confirm both produce complete `judge_aggregate` summaries and that the hybrid run's `exact_term` Recall@10/MRR exceeds the baseline by more than the 2-percentage-point threshold from spec.md's Clarifications, with no standard category regressing by more than 2 points (depends on T009, T018, T019)

**Checkpoint**: User Stories 1 and 2 together produce a full, reproducible baseline-vs-hybrid comparison across retrieval metrics, the exact-term subset, and downstream judge scores.

---

## Phase 5: User Story 3 - Toggle Hybrid Search Without Code Changes (Priority: P2)

**Goal**: Enabling/disabling hybrid search and adjusting keyword-vs-vector weighting requires only a configuration change; an invalid weight value fails loudly at startup rather than silently falling back.

**Independent Test**: Quickstart Scenario 2 — disabled run matches today's behavior exactly, enabled run with default weights succeeds, invalid weight value raises at startup.

- [X] T021 [US3] Extend `packages/rag/tests/knowledge/test_retriever_hybrid.py` (from T010) with an explicit disabled-path regression test: for a fixed mock query/collection setup, `HYBRID_SEARCH_ENABLED=false` output (`rrf_score` values, ordering, `matched_signals`) is asserted equal to a captured pre-014 fixture/snapshot, not just "equal to a hand-computed vector-only baseline" — closing the gap between "should be unchanged" and "verified unchanged" (depends on T009, T010)
- [X] T022 [US3] Verification pass: confirm (via T003's tests) that `Settings` raises `ValueError` at construction time — not at first query — when `HYBRID_SEARCH_KEYWORD_WEIGHT` or `HYBRID_SEARCH_VECTOR_WEIGHT` is `<= 0.0`; if any gap exists between T003's coverage and User Story 3 Acceptance Scenario 3, extend `packages/core/tests/test_config.py` to close it (depends on T003)
- [ ] T023 [US3] Run Quickstart Scenario 2 end-to-end (disabled → enabled with default weights → invalid weight value) and confirm all three pass criteria (depends on T009, T021, T022)

**Checkpoint**: All three user stories are independently functional and demonstrated via `quickstart.md`.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Code quality, observability, documentation.

- [X] T024 [P] Run `ruff check` and `pyright` on all new/modified files (`packages/rag/rag/knowledge/lexical_store.py`, `backfill_lexical_index.py`, modified `retriever.py`/`pipeline.py`/`interface.py`/`evaluator.py`/`test_questions.py`, `packages/core/core/config.py`, and all new test files); fix any errors
- [X] T025 [P] Verify `LOG_LEVEL=DEBUG` surfaces the lexical query text (post-tokenization), matched `chunk_id`s per signal, and per-list RRF weight contributions without crashing, per quickstart.md's Debugging section
- [X] T026 Update `README.md` to document: `HYBRID_SEARCH_ENABLED` / `HYBRID_SEARCH_KEYWORD_WEIGHT` / `HYBRID_SEARCH_VECTOR_WEIGHT` env vars, the `backfill_lexical_index.py` migration command and when to run it (once, before comparing baseline vs. hybrid on existing collections), and the `exact_term` tag in the gold-standard question format
- [ ] T027 Run all 5 Quickstart Scenarios from `specs/014-hybrid-search/quickstart.md` end-to-end and confirm SC-001 through SC-005 pass

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on T001 (Phase 1) for the config fields `search()` will read in Phase 3 — **BLOCKS all user stories**
- **US1 (Phase 3)**: Depends on Phase 2 (T004, T005) and T001; no dependency on US2 or US3
- **US2 (Phase 4)**: Depends on Phase 2 and T001. Tasks T014-T017 (gold-standard tagging, evaluator changes) have no code dependency on US1 and can proceed in parallel with Phase 3. Tasks T018/T020 (running an actual baseline-vs-hybrid comparison) require T009 (US1's retriever fusion change) to exist — otherwise toggling `HYBRID_SEARCH_ENABLED` has no observable effect
- **US3 (Phase 5)**: Depends on T001's validator and T009's enabled/disabled branching — this phase is primarily verification of behavior already implemented in Phases 1-3, plus one additional regression test
- **Polish (Phase 6)**: Depends on all prior phases

### User Story Dependencies

- **US1 (P1)**: Independent after Foundational — start immediately after Phase 2
- **US2 (P1)**: Independent after Foundational for T014-T017; T018/T020 depend on US1's T009
- **US3 (P2)**: Depends on US1's T009 for anything to verify; otherwise independent of US2

### Within Each Phase

- T001 and T002 can proceed in parallel (different files); T003 depends on T001
- T004 and T005 are parallel (different files); T006 depends on T004
- T007 and T008 both depend on T004 (SQLiteLexicalStore) but touch different files, so they are parallel with each other; T009 depends on T004 + T005 (touches the same file as neither T007 nor T008, but logically follows them for a coherent `retriever.py` diff)
- T010 depends on T009; T011 depends on T004 (independent of T009); T012 depends on T011; T013 depends on T007 + T009
- T014 is standalone; T015 depends on T014; T016 depends on T014; T017 depends on T016; T018 depends on T016; T019 depends on T018; T020 depends on T009 + T018 + T019
- T021 depends on T009 + T010; T022 depends on T003; T023 depends on T009 + T021 + T022

---

## Parallel Execution Examples

### Phase 1 — Setup

```
T001: config.py settings + validator
T002: .env.example + .env (already done)
(T003 starts after T001 completes)
```

### Phase 2 — Foundational

```
T004: lexical_store.py
T005: interface.py (matched_signals field)
(T006 starts after T004 completes)
```

### Phase 3 (US1) — parallel start after Foundational

```
T007: pipeline.py sync hook
T008: retriever.py delete hook
(T009 starts after T004 + T005 — extends retriever.py further)
(T010 starts after T009)
T011: backfill_lexical_index.py (parallel with T009, only needs T004)
(T012 starts after T011)
(T013 starts after T007 + T009)
```

### Phase 4 (US2) — parallel start after Foundational

```
T014: test_questions.py exact_term field
(T016 starts after T014 — evaluator.py)
(T015 starts after T014 — gold-standard tagging)
(T017 starts after T016)
(T018 starts after T016 — benchmark_results.jsonl provenance fields)
(T019 starts after T018)
(T020 starts after T009 + T018 + T019 — requires US1's retriever change to be meaningful)
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL — blocks all stories)
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: Run Quickstart Scenario 3 (single exact-term query, both configs)
5. Demo: an exact-term query that previously missed the right chunk now finds it with hybrid search enabled

### Incremental Delivery

1. Setup + Foundational → lexical index ready, config surface ready
2. US1 → literal-term retrieval reliably works, backfill available (MVP)
3. US2 → full baseline-vs-hybrid harness comparison, including the exact-term subset
4. US3 → toggle/weight behavior formally verified (disabled path unchanged, invalid config fails fast)
5. Polish → lint/type-check clean, README updated, all quickstart scenarios pass

---

## Notes

- [P] tasks involve different files with no blocking dependencies on in-progress work
- [Story] label maps each task to a user story for traceability
- Tests are included per constitution Principle V (Harness-Driven Quality)
- Each user story has one or more Quickstart scenarios as its independent acceptance test
- All new modules MUST use `logging.getLogger(__name__)` — no bare `print()` except in CLI output paths (Principle VIII)
- `HYBRID_SEARCH_ENABLED` defaults to `false`; disabled behavior must remain byte-for-byte identical to pre-014 `search()` output (T009, verified in T021)
- The lexical index lives in the same SQLite database as the rest of the app (`core.config.settings.database_url`), not a separate file like `data/eval.db`
- `backfill_lexical_index.py` is a production/development migration tool, not a harness script — it lives in `packages/rag/rag/knowledge/`, not `harness/knowledge_qa/`
