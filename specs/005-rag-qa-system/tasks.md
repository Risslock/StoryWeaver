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

- [ ] T001 Add `pymupdf4llm` and `pydantic-ai` to `packages/rag/pyproject.toml` dependencies
- [ ] T002 Create `packages/rag/rag/knowledge/` sub-module: `__init__.py` for all files listed in plan.md (interface.py, enricher.py, chunker.py, ingestor.py, pipeline.py, retriever.py — stubs only)
- [ ] T003 [P] Create `harness/knowledge_qa/fixtures/` directory with `sample_rules.md` (plain rules text) and `sample_gm_only.md` (GM-only lore block) fixture files for harness evals

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before any user story can be implemented.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [ ] T004 Add `KnowledgeDocument` SQLAlchemy ORM model (with `UniqueConstraint`, `campaign` relationship, and all columns per data-model.md §1) to `packages/core/core/models.py`
- [ ] T005 Write Alembic migration `packages/core/core/migrations/versions/0005_knowledge_documents.py` — creates `knowledge_documents` table with `uq_knowledge_doc_title` constraint and indexes on `campaign_id` and `ingestion_status`
- [ ] T006 [P] Define `packages/rag/rag/knowledge/interface.py` — `KnowledgeRetriever` ABC, `KnowledgeChunk` dataclass, `ChunkEnrichment` Pydantic model, `QueryExpansion` Pydantic model exactly as specified in data-model.md §3 and plan.md §Structured Output Pattern
- [ ] T007 [P] Create placeholder `apps/web/pages/gm/knowledge_qa.py` — all Gradio components wired (chatbot, input, file upload, scope/access dropdowns, doc table, timer) per contracts/knowledge-qa-ui.md §1; chatbot initial message: "Knowledge Q&A — not yet implemented"
- [ ] T008 [P] Create placeholder `apps/web/pages/player/knowledge_qa.py` — all Gradio components wired per contracts/knowledge-qa-ui.md §2; chatbot initial message: "Knowledge Q&A — not yet implemented"; file input restricted to `file_types=[".md"]`
- [ ] T009 Register both Knowledge Q&A tabs in `apps/web/app.py` inside `gr.Tabs(elem_id="gm-tabs")` and `gr.Tabs(elem_id="player-tabs")` so the app launches and navigates to both tabs

**Checkpoint**: Run `uv run alembic upgrade head` (migration succeeds) and `uv run python apps/web/main.py` (both placeholder tabs visible and app navigable).

---

## Phase 3: User Story 1 — Ask a Game Question (Priority: P1) 🎯 MVP

**Goal**: A player or GM can type a natural-language question and receive a synthesized answer with at least one source citation drawn from pre-seeded knowledge base content.

**Independent Test**: With at least one document already indexed in ChromaDB (loaded via fixture or manual seeding), ask "How does combat initiative work?" and confirm a cited answer appears within 30 seconds.

### Implementation for User Story 1

- [ ] T010 [US1] Implement `packages/rag/rag/knowledge/enricher.py` — pydantic-ai `Agent` with `result_type=QueryExpansion` for multi-query expansion (3 alternatives) and `result_type=ChunkEnrichment` for chunk enrichment; use `LLMProvider` abstraction per plan.md §Structured Output Pattern; fallback on `ValidationError` as described
- [ ] T011 [US1] Implement `packages/rag/rag/knowledge/retriever.py` — `ChromaKnowledgeRetriever` implementing `KnowledgeRetriever` ABC: creates `knowledge_global` and `knowledge_{campaign_id_hex}` collections with `OllamaEmbeddingFunction(model_name=KNOWLEDGE_EMBED_MODEL, url=OLLAMA_BASE_URL)`, runs multi-query retrieval across both collections, applies RRF with k=60 (formula: `Σ 1/(k+rank_i)`), returns top-K `KnowledgeChunk` list sorted by `rrf_score` descending
- [ ] T012 [US1] Create `apps/web/services/knowledge.py` — implement `ask_question(question, campaign_id, role) -> tuple[str, list[KnowledgeChunk]]` (calls retriever then LLM synthesis) and `list_documents(campaign_id, scope_filter=None) -> list[KnowledgeDocument]`; raise `ProviderUnavailableError` when Ollama is unreachable; return "I couldn't find relevant information…" when no chunks retrieved (FR-011)
- [ ] T013 [US1] Wire `on_ask` event handler in `apps/web/pages/gm/knowledge_qa.py` — calls `knowledge.ask_question`, formats answer text + citations as Markdown per contracts/knowledge-qa-ui.md §3 (Sources block: doc title, headline, topic, ≤200-char excerpt, max 5, RRF-ordered); show "The knowledge service is unavailable…" on `ProviderUnavailableError` (FR-012)
- [ ] T014 [P] [US1] Wire `on_ask` event handler in `apps/web/pages/player/knowledge_qa.py` — same formatting as GM tab; player role passed so retriever applies `player_visible` filter from the start

**Checkpoint**: With a pre-seeded ChromaDB collection (or fixture-loaded content), both dashboards return cited answers. Unanswerable questions display FR-011 message. Ollama down → FR-012 message. Validate SC-001 (≤30 s).

---

## Phase 4: User Story 2 — Ingest a PDF Rulebook (Priority: P2)

**Goal**: A GM uploads a PDF rulebook; it is converted to Markdown, semantically chunked, enriched, indexed, and becomes queryable.

**Independent Test**: Upload a PDF, wait for ✅ ready status in the doc table, then ask a question from the PDF's content and confirm a cited answer is returned. Validate SC-002 (≤10 min for 200-page PDF).

### Implementation for User Story 2

- [ ] T015 [US2] Implement `packages/rag/rag/knowledge/chunker.py` — `MarkdownChunker`: heading-based splitting at `##`/`###` boundaries; table-atomic rule (heading + table = one indivisible chunk); 800-token max (configurable via `KNOWLEDGE_MAX_CHUNK_TOKENS`); overflow splits at blank-line paragraph breaks; 50-token overlap between adjacent chunks (`KNOWLEDGE_CHUNK_OVERLAP_TOKENS`)
- [ ] T016 [P] [US2] Implement `packages/rag/rag/knowledge/ingestor.py` — `Ingestor` ABC with `ingest(file_path, doc_id, title, access_level_default) -> list[str]` (returns raw text chunks); `PdfIngestor` uses `pymupdf4llm` for PDF→GFM Markdown conversion with `image_captioner: Callable[[bytes], str] | None` parameter (falls back to `[Figure: page {p}, image {n}]` when `None`); passes Markdown output to `MarkdownChunker`; emits visible warning (not silent failure) for image-only pages per research.md §1
- [ ] T017 [US2] Implement `packages/rag/rag/knowledge/pipeline.py` — `IngestionPipeline.run(doc_id, file_path, format, access_level_default)`: (1) calls `Ingestor` to get text chunks, (2) calls `Enricher.enrich_chunk()` per chunk to get `ChunkEnrichment`, (3) applies `access_level_default` override when set, (4) generates deterministic chunk IDs `{doc_id_hex}_{chunk_index:04d}`, (5) upserts chunks into ChromaDB collection; updates `KnowledgeDocument.ingestion_status` to `processing` → `ready` or `failed` with `error_message`; launched via `asyncio.create_task`
- [ ] T018 [US2] Add `submit_document`, `check_duplicate`, and `confirm_overwrite` to `apps/web/services/knowledge.py` per contracts/knowledge-qa-ui.md §5; `submit_document` creates `KnowledgeDocument` row with `status="pending"` then dispatches pipeline task; `confirm_overwrite` deletes all ChromaDB chunks prefixed `{doc_id_hex}_`, resets status to `processing`, re-dispatches pipeline; `check_duplicate` queries by `(scope, campaign_id, title)` per data-model.md §1 Constraints
- [ ] T019 [US2] Implement GM upload panel event handlers in `apps/web/pages/gm/knowledge_qa.py` — `on_upload` (calls `check_duplicate`, shows ⚠️ warning with confirm/cancel buttons on match or dispatches `submit_document`), `on_confirm_overwrite`, `on_cancel_overwrite`, `on_refresh_docs` (reads `list_documents`), `gr.Timer(value=5)` polling; upload button disabled until file selected; scope auto-updates on file-type change per UI contract
- [ ] T020 [US2] Create `harness/knowledge_qa/test_ingestion.py` — evals: (a) MD ingest produces `chunk_count >= 1` with non-empty `headline`, `summary`, `topic`, valid `access_level`; (b) missing `nomic-embed-text` raises `ProviderUnavailableError` (not silent); (c) document with `ingestion_status="processing"` and `updated_at > 15 min` triggers stale warning

**Checkpoint**: Upload a PDF as GM → status shows ⏳ processing → transitions to ✅ ready. Doc table reflects chunk count. Question from PDF content returns cited answer.

---

## Phase 5: User Story 3 — Ingest a Markdown File Directly (Priority: P2)

**Goal**: A GM or player uploads a `.md` file; it skips PDF conversion and enters the RAG pipeline directly (chunking → enrichment → indexing). Players are restricted to `.md` only.

**Independent Test**: Upload a hand-written `.md` lore file as a player. Confirm it appears in the doc table as ✅ ready and a question about its content returns a cited answer. Validate SC-003 (≤2 min).

### Implementation for User Story 3

- [ ] T021 [US3] Add `MarkdownIngestor` to `packages/rag/rag/knowledge/ingestor.py` — reads `.md` file directly, passes text to `MarkdownChunker`; no PDF conversion step; handles empty/malformed Markdown gracefully (FR-012 visible error, not silent failure)
- [ ] T022 [US3] Implement player upload panel event handlers in `apps/web/pages/player/knowledge_qa.py` — `on_upload` (player scope always `"campaign"`, no PDF option, check_duplicate, confirm/cancel flow), `on_confirm_overwrite`, `on_cancel_overwrite`, `on_refresh_docs` (shows only this player's documents), `gr.Timer(value=5)`; `file_types=[".md"]` enforced on `gr.File` component

**Checkpoint**: Player uploads `.md` file → status ⏳ → ✅ ready within 2 min. Player cannot select PDF files (file picker rejects non-`.md` input). GM can upload both PDF and MD.

---

## Phase 6: User Story 4 — Access-Controlled Answers (Priority: P3)

**Goal**: Player queries only surface `player_visible` chunks. GM queries surface all content. Document-level `access_level_default` overrides LLM-inferred per-chunk access level.

**Independent Test**: Ingest `sample_gm_only.md` (from T003) with access `GM-only`. As player, ask a question only that content can answer → confirm zero citations returned and "no relevant information" message. As GM, ask same question → confirm GM-only chunk cited.

### Implementation for User Story 4

- [ ] T023 [US4] Apply `access_level_default` override in `packages/rag/rag/knowledge/pipeline.py` — after `ChunkEnrichment` is returned, if `doc.access_level_default` is not `None`, replace `enrichment.access_level` with `doc.access_level_default` before storing the chunk metadata in ChromaDB
- [ ] T024 [US4] Apply role-based `where` filter in `packages/rag/rag/knowledge/retriever.py` — when `role == "player"`, add `where={"access_level": {"$eq": "player_visible"}}` to all ChromaDB queries across both `knowledge_global` and `knowledge_{campaign_id_hex}` collections; GM role passes no filter (all chunks visible)
- [ ] T025 [US4] Create `harness/knowledge_qa/test_retrieval.py` — evals: (a) player query returns 0 chunks for GM-only content (SC-005 zero leakage); (b) directly relevant chunk appears in top-3 for a targeted question (RRF ranking); (c) empty knowledge base returns "couldn't find" phrase with 0 citations (FR-011)

**Checkpoint**: Run `harness/knowledge_qa/test_retrieval.py` — all three evals pass. SC-005 confirmed: zero GM-only leakage to players.

---

## Phase 7: User Story 5 — Source Navigation (Priority: P3)

**Goal**: After an answer is returned, each citation shows document name, section heading/topic label, and a readable excerpt so users can verify accuracy or read further context.

**Independent Test**: Ask any question that yields a result. Confirm every citation in the response shows: doc title, headline, topic label in parentheses, and an excerpt ≤200 characters. Confirm citations are ordered highest RRF score first, with at most 5 shown.

### Implementation for User Story 5

- [ ] T026 [US5] Refine citation rendering in both `apps/web/pages/gm/knowledge_qa.py` and `apps/web/pages/player/knowledge_qa.py` — format each `KnowledgeChunk` as the Sources block defined in contracts/knowledge-qa-ui.md §3: `> **[doc_title] — [headline]** *(topic)*\n> excerpt…`; truncate excerpt at 200 chars with `…`; cap at 5 citations ordered by `rrf_score` descending; include `> **[doc_title] — [headline]** *(topic)*` structure exactly

**Checkpoint**: All acceptance scenarios for US5 verified. Multiple-chunk answers list all contributing sources ranked by relevance.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Environment configuration, stale detection, README update, and final validation.

- [ ] T027 [P] Read all knowledge env vars from environment throughout `packages/rag/rag/knowledge/` — `OLLAMA_BASE_URL`, `KNOWLEDGE_EMBED_MODEL` (default `nomic-embed-text`), `KNOWLEDGE_LLM_MODEL` (default `llama3.1`), `KNOWLEDGE_MAX_CHUNK_TOKENS` (default `800`), `KNOWLEDGE_CHUNK_OVERLAP_TOKENS` (default `50`), `KNOWLEDGE_TOP_K` (default `8`), `KNOWLEDGE_RRF_K` (default `60`), `KNOWLEDGE_EXPANSION_COUNT` (default `3`) per quickstart.md §Environment Variables
- [ ] T028 [P] Implement stale processing detection in `apps/web/pages/gm/knowledge_qa.py` and `apps/web/pages/player/knowledge_qa.py` — in `on_refresh_docs`, if any document row has `ingestion_status="processing"` and `updated_at > 15 minutes ago`, display ⚠️ "Ingestion stalled — restart may be required." in that row's status cell per data-model.md §1 State Transitions and quickstart.md §Stale detection
- [ ] T029 Update `README.md` to reflect the Knowledge Q&A feature as implemented — add setup steps (`ollama pull nomic-embed-text`, `ollama pull llama3.1`, `uv run alembic upgrade head`), document the two-tier collection topology, list the new Knowledge Q&A tabs, and note MVP limitations (no document deletion, no scanned PDF support)

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
- No pytest unit tests are generated (not requested); harness evals (T020, T025) satisfy Principle V
- Placeholder-first (T007, T008, T009) satisfies Principle VII — app must be navigable after Phase 2
- All error paths in UI-facing code MUST surface a descriptive Gradio message; `except: pass` is prohibited per constitution §VII
- `confirm_overwrite` flow (FR-009b) is part of both T019 (GM) and T022 (player)
- ChromaDB collections are created lazily on first use by `ChromaKnowledgeRetriever` — no migration needed for vector store
