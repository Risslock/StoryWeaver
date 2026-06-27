---
description: "Implementation tasks for the Docling ingestion pipeline adoption"
---

# Tasks: Docling Ingestion Pipeline (012)

**Input**: Design documents from `/specs/012-docling-pipeline/`

**Branch**: `012-docling-pipeline`

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story. Tests are not included (not explicitly requested in the spec — use `quickstart.md` for manual validation scenarios).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel with other `[P]` tasks in the same phase (different files, no shared dependency)
- **[Story]**: Which user story this task belongs to (US1=P1, US2=P2 breadcrumbs, US3=P3 deprecations, US4=P2 providers)

---

## Phase 1: Setup

**Purpose**: Add new package dependencies and env var scaffolding before any implementation begins.

- [ ] T001 Add `docling>=2.0.0` and `transformers>=4.40` to the `dependencies` list in `packages/rag/pyproject.toml`
- [ ] T002 [P] Verify `httpx` is listed in `packages/rag/pyproject.toml` dependencies (required by `HuggingFaceEmbedFn` in US4); add it if missing

**Checkpoint**: `uv sync` succeeds and `from docling.document_converter import DocumentConverter` imports without error.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core primitives that both US1 and US4 depend on. Must complete before any user story begins.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [ ] T003 Create `DoclingChunker` class in `packages/rag/rag/knowledge/docling_chunker.py` — constructor accepts `tokenizer_name: str` (default `"nomic-ai/nomic-embed-text-v1.5"`) and `max_tokens: int` (default `512`); constructor builds `self._tokenizer = AutoTokenizer.from_pretrained(tokenizer_name)` and `self._chunker = HybridChunker(tokenizer=self._tokenizer, max_tokens=max_tokens)`; `chunk(document: DoclingDocument) -> list[tuple[str, list[str]]]` iterates chunk objects and returns `[(chunk.text, list(chunk.meta.headings or [])) for chunk in self._chunker.chunk(document)]`; imports: `from docling.chunking import HybridChunker` and `from transformers import AutoTokenizer`
- [ ] T004 [P] Add `"docling"` as a valid value for `extraction_mode` in `IngestionConfig` in `packages/rag/rag/knowledge/interface.py` — update the field's type annotation or docstring to reflect `"text" | "vision" | "docling"`

**Checkpoint**: `DoclingChunker("nomic-ai/nomic-embed-text-v1.5").chunk(doc)` returns a list of `(str, list[str])` tuples without error.

---

## Phase 3: User Story 1 — Docling Re-ingestion Pipeline (Priority: P1) 🎯 MVP

**Goal**: A developer can re-ingest ED4_Players_Guide using `extraction_mode="docling"` and get zero image placeholders, zero furniture lines, coherent structured tables, ≥96.7% breadcrumb coverage, and ~30× faster ingestion compared to the pymupdf4llm baseline.

**Independent Test**: Set `extraction_mode="docling"` in `IngestionConfig`, run `IngestionPipeline.run()` on a test PDF, inspect ChromaDB collection via the quickstart Scenario A checks (SC-001 through SC-008).

### Implementation

- [ ] T005 [US1] Implement `DoclingIngestor` class in `packages/rag/rag/knowledge/ingestor.py` with method `async extract(file_path: str, config: IngestionConfig) -> tuple[str, list[str], list[str]]`; page-batch loop reads `KNOWLEDGE_DOCLING_PAGE_BATCH_SIZE` env var (default `10`); each batch calls `converter.convert(str(file_path), page_range=(batch_start, batch_end), raises_on_error=False)`; if `result.errors` is non-empty, log `ERROR` and raise `IngestionAbortError`; use a single `DoclingChunker` instance (constructed once before the loop); concatenate all `(body, headings)` pairs across batches; assemble `breadcrumb` per chunk by calling `_strip_heading(h)` on each entry then joining with `" > "` (empty `headings` → `""`); export `full_text` as `result.document.export_to_markdown()` from the last batch (or `""` if only logging is needed); return `(full_text, body_chunks, breadcrumbs)`; the converter must be configured with `PdfPipelineOptions(do_ocr=False, generate_page_images=False)`. Add private helper `_strip_heading(h: str) -> str` that strips `*`, `_`, `#`, and `` ` `` characters.

- [ ] T006 [US1] Wire `DoclingIngestor` into `IngestionPipeline._extract()` in `packages/rag/rag/knowledge/pipeline.py` — add a new branch **before** the existing `if format == "pdf":` check: `if format == "pdf" and config.extraction_mode == "docling": from rag.knowledge.ingestor import DoclingIngestor; return await DoclingIngestor().extract(file_path, config)`. Change `_extract()` return type to `tuple[str, list[str]] | tuple[str, list[str], list[str]]` or use an overloaded approach (see T007 for how the caller handles both shapes).

- [ ] T007 [US1] Update `IngestionPipeline.run()` in `packages/rag/rag/knowledge/pipeline.py` to handle the Docling path — after calling `self._extract()`, detect whether a 3-tuple was returned (docling path) or 2-tuple (legacy path); for the docling path: assign `full_text, chunks, docling_breadcrumbs = result`; set `all_breadcrumbs = docling_breadcrumbs` **instead of** the `BreadcrumbExtractor` block (skip lines 150–154 entirely for this path); for the legacy path: preserve existing behavior unchanged. CorpusCleaner FR-003/FR-004 rules are not called by `DoclingIngestor` (Docling handles furniture at extraction); stat-block detection via CorpusCleaner will run if called from `DoclingIngestor` (see note: verify whether existing PdfIngestor calls CorpusCleaner and mirror that for DoclingIngestor, excluding FR-003/FR-004 rules per FR-002/FR-003 of spec).

**Checkpoint**: Running `IngestionPipeline.run()` with `extraction_mode="docling"` on a test PDF populates ChromaDB with chunks that have `extraction_mode="docling"`, non-empty `breadcrumb` on ≥96% of chunks, and `original_text` in C-effective format. Zero image placeholder lines in any chunk body.

---

## Phase 4: User Story 2 — Breadcrumb-Enriched Chunks (Priority: P2)

**Goal**: Every chunk in ChromaDB carries a `breadcrumb` from `meta.headings` (not from BreadcrumbExtractor). `BreadcrumbExtractor` is marked deprecated and excluded from the active Docling path.

**Independent Test**: After US1 ingestion, inspect 20 random chunks — all have `breadcrumb` key (non-null, possibly empty string); run quickstart Scenario A SC-004 check (≥1392 of 1439 non-empty breadcrumbs).

### Implementation

- [ ] T008 [US2] Deprecate `BreadcrumbExtractor` in `packages/rag/rag/knowledge/breadcrumb.py` — add a module-level docstring at the top of the file: `"""Deprecated since feature 012. BreadcrumbExtractor is superseded by Docling HybridChunker's meta.headings field. See spike PR #19. This module is retained for portfolio continuity only."""`; add a `WARNING`-level log in `BreadcrumbExtractor.__init__` or at the top of `extract()`: `_log.warning("BreadcrumbExtractor is deprecated since feature 012 — use DoclingIngestor breadcrumbs (meta.headings) instead.")`; ensure `_log = logging.getLogger(__name__)` is present (FR-010)

- [ ] T009 [P] [US2] Verify and document C-effective format and edge cases in `packages/rag/rag/knowledge/pipeline.py` `_build_records()` — confirm line 244 `original_text = f"{breadcrumb}\n\n{raw_text}" if breadcrumb else raw_text` is the sole assembly point and matches FR-011 (C-effective when breadcrumb non-empty) and FR-012 (consistent with the stored `breadcrumb` metadata field); add inline comment `# FR-011: C-effective format — heading path prepended when breadcrumb non-empty` if not already present; confirm `breadcrumb` dict entry in `metadatas` (line ~266) is set from the `breadcrumbs` list (not from BreadcrumbExtractor output) for the docling path after T007

**Checkpoint**: `BreadcrumbExtractor().extract(...)` emits a WARNING log. All Docling-ingested chunks have `breadcrumb` in metadata (empty string or non-empty, never absent). SC-008 passes.

---

## Phase 5: User Story 3 — Deprecated Pipeline Code as Portfolio Artifact (Priority: P3)

**Goal**: Every legacy extractor and chunker class is visibly marked deprecated with a reference to feature 012 and spike PR #19. The deprecated code still runs without crashing and emits WARNING logs.

**Independent Test**: Import each deprecated class and call it — observe WARNING log; confirm no exception is raised (SC-009).

### Implementation

- [ ] T010 [P] [US3] Deprecate `PdfIngestor` in `packages/rag/rag/knowledge/ingestor.py` — add a module-level comment block before the class: `# DEPRECATED since feature 012. Superseded by DoclingIngestor. Spike PR #19 showed 30x speed improvement and zero image placeholders with Docling. Retained for portfolio continuity.`; add WARNING log in `PdfIngestor.__init__`: `_log.warning("PdfIngestor is deprecated since feature 012 — use DoclingIngestor instead.")` (FR-013)

- [ ] T011 [P] [US3] Deprecate `HeadingChunker` in `packages/rag/rag/knowledge/chunker.py`, `SemanticChunker` in `packages/rag/rag/knowledge/chunker_semantic.py`, and `AgenticChunker` in `packages/rag/rag/knowledge/chunker_agentic.py` — add the same module-level deprecation comment pattern to each file (`# DEPRECATED since feature 012. Superseded by Docling HybridChunker. Spike PR #19. Retained for portfolio continuity.`) and WARNING log in each class's `__init__` (FR-014/FR-015)

- [ ] T012 [US3] Mark CorpusCleaner FR-003 and FR-004 rules with `# DEPRECATED(012)` inline comments in `packages/rag/rag/knowledge/cleaner.py` — locate the image-placeholder stripping rule (FR-003 from feature 011) and the furniture/page-number stripping rule (FR-004 from feature 011); add `# DEPRECATED(012): Docling handles image placeholders at extraction time — this rule MUST NOT be applied to Docling-extracted content.` and `# DEPRECATED(012): Docling handles furniture (headers, footers, page numbers) at extraction time — this rule MUST NOT be applied to Docling-extracted content.`; rules remain in code as documented dead paths — do not delete them (FR-016)

**Checkpoint**: `from rag.knowledge.ingestor import PdfIngestor; PdfIngestor()` emits a WARNING and doesn't crash. Same for `HeadingChunker`, `SemanticChunker`, `AgenticChunker`. `CorpusCleaner` source has `# DEPRECATED(012)` on both rules.

---

## Phase 6: User Story 4 — Provider-Selectable Ingestion Models (Priority: P2)

**Goal**: Switching between Ollama and HuggingFace for enrichment LLM and embeddings requires only `.env` changes. Missing required env vars abort the pipeline within 1 second with a specific ERROR log. HuggingFace rate-limit errors retry with backoff before surfacing as failures.

**Independent Test**: (a) With `KNOWLEDGE_ENRICH_PROVIDER=ollama` and `KNOWLEDGE_EMBED_PROVIDER=ollama`, run ingestion — succeeds locally. (b) Unset `KNOWLEDGE_ENRICH_MODEL` — pipeline logs ERROR within 1 second and aborts. (c) With `KNOWLEDGE_EMBED_PROVIDER=huggingface` and a valid `HF_API_KEY`, embedding calls go to HF endpoint (verifiable via DEBUG logs). See quickstart Scenarios B, C.

### Implementation

- [ ] T013 [US4] Create `packages/rag/rag/knowledge/factory.py` with `get_knowledge_enrich_provider(model: str) -> LLMProvider` — reads `KNOWLEDGE_ENRICH_PROVIDER` env var (required; `"ollama"` | `"huggingface"`); if absent/blank: `_log.error("KNOWLEDGE_ENRICH_PROVIDER is required (accepted: ollama, huggingface)")` then raise `EnvironmentError`; if unrecognised value: same ERROR pattern; if `"ollama"`: return `OllamaProvider(model=model, base_url=os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"))`; if `"huggingface"`: validate `HF_API_KEY` (absent/blank → `_log.error("HF_API_KEY is required when KNOWLEDGE_ENRICH_PROVIDER=huggingface")`, raise `EnvironmentError`); return `HuggingFaceLLMProvider(api_key=api_key, model=model)`. Also validate `model` is non-blank before any branch: if blank, `_log.error("model is required ...")` and raise. Follow `packages/imagegen/imagegen/factory.py` `get_image_provider()` pattern.

- [ ] T014 [P] [US4] Add `HuggingFaceEmbedFn` class to `packages/rag/rag/knowledge/embedder.py` — constructor: `__init__(self, model: str, api_key: str)`; `name` property returns `f"huggingface_{self._model}"`; `__call__(self, input: list[str]) -> list[list[float]]`: POST to `https://api-inference.huggingface.co/models/{self._model}` with `{"inputs": input}` and `Authorization: Bearer {api_key}` header using `urllib.request` (same pattern as `OllamaEmbedFn`); on HTTP 429, retry with exponential backoff: 3 attempts, delays `[5, 10, 20]` seconds using `time.sleep`; on other HTTP errors, raise `ProviderUnavailableError`; parse response as `json.loads(resp.read())` which returns `list[list[float]]`; `async embed(self, texts: list[str]) -> list[list[float]]`: `return await asyncio.to_thread(self, texts)`

- [ ] T015 [US4] Add `get_knowledge_embed_fn() -> OllamaEmbedFn | HuggingFaceEmbedFn` to `packages/rag/rag/knowledge/factory.py` — reads `KNOWLEDGE_EMBED_PROVIDER` (required, same validation pattern as T013); reads `KNOWLEDGE_EMBED_MODEL` (required, no settings fallback — if absent/blank: `_log.error("KNOWLEDGE_EMBED_MODEL is required but not set")`, raise `EnvironmentError`); if `"ollama"`: return `OllamaEmbedFn(model=model, base_url=os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"))`; if `"huggingface"`: validate `HF_API_KEY` (same pattern); return `HuggingFaceEmbedFn(model=model, api_key=api_key)`

- [ ] T016 [US4] Replace hardcoded `OllamaProvider` and `get_embed_fn()` in `packages/rag/rag/knowledge/pipeline.py` — (a) replace `enrich_model = os.environ.get("KNOWLEDGE_ENRICH_MODEL", settings.knowledge_enrich_model)` with a required read: `enrich_model = os.environ.get("KNOWLEDGE_ENRICH_MODEL", "").strip(); if not enrich_model: _log.error("KNOWLEDGE_ENRICH_MODEL is required but not set"); raise EnvironmentError(...)`; (b) replace `from llm.providers.ollama import OllamaProvider; enricher = ChunkEnricher(OllamaProvider(model=enrich_model))` with `from rag.knowledge.factory import get_knowledge_enrich_provider; enricher = ChunkEnricher(get_knowledge_enrich_provider(enrich_model))`; (c) replace `embed_fn = get_embed_fn()` with `from rag.knowledge.factory import get_knowledge_embed_fn; embed_fn = get_knowledge_embed_fn()`; remove the now-unused `from rag.knowledge.embedder import get_embed_fn` import

- [ ] T017 [US4] Replace hardcoded `OllamaProvider` in `packages/rag/rag/knowledge/retriever.py` — replace `from llm.providers.ollama import OllamaProvider; enricher = ChunkEnricher(OllamaProvider(model=llm_model))` with `from rag.knowledge.factory import get_knowledge_enrich_provider; enricher = ChunkEnricher(get_knowledge_enrich_provider(llm_model))`; also update `_embed_query()` to use `get_knowledge_embed_fn()` from factory instead of `get_embed_fn()` from embedder; remove the now-unused `from rag.knowledge.embedder import get_embed_fn` import

- [ ] T018 [P] [US4] Update `.env.example` — add the Knowledge Pipeline Provider Selection block per `specs/012-docling-pipeline/contracts/ingestion-pipeline.md` section 5: include `KNOWLEDGE_ENRICH_PROVIDER`, `KNOWLEDGE_EMBED_PROVIDER`, `KNOWLEDGE_ENRICH_MODEL`, `KNOWLEDGE_EMBED_MODEL` as required vars with example values; add commented `KNOWLEDGE_DOCLING_PAGE_BATCH_SIZE=10`; add commented HuggingFace configuration block showing `BAAI/bge-m3` as primary HF embed model and `sentence-transformers/all-MiniLM-L6-v2` as confirmed fallback (FR-027)

**Checkpoint**: With `KNOWLEDGE_ENRICH_PROVIDER=ollama`, `KNOWLEDGE_EMBED_PROVIDER=ollama`, `KNOWLEDGE_ENRICH_MODEL=llama3.2`, `KNOWLEDGE_EMBED_MODEL=nomic-ai/nomic-embed-text-v1.5`, ingestion succeeds. Removing `KNOWLEDGE_ENRICH_MODEL` causes ERROR log + immediate abort. `get_knowledge_embed_fn()` returns `OllamaEmbedFn` for ollama provider, `HuggingFaceEmbedFn` for huggingface provider.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: README currency, cleanup of superseded helpers, and final validation.

- [ ] T019 [P] Deprecate `get_embed_fn()` in `packages/rag/rag/knowledge/embedder.py` — this factory function is now superseded by `get_knowledge_embed_fn()` in `factory.py`; after T016 and T017 remove all callers, either delete `get_embed_fn()` if no other callers exist, or replace its body with: `_log.warning("get_embed_fn() is deprecated since feature 012 — use get_knowledge_embed_fn() from rag.knowledge.factory instead."); return get_knowledge_embed_fn()` and add the corresponding import

- [ ] T020 Update `README.md` to reflect the current implemented state after this feature — document: (a) Docling is now the active extraction + chunking engine; (b) four new required env vars (`KNOWLEDGE_ENRICH_PROVIDER`, `KNOWLEDGE_EMBED_PROVIDER`, `KNOWLEDGE_ENRICH_MODEL`, `KNOWLEDGE_EMBED_MODEL`); (c) embedding model options (nomic-v1.5 for Ollama with dim=256, `BAAI/bge-m3` or `all-MiniLM-L6-v2` for HF); (d) note that Docling downloads ~1–2 GB of layout models on first run; (e) legacy extractor/chunker code is preserved but deprecated; per Constitution Principle I (README must reflect current implemented state after each milestone)

**Checkpoint**: `README.md` accurately describes the Docling pipeline. `get_embed_fn()` either removed or emits deprecation WARNING.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Setup (Phase 1) — **BLOCKS all user stories**
- **US1 (Phase 3)**: Depends on Foundational; can start immediately after T003 and T004
- **US2 (Phase 4)**: Depends on US1 being complete (breadcrumbs come from DoclingIngestor)
- **US3 (Phase 5)**: Depends only on Foundational — can proceed in parallel with US1/US2
- **US4 (Phase 6)**: Depends on Foundational; T013 and T014 can start immediately; T016/T017 depend on T013 and T015
- **Polish (Phase 7)**: Depends on all user story phases complete

### User Story Dependencies

- **US1 (P1)**: Start after Phase 2 — no story dependencies
- **US2 (P2)**: Start after US1 (depends on DoclingIngestor being complete)
- **US3 (P3)**: Start after Phase 2 — independent of US1/US2/US4 (pure deprecation markers)
- **US4 (P2)**: Start after Phase 2 — T013/T014/T015/T018 are independent of US1/US2/US3; T016/T017 depend on T013+T015

### Within Phase 6 (US4)

```
T013 (enrich factory) ──┐
                         ├──▶ T016 (pipeline.py wiring)
T015 (embed factory)  ──┘
                         └──▶ T017 (retriever.py wiring)
T014 (HuggingFaceEmbedFn) ──▶ T015
T018 (.env.example) ────── independent [P]
```

---

## Parallel Opportunities

```
# Phase 1 — run together:
T001  Add docling + transformers to pyproject.toml
T002  Verify httpx in pyproject.toml

# Phase 2 — run together:
T003  Create DoclingChunker
T004  Add "docling" to IngestionConfig.extraction_mode

# Phase 3 — sequential (each depends on prior):
T005 → T006 → T007

# Phase 4 + Phase 5 — run together (US2 and US3 only share Phase 2 dependency):
T008  Deprecate BreadcrumbExtractor       (US2)
T009  Verify C-effective in _build_records (US2)
T010  Deprecate PdfIngestor               (US3)
T011  Deprecate chunkers                  (US3)
T012  Mark CorpusCleaner rules deprecated (US3)

# Phase 6 — parallel start, then sequential wiring:
T013  factory.py get_knowledge_enrich_provider   [P start]
T014  HuggingFaceEmbedFn in embedder.py          [P start]
T018  .env.example                               [P independent]
# then after T013 + T014:
T015  get_knowledge_embed_fn in factory.py
# then after T013 + T015:
T016  pipeline.py wiring
T017  retriever.py wiring

# Phase 7 — run together:
T019  Deprecate get_embed_fn()
T020  Update README.md
```

---

## Implementation Strategy

### MVP First (US1 Only — Docling pipeline working locally)

1. Complete Phase 1: Setup (T001–T002)
2. Complete Phase 2: Foundational (T003–T004)
3. Complete Phase 3: US1 (T005–T007)
4. **STOP and VALIDATE**: Run quickstart Scenario A — ingest ED4_Players_Guide with `extraction_mode="docling"` and verify SC-001 through SC-008
5. Merge US1 if all success criteria pass — retrieval quality is working

### Incremental Delivery

1. Phase 1 + 2 → Foundation ready
2. Phase 3 (US1) → Docling pipeline works with Ollama (MVP)
3. Phase 4 (US2) → Breadcrumb deprecation formalized
4. Phase 5 (US3) → Full portfolio-legible deprecation trail
5. Phase 6 (US4) → Provider-selectable pipeline (HuggingFace option enabled)
6. Phase 7 → Polish + README update

### Parallel Execution (if desired)

After Phase 2 completes:
- Track A: US1 (T005 → T006 → T007), then US2 (T008, T009)
- Track B: US3 (T010, T011, T012) — purely additive, no conflicts
- Track C: US4 setup (T013, T014, T018) — no conflicts until T016/T017

---

## Notes

- **[P]** tasks touch different files and have no dependency on incomplete tasks in the same phase — safe to parallelize
- US2 is tightly coupled to US1 (breadcrumbs are produced inside `DoclingIngestor`) — US2 is primarily verification + BreadcrumbExtractor deprecation
- US3 tasks are purely additive (deprecation markers only) — they cannot break any functionality
- US4 T016/T017 are the only tasks that change the enrichment and embedding wiring in the active pipeline — validate with a full end-to-end ingestion run after both are complete
- `KNOWLEDGE_DOCLING_PAGE_BATCH_SIZE` defaults to `10` — increase on high-RAM machines for throughput, decrease for machines with ≤16 GB RAM
- ChromaDB collection dimensionality is set on first upsert — switching `KNOWLEDGE_EMBED_MODEL` requires clearing or renaming the collection
- The `get_embed_fn()` in `embedder.py` (T019) must be cleaned up **after** T016 and T017 remove its callers; otherwise the module import would fail
