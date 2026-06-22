---
description: "Task list for 005-rag-qa-system: Game Knowledge Q&A (RAG)"
---

# Tasks: Game Knowledge Q&A (RAG)

**Input**: Design documents from `specs/005-rag-qa-system/`

**Prerequisites**: plan.md ✅ | spec.md ✅ | research.md ✅ | data-model.md ✅ | contracts/knowledge-qa-ui.md ✅

**Tests**: Not explicitly requested — harness evals (Principle V) are included; pytest unit/integration tests are not.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no cross-task dependencies)
- **[Story]**: Which user story this task belongs to (US1–US5)
- Exact file paths are included in every description

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Add new dependencies and scaffold the module skeleton before any logic is written.

- [X] T001 Add `pymupdf4llm` and `pydantic-ai` to `packages/rag/pyproject.toml` dependencies
- [X] T002 Create `packages/rag/rag/knowledge/` sub-module: `__init__.py` for all files listed in plan.md (interface.py, enricher.py, chunker.py, ingestor.py, pipeline.py, retriever.py — stubs only)
- [X] T003 [P] Create `harness/knowledge_qa/fixtures/` directory with `sample_rules.md` (plain rules text) and `sample_gm_only.md` (GM-only lore block) fixture files for harness evals

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before any user story can be implemented.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T004 Add `KnowledgeDocument` SQLAlchemy ORM model (with `UniqueConstraint`, `campaign` relationship, and all columns per data-model.md §1) to `packages/core/core/models.py`
- [X] T005 Write Alembic migration `packages/core/core/migrations/versions/0005_knowledge_documents.py` — creates `knowledge_documents` table with `uq_knowledge_doc_title` constraint and indexes on `campaign_id` and `ingestion_status`
- [X] T006 [P] Define `packages/rag/rag/knowledge/interface.py` — `KnowledgeRetriever` ABC, `KnowledgeChunk` dataclass, `ChunkEnrichment` Pydantic model, `QueryExpansion` Pydantic model exactly as specified in data-model.md §3 and plan.md §Structured Output Pattern
- [X] T007 [P] Create placeholder `apps/web/pages/gm/knowledge_qa.py` — all Gradio components wired (chatbot, input, file upload, scope/access dropdowns, doc table, timer) per contracts/knowledge-qa-ui.md §1; chatbot initial message: "Knowledge Q&A — not yet implemented"
- [X] T008 [P] Create placeholder `apps/web/pages/player/knowledge_qa.py` — all Gradio components wired per contracts/knowledge-qa-ui.md §2; chatbot initial message: "Knowledge Q&A — not yet implemented"; file input restricted to `file_types=[".md"]`
- [X] T009 Register both Knowledge Q&A tabs in `apps/web/app.py` inside `gr.Tabs(elem_id="gm-tabs")` and `gr.Tabs(elem_id="player-tabs")` so the app launches and navigates to both tabs

**Checkpoint**: Run `uv run alembic upgrade head` (migration succeeds) and `uv run python apps/web/main.py` (both placeholder tabs visible and app navigable).

---

## Phase 3: User Story 1 — Ask a Game Question (Priority: P1) 🎯 MVP

**Goal**: A player or GM can type a natural-language question and receive a synthesized answer with at least one source citation drawn from pre-seeded knowledge base content.

**Independent Test**: With at least one document already indexed in ChromaDB (loaded via fixture or manual seeding), ask "How does combat initiative work?" and confirm a cited answer appears within 30 seconds.

### Implementation for User Story 1

- [X] T010 [US1] Implement `packages/rag/rag/knowledge/enricher.py` — pydantic-ai `Agent` with `result_type=QueryExpansion` for multi-query expansion (3 alternatives) and `result_type=ChunkEnrichment` for chunk enrichment; use `LLMProvider` abstraction per plan.md §Structured Output Pattern; fallback on `ValidationError` as described
- [X] T011 [US1] Implement `packages/rag/rag/knowledge/retriever.py` — `ChromaKnowledgeRetriever` implementing `KnowledgeRetriever` ABC: creates `knowledge_global` and `knowledge_{campaign_id_hex}` collections with `OllamaEmbeddingFunction(model_name=KNOWLEDGE_EMBED_MODEL, url=OLLAMA_BASE_URL)`, runs multi-query retrieval across both collections, applies RRF with k=60 (formula: `Σ 1/(k+rank_i)`), returns top-K `KnowledgeChunk` list sorted by `rrf_score` descending
- [X] T012 [US1] Create `apps/web/services/knowledge.py` — implement `ask_question(question, campaign_id, role) -> tuple[str, list[KnowledgeChunk]]` (calls retriever then LLM synthesis) and `list_documents(campaign_id, scope_filter=None) -> list[KnowledgeDocument]`; raise `ProviderUnavailableError` when Ollama is unreachable; return "I couldn't find relevant information…" when no chunks retrieved (FR-011)
- [X] T013 [US1] Wire `on_ask` event handler in `apps/web/pages/gm/knowledge_qa.py` — calls `knowledge.ask_question`, formats answer text + citations as Markdown per contracts/knowledge-qa-ui.md §3 (Sources block: doc title, headline, topic, ≤200-char excerpt, max 5, RRF-ordered); show "The knowledge service is unavailable…" on `ProviderUnavailableError` (FR-012)
- [X] T014 [P] [US1] Wire `on_ask` event handler in `apps/web/pages/player/knowledge_qa.py` — same formatting as GM tab; player role passed so retriever applies `player_visible` filter from the start

**Checkpoint**: With a pre-seeded ChromaDB collection (or fixture-loaded content), both dashboards return cited answers. Unanswerable questions display FR-011 message. Ollama down → FR-012 message. Validate SC-001 (≤30 s).

---

## Phase 4: User Story 2 — Ingest a PDF Rulebook (Priority: P2)

**Goal**: A GM uploads a PDF rulebook; it is converted to Markdown, semantically chunked, enriched, indexed, and becomes queryable.

**Independent Test**: Upload a PDF, wait for ✅ ready status in the doc table, then ask a question from the PDF's content and confirm a cited answer is returned. Validate SC-002 (≤10 min for 200-page PDF).

### Implementation for User Story 2

- [X] T015 [US2] Implement `packages/rag/rag/knowledge/chunker.py` — `MarkdownChunker`: heading-based splitting at `##`/`###` boundaries; table-atomic rule (heading + table = one indivisible chunk); 800-token max (configurable via `KNOWLEDGE_MAX_CHUNK_TOKENS`); overflow splits at blank-line paragraph breaks; 50-token overlap between adjacent chunks (`KNOWLEDGE_CHUNK_OVERLAP_TOKENS`)
- [X] T016 [P] [US2] Implement `packages/rag/rag/knowledge/ingestor.py` — `Ingestor` ABC with `ingest(file_path, doc_id, title, access_level_default) -> list[str]` (returns raw text chunks); `PdfIngestor` uses `pymupdf4llm` for PDF→GFM Markdown conversion with `image_captioner: Callable[[bytes], str] | None` parameter (falls back to `[Figure: page {p}, image {n}]` when `None`); passes Markdown output to `MarkdownChunker`; emits visible warning (not silent failure) for image-only pages per research.md §1
- [X] T017 [US2] Implement `packages/rag/rag/knowledge/pipeline.py` — `IngestionPipeline.run(doc_id, file_path, format, access_level_default)`: (1) calls `Ingestor` to get text chunks, (2) calls `Enricher.enrich_chunk()` per chunk to get `ChunkEnrichment`, (3) applies `access_level_default` override when set, (4) generates deterministic chunk IDs `{doc_id_hex}_{chunk_index:04d}`, (5) upserts chunks into ChromaDB collection; updates `KnowledgeDocument.ingestion_status` to `processing` → `ready` or `failed` with `error_message`; launched via `asyncio.create_task`
- [X] T018 [US2] Add `submit_document`, `check_duplicate`, and `confirm_overwrite` to `apps/web/services/knowledge.py` per contracts/knowledge-qa-ui.md §5; `submit_document` creates `KnowledgeDocument` row with `status="pending"` then dispatches pipeline task; `confirm_overwrite` deletes all ChromaDB chunks prefixed `{doc_id_hex}_`, resets status to `processing`, re-dispatches pipeline; `check_duplicate` queries by `(scope, campaign_id, title)` per data-model.md §1 Constraints
- [X] T019 [US2] Implement GM upload panel event handlers in `apps/web/pages/gm/knowledge_qa.py` — `on_upload` (calls `check_duplicate`, shows ⚠️ warning with confirm/cancel buttons on match or dispatches `submit_document`), `on_confirm_overwrite`, `on_cancel_overwrite`, `on_refresh_docs` (reads `list_documents`), `gr.Timer(value=5)` polling; upload button disabled until file selected; scope auto-updates on file-type change per UI contract
- [X] T020 [US2] Create `harness/knowledge_qa/test_ingestion.py` — evals: (a) MD ingest produces `chunk_count >= 1` with non-empty `headline`, `summary`, `topic`, valid `access_level`; (b) missing `nomic-embed-text` raises `ProviderUnavailableError` (not silent); (c) document with `ingestion_status="processing"` and `updated_at > 15 min` triggers stale warning

**Checkpoint**: Upload a PDF as GM → status shows ⏳ processing → transitions to ✅ ready. Doc table reflects chunk count. Question from PDF content returns cited answer.

---

## Phase 5: User Story 3 — Ingest a Markdown File Directly (Priority: P2)

**Goal**: A GM or player uploads a `.md` file; it skips PDF conversion and enters the RAG pipeline directly (chunking → enrichment → indexing). Players are restricted to `.md` only.

**Independent Test**: Upload a hand-written `.md` lore file as a player. Confirm it appears in the doc table as ✅ ready and a question about its content returns a cited answer. Validate SC-003 (≤2 min).

### Implementation for User Story 3

- [X] T021 [US3] Add `MarkdownIngestor` to `packages/rag/rag/knowledge/ingestor.py` — reads `.md` file directly, passes text to `MarkdownChunker`; no PDF conversion step; handles empty/malformed Markdown gracefully (FR-012 visible error, not silent failure)
- [X] T022 [US3] Implement player upload panel event handlers in `apps/web/pages/player/knowledge_qa.py` — `on_upload` (player scope always `"campaign"`, no PDF option, check_duplicate, confirm/cancel flow), `on_confirm_overwrite`, `on_cancel_overwrite`, `on_refresh_docs` (shows only this player's documents), `gr.Timer(value=5)`; `file_types=[".md"]` enforced on `gr.File` component

**Checkpoint**: Player uploads `.md` file → status ⏳ → ✅ ready within 2 min. Player cannot select PDF files (file picker rejects non-`.md` input). GM can upload both PDF and MD.

---

## Phase 6: User Story 4 — Access-Controlled Answers (Priority: P3)

**Goal**: Player queries only surface `player_visible` chunks. GM queries surface all content. Document-level `access_level_default` overrides LLM-inferred per-chunk access level.

**Independent Test**: Ingest `sample_gm_only.md` (from T003) with access `GM-only`. As player, ask a question only that content can answer → confirm zero citations returned and "no relevant information" message. As GM, ask same question → confirm GM-only chunk cited.

### Implementation for User Story 4

- [X] T023 [US4] Apply `access_level_default` override in `packages/rag/rag/knowledge/pipeline.py` — after `ChunkEnrichment` is returned, if `doc.access_level_default` is not `None`, replace `enrichment.access_level` with `doc.access_level_default` before storing the chunk metadata in ChromaDB
- [X] T024 [US4] Apply role-based `where` filter in `packages/rag/rag/knowledge/retriever.py` — when `role == "player"`, add `where={"access_level": {"$eq": "player_visible"}}` to all ChromaDB queries across both `knowledge_global` and `knowledge_{campaign_id_hex}` collections; GM role passes no filter (all chunks visible)
- [X] T025 [US4] Create `harness/knowledge_qa/test_retrieval.py` — evals: (a) player query returns 0 chunks for GM-only content (SC-005 zero leakage); (b) directly relevant chunk appears in top-3 for a targeted question (RRF ranking); (c) empty knowledge base returns "couldn't find" phrase with 0 citations (FR-011)

**Checkpoint**: Run `harness/knowledge_qa/test_retrieval.py` — all three evals pass. SC-005 confirmed: zero GM-only leakage to players.

---

## Phase 7: User Story 5 — Source Navigation (Priority: P3)

**Goal**: After an answer is returned, each citation shows document name, section heading/topic label, and a readable excerpt so users can verify accuracy or read further context.

**Independent Test**: Ask any question that yields a result. Confirm every citation in the response shows: doc title, headline, topic label in parentheses, and an excerpt ≤200 characters. Confirm citations are ordered highest RRF score first, with at most 5 shown.

### Implementation for User Story 5

- [X] T026 [US5] Refine citation rendering in both `apps/web/pages/gm/knowledge_qa.py` and `apps/web/pages/player/knowledge_qa.py` — format each `KnowledgeChunk` as the Sources block defined in contracts/knowledge-qa-ui.md §3: `> **[doc_title] — [headline]** *(topic)*\n> excerpt…`; truncate excerpt at 200 chars with `…`; cap at 5 citations ordered by `rrf_score` descending; include `> **[doc_title] — [headline]** *(topic)*` structure exactly

**Checkpoint**: All acceptance scenarios for US5 verified. Multiple-chunk answers list all contributing sources ranked by relevance.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Environment configuration, stale detection, README update, and final validation.

- [X] T027 [P] Read all knowledge env vars from environment throughout `packages/rag/rag/knowledge/` — `OLLAMA_BASE_URL`, `KNOWLEDGE_EMBED_MODEL` (default `nomic-embed-text`), `KNOWLEDGE_LLM_MODEL` (default `llama3.1`), `KNOWLEDGE_MAX_CHUNK_TOKENS` (default `800`), `KNOWLEDGE_CHUNK_OVERLAP_TOKENS` (default `50`), `KNOWLEDGE_TOP_K` (default `8`), `KNOWLEDGE_RRF_K` (default `60`), `KNOWLEDGE_EXPANSION_COUNT` (default `3`) per quickstart.md §Environment Variables
- [X] T028 [P] Implement stale processing detection in `apps/web/pages/gm/knowledge_qa.py` and `apps/web/pages/player/knowledge_qa.py` — in `on_refresh_docs`, if any document row has `ingestion_status="processing"` and `updated_at > 15 minutes ago`, display ⚠️ "Ingestion stalled — restart may be required." in that row's status cell per data-model.md §1 State Transitions and quickstart.md §Stale detection
- [X] T029 Update `README.md` to reflect the Knowledge Q&A feature as implemented — add setup steps (`ollama pull nomic-embed-text`, `ollama pull llama3.1`, `uv run alembic upgrade head`), document the two-tier collection topology, list the new Knowledge Q&A tabs, and note MVP limitations (no document deletion, no scanned PDF support)

---

---

## Phase 9: Bug Fixes & Documentation Sync

**Purpose**: Fix two CRITICAL bugs discovered during `/speckit-analyze` (pipeline enrichment overloading Ollama, and silent DB status failures masking errors), enforce Principle VII on all error paths, and sync plan/research/data-model/quickstart docs to reflect the actual implementation (embedder.py, vector_store.py, LLM re-ranking, batch enrichment, chunks_processed column).

**⚠️ CRITICAL**: T030–T032 fix active bugs that cause PDF ingestion to appear broken. Resolve before any further feature work.

### Code Fixes

- [X] T030 Fix concurrent enrichment overloading Ollama in `packages/rag/rag/knowledge/pipeline.py` — in `_enrich_with_progress`, replace `asyncio.gather(*[_run_batch(b) for b in batches])` with a sequential loop: `for batch in batches: results.extend(await _run_batch(batch))`. This prevents all enrichment batches from firing simultaneously against a single Ollama instance, which causes timeouts and "unknown error" failures for large PDFs.

- [X] T031 *(Verified — no fix needed)* `async with await _backend.get_session()` pattern audited: `SQLiteBackend.get_session()` is `async def` returning `AsyncSession`; `AsyncSession` implements `__aenter__`/`__aexit__`, so the double-await pattern is correct. No code change required.

- [X] T032 [P] Fix error opacity in `packages/rag/rag/knowledge/pipeline.py` — replaced bare `str(exc)` with `f"{type(exc).__name__}: {exc}"` in both exception handlers. Replaced `except Exception: pass` in `_set_status` and `_set_progress` with `except Exception as _e: _log.warning(...)`. Added `import logging` and `_log = logging.getLogger(__name__)`. Also removed dead `import fitz` from `PdfIngestor.ingest()` (it was imported but only used inside `_inline_image_captions`).

### Documentation Sync

- [X] T033 [P] Updated `specs/005-rag-qa-system/research.md` — §7 now documents two-pass re-ranking (RRF → LLM re-rank via `ChunkEnricher.rerank()`); cross-encoder re-rankers remain deferred. New §11 documents `OllamaEmbedFn` decision (ChromaDB API instability rationale, urllib.request approach, split-embed consistency requirement).

- [X] T034 [P] Updated `specs/005-rag-qa-system/data-model.md` — added `chunks_processed` column to `KnowledgeDocument` schema. Migration gap confirmed and already resolved: `packages/core/core/migrations/versions/0006_knowledge_progress.py` adds the column via `batch_alter_table` (correct for SQLite).

- [X] T035 [P] Updated `specs/005-rag-qa-system/quickstart.md` — added `KNOWLEDGE_ENRICH_MODEL` (default `llama3.2`) and `KNOWLEDGE_ENRICH_BATCH_SIZE` (default `5`) to the Environment Variables table.

- [X] T036 Rewrite `packages/rag/rag/knowledge/pipeline.py` — replace the four sequential phases (extract ALL → enrich ALL → embed ALL → store ALL) with an incremental batch loop: extract all chunks once, then for each batch of `KNOWLEDGE_ENRICH_BATCH_SIZE` chunks run enrich → embed → upsert → persist progress. Fixes HTTP 400 from Ollama's `/api/embed` on large payloads (each embed request now carries ≤5 texts). Adds `chunk_offset` parameter to `_build_records` to keep chunk IDs globally deterministic across batches. Removes `_enrich_with_progress` (now inline). Decision documented in `docs/adr/ADR-007-incremental-batch-ingestion-pipeline.md`. Updated `plan.md §Ingestion Pipeline Design` to describe the new loop structure and reference ADR-007.

---

## Phase 10: Integration Tests — Live Ollama (SC-004, SC-008)

**Purpose**: Implement the three live-Ollama integration tests designed in `plan.md §Phase 10` and the SC-004 five-question fixture battery. These replace informal manual spot-checks with deterministic, auto-skippable assertions (SC-008: skip when Ollama unreachable, required gate when Ollama is available).

**Independent Test**: `uv run pytest harness/knowledge_qa/test_integration.py -v` — all 4 test classes pass when Ollama is running with `nomic-embed-text` and a text LLM; all 4 auto-skip when Ollama is unreachable.

### Implementation for Phase 10

- [X] T037 Add `chroma_path: str | None = None` parameter to `IngestionPipeline.__init__` in `packages/rag/rag/knowledge/pipeline.py` — use `ChromaVectorStore(chroma_path)` when provided, fall back to `ChromaVectorStore()` when `None`; mirrors the existing `ChromaKnowledgeRetriever` pattern and is required so integration tests can direct all writes to a temp directory without touching `./data/chroma`

- [X] T038 [P] Implement module-level test fixtures in `harness/knowledge_qa/test_integration.py` — three `pytest.fixture(scope="module")` fixtures: (1) `ollama_available`: calls `urllib.request.urlopen` on `{OLLAMA_BASE_URL}/api/tags`; issues `pytest.skip("Ollama not reachable …")` if it raises, so the entire module skips cleanly; (2) `tmp_chroma`: returns `str(tmp_path_factory.mktemp("chroma"))` — a fresh temp directory per test session; (3) `ingested_doc_id`: returns `str(uuid.uuid4())` for the test document row

- [X] T039 Implement `TestIngestionFlow.test_md_to_chunks_to_db` in `harness/knowledge_qa/test_integration.py` — depends on `ollama_available`, `tmp_chroma`, `ingested_doc_id`; patches `IngestionPipeline._get_doc_title` (returns `"Sample Rules"`), `_set_status`, and `_set_progress` with `AsyncMock` stubs so no real SQLite is needed; runs `IngestionPipeline(chroma_path=tmp_chroma).run(doc_id=ingested_doc_id, file_path=str(SAMPLE_RULES), format="markdown", access_level_default=None, scope="global", campaign_id=None)`; asserts: `collection.count() >= 1`, every fetched chunk metadata contains keys `doc_id`, `doc_title`, `headline`, `summary`, `topic`, `access_level`, `original_text`, and `access_level` is one of `{"gm_only", "player_visible"}`

- [X] T040 [P] Implement `TestRetrievalFlow.test_query_returns_relevant_chunks` in `harness/knowledge_qa/test_integration.py` — depends on `ollama_available`, `tmp_chroma` (same session as T039, so data is already ingested); creates `ChromaKnowledgeRetriever(chroma_path=tmp_chroma)` and calls `await retriever.search(query="How does combat initiative work?", campaign_id="test", role="gm", top_k=4)`; asserts: `len(chunks) >= 1`, `chunks[0].rrf_score > 0`, `"dex" in chunks[0].text.lower()` (oracle phrase from `sample_rules.md`)

- [X] T041 [P] Implement `TestEndToEndQA.test_llm_synthesises_answer` in `harness/knowledge_qa/test_integration.py` — depends on `ollama_available`, `tmp_chroma`, `ingested_doc_id` (same session); patches `services.knowledge.ChromaKnowledgeRetriever` to use `chroma_path=tmp_chroma` by patching its constructor call with `partial(ChromaKnowledgeRetriever, chroma_path=tmp_chroma)`; calls `await ask_question("What step is used for initiative?", campaign_id=uuid.uuid4(), role="gm")`; asserts: `len(answer) > 0`, `"couldn't find" not in answer.lower()`, `len(chunks) >= 1`, `chunks[0].doc_title` is not empty

- [X] T042 [P] Implement `TestFixtureBattery.test_sc004_four_of_five_questions_cited` in `harness/knowledge_qa/test_integration.py` — SC-004 automated criterion; depends on `ollama_available`, `tmp_chroma`; runs these 5 questions via `ChromaKnowledgeRetriever(chroma_path=tmp_chroma).search(...)`: `["How does combat initiative work?", "What is a Talent?", "How do you use a Talent?", "What are Difficulty Numbers?", "How does Karma work?"]`; counts how many return `len(chunks) >= 1`; asserts `cited_count >= 4` (`≥4 of 5` per SC-004)

**Checkpoint**: Run `uv run pytest harness/knowledge_qa/test_integration.py -v` with Ollama running. Expected: 4 test classes pass in 30–120 s. Without Ollama: 4 classes skipped. Both outcomes are a pass for CI.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 — BLOCKS all user stories
- **US1 (Phase 3)**: Depends on Phase 2 — no dependency on US2, US3, US4, US5
- **US2 (Phase 4)**: Depends on Phase 2 — no dependency on US1 (can develop in parallel with US1)
- **US3 (Phase 5)**: Depends on US2 (Phase 4) — MarkdownIngestor reuses chunker and pipeline from US2
- **US4 (Phase 6)**: Depends on US1 (retriever), US2/US3 (ingestion pipeline) — access filter and override build on both
- **US5 (Phase 7)**: Depends on US1 (on_ask handler exists and returns KnowledgeChunk list)
- **Polish (Phase 8)**: Depends on all user story phases complete
- **Integration Tests (Phase 10)**: Depends on Phase 9 complete — T037 (pipeline change) must land before T038–T042 (tests consume it)

### User Story Dependencies

- **US1 (P1)**: Can start after Foundational — independently testable with pre-seeded fixture data
- **US2 (P2)**: Can start after Foundational — independently testable (chunker + pipeline + upload UI)
- **US3 (P2)**: Depends on US2 (reuses chunker, pipeline, service functions) — independently testable
- **US4 (P3)**: Depends on US1 (retriever must exist) and US2/US3 (pipeline must apply override) — independently testable via harness
- **US5 (P3)**: Depends on US1 (on_ask must return KnowledgeChunk list with rrf_score) — refinement only

### Within Each Phase

- T004 (model) must complete before T005 (migration)
- T006, T007, T008 can all start in parallel once T004+T005 are done
- T009 depends on T007 and T008
- T010, T011 can start in parallel (different files) within Phase 3
- T015, T016 can start in parallel within Phase 4
- T013, T014 can start in parallel within Phase 3 (once T012 is done)
- T027, T028 can run in parallel in Phase 8

---

## Parallel Execution Examples

### Phase 2: Foundational

```
Sequential:  T004 → T005
Then parallel: T006 || T007 || T008
Then:        T009 (depends on T007 + T008)
```

### Phase 3: User Story 1 (MVP)

```
Sequential:  T010 → T011 → T012
Then parallel: T013 || T014
```

### Phase 4: User Story 2

```
Parallel:    T015 || T016
Then:        T017 (depends on T015 + T016)
Then:        T018 (depends on T017)
Then:        T019 (depends on T018)
Then:        T020 (harness, depends on T017)
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (migration, interfaces, placeholder tabs)
3. Complete Phase 3: User Story 1 (retriever, enricher for query expansion, ask service, on_ask handler)
4. **STOP and VALIDATE**: Load fixture data into ChromaDB directly, ask questions, confirm citations and SC-001 (≤30 s)
5. Demo with pre-seeded content

### Incremental Delivery

1. Phase 1 + Phase 2 → App launches with visible placeholder tabs
2. Phase 3 (US1) → Q&A loop works with pre-seeded content (MVP demo-able)
3. Phase 4 (US2) → GMs can upload PDFs; SC-002 validated
4. Phase 5 (US3) → Players can upload MD files; SC-003 validated
5. Phase 6 (US4) → Access control harness passes; SC-005 confirmed
6. Phase 7 (US5) → Citation display polished
7. Phase 8 → Env vars, stale detection, README updated

### Parallel Team Strategy

After Phase 2 completes:
- Developer A: US1 (Phase 3) — retriever, enricher, ask handler
- Developer B: US2 (Phase 4) — chunker, ingestor, pipeline, GM upload UI
- Developer C: US5 polish (Phase 7) — can design citation rendering format independently

---

## Notes

- **[P]** tasks operate on different files; verify before running in parallel that no incomplete task writes to the same file
- **[Story]** label maps every task back to its user story for traceability to spec.md acceptance criteria
- No pytest unit tests are generated (not requested); harness evals (T020, T025, T038–T042) satisfy Principle V
- Phase 10 tests (T038–T042) all auto-skip when Ollama is unreachable — this is NOT a failure (SC-008 skip semantics)
- T039 must run before T040–T042 within a test session because they share module-scoped fixtures and depend on ingested data
- Placeholder-first (T007, T008, T009) satisfies Principle VII — app must be navigable after Phase 2
- All error paths in UI-facing code MUST surface a descriptive Gradio message; `except: pass` is prohibited per constitution §VII
- `confirm_overwrite` flow (FR-009b) is part of both T019 (GM) and T022 (player)
- ChromaDB collections are created lazily on first use by `ChromaKnowledgeRetriever` — no migration needed for vector store
