# Tasks: PDF Extraction Quality & Corpus Cleaning v2

**Input**: Design documents from `specs/011-pdf-extraction-quality/`

**Prerequisites**: [plan.md](plan.md) | [spec.md](spec.md) | [data-model.md](data-model.md) | [contracts/](contracts/) | [research.md](research.md) | [quickstart.md](quickstart.md)

**Tests**: No dedicated test tasks — validated via existing pytest suite and the gold standard harness in `harness/knowledge_qa/`.

**Organization**: Tasks grouped by user story. US1 (P1 text cleaning) is entirely independent of US2 (P2 vision path) and US3 (P3 comparison tool). Each story delivers a standalone, testable increment.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no data dependencies on an in-progress task)
- **[Story]**: User story this task belongs to (US1, US2, US3)

---

## Phase 1: Setup

**Purpose**: Establish the pre-feature benchmark baseline needed to measure SC-006 (Recall@10 +5pp).

- [ ] T001 Run the existing gold standard benchmark and confirm a new record lands in `harness/knowledge_qa/benchmark_results.jsonl` — this record is the SC-006 baseline; note the timestamp for later comparison

**Checkpoint**: Baseline captured — coding can begin

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Two shared primitives that US1 and US2 both depend on. MUST be complete before any user-story work.

**⚠️ CRITICAL**: No US1 or US2 work can begin until this phase is complete.

- [ ] T002 Add `extraction_mode: Literal["text", "vision"] = "text"` field to `IngestionConfig` dataclass in `packages/rag/rag/knowledge/interface.py` (used by US1 for metadata tagging and by US2 for extraction routing)
- [ ] T003 Add `IngestionAbortError(RuntimeError)` exception class to `packages/rag/rag/knowledge/interface.py` (used by US2 to abort vision ingestion on exhausted retries)

**Checkpoint**: Foundation ready — US1 and US2 work can now begin in parallel

---

## Phase 3: User Story 1 — Enhanced Text Cleaning (Priority: P1) 🎯 MVP

**Goal**: Fix all seven corpus quality problems (encoding, drop-cap, image placeholders, page numbers, index pages, backer pages, quality gate, breadcrumb markdown) so re-ingesting ED4_Players_Guide produces a clean corpus that satisfies SC-001–SC-006.

**Independent Test**: Re-ingest ED4_Players_Guide with `extraction_mode="text"` (default). Run the assertions in `quickstart.md` Scenario 1 — all five `assert` statements must pass. Then run the benchmark and use T023 (when done) to verify ΔRecall ≥ +0.05.

### Implementation

- [ ] T004 [US1] Add module-level `_log = logging.getLogger(__name__)` and the `_WIN1252_MAP = str.maketrans({...})` constant to `packages/rag/rag/knowledge/cleaner.py` (covers the full Windows-1252 C1 range: curly quotes, em-dash, en-dash, bullet, ellipsis, and related chars; strip bare U+FFFD `�` replacement chars)
- [ ] T005 [US1] Add `_repair_encoding(text: str) -> str` to `packages/rag/rag/knowledge/cleaner.py`: applies `text.translate(_WIN1252_MAP)` then strips any remaining `�` chars
- [ ] T006 [US1] Add `_DROPCAP_RE = re.compile(r'(?m)^([A-Z])\n([a-z])')` constant and `_repair_dropcap(text: str) -> str` to `packages/rag/rag/knowledge/cleaner.py`: substitutes `\1\2` to rejoin isolated drop-cap uppercase letter with the lowercase continuation on the next line
- [ ] T007 [US1] Add `_IMAGE_PLACEHOLDER_RE` (matches `==> picture … <==` lines and `--- Start of picture text ---` … `--- End of picture text ---` fenced blocks) and `_strip_image_placeholders(text: str) -> str` to `packages/rag/rag/knowledge/cleaner.py`
- [ ] T008 [US1] Add `_PAGE_NUMBER_RE = re.compile(r'(?m)^\s*\d{1,4}\s*$')` and `_strip_page_numbers(text: str) -> str` to `packages/rag/rag/knowledge/cleaner.py`: removes standalone integer-only lines (bare page-footer numbers) that appear between blank lines
- [ ] T009 [US1] Add `_INDEX_LINE_RE = re.compile(r'^.{1,120}(?:\.{2,}|\|)\s*\d*\s*$')` and `_is_index_page(page: str) -> bool` to `packages/rag/rag/knowledge/cleaner.py`: returns `True` when >80% of non-empty lines match the dot-leader or pipe-table pattern (back-of-book A-Z index detection)
- [ ] T010 [US1] Add `_is_backer_page(page: str) -> bool` to `packages/rag/rag/knowledge/cleaner.py`: returns `True` when `re.findall(r'\b[A-Z][a-z]+(?:\s[A-Z][a-z]+){0,2}\b', page)` count > 40 AND the count of sentences (lines ending in `.`, `!`, or `?`) < 5 (Kickstarter backer-list detection per FR-006)
- [ ] T011 [US1] Wire all new rules into `CorpusCleaner.clean(pages: list[str]) -> list[str]` in `packages/rag/rag/knowledge/cleaner.py`: (1) filter out pages where `_is_index_page` or `_is_backer_page` returns True (log WARNING with page index and reason); (2) apply `_repair_encoding`, `_repair_dropcap`, `_strip_image_placeholders`, `_strip_page_numbers` in that order to each remaining page's text
- [ ] T012 [P] [US1] Add markdown-stripping to `BreadcrumbExtractor.extract()` in `packages/rag/rag/knowledge/breadcrumb.py`: apply `re.sub(r'[*_`#]', '', heading_text)` to each heading segment before assembling the breadcrumb path string (the heading regex match continues to use the original markdown; only the stored breadcrumb path segment is plain-text)
- [ ] T013 [US1] Add `KNOWLEDGE_MIN_CHUNK_CHARS = int(os.getenv("KNOWLEDGE_MIN_CHUNK_CHARS", "150"))` and `KNOWLEDGE_MAX_CHUNK_CHARS = int(os.getenv("KNOWLEDGE_MAX_CHUNK_CHARS", "15000"))` reads and implement `_apply_quality_gate(chunks: list[str], min_chars: int, max_chars: int) -> list[str]` in `packages/rag/rag/knowledge/pipeline.py`: Pass 1 — left-to-right merge stubs < min_chars into previous chunk (or next if first); Pass 2 — replace giants > max_chars using `create_chunker().chunk(chunk)` (no recursive re-split); Pass 3 — repeat Pass 1 once to clean up any new stubs
- [ ] T014 [US1] Wire `_apply_quality_gate()` into `IngestionPipeline.run()` in `packages/rag/rag/knowledge/pipeline.py`: call it after chunking and before the enrichment loop; log at INFO level with the count of stubs merged and giants split
- [ ] T015 [US1] Add `"extraction_mode": config.extraction_mode` to the chunk metadata dict constructed before each ChromaDB upsert call in `packages/rag/rag/knowledge/pipeline.py`

**Checkpoint**: US1 complete — re-ingest ED4_Players_Guide and run quickstart.md Scenario 1 assertions; all five must pass

---

## Phase 4: User Story 2 — Vision LLM Extraction Path (Priority: P2)

**Goal**: Opt-in `extraction_mode="vision"` that renders each PDF page to PNG, extracts Markdown via `OllamaVisionProvider`, retries up to `KNOWLEDGE_VISION_MAX_RETRIES` times on failure, and aborts with `IngestionAbortError` if retries are exhausted — no silent fallback to text.

**Independent Test**: Set `KNOWLEDGE_VISION_MODEL=minicpm-v`, re-ingest a short PDF (or the first 10 pages of ED4_Players_Guide) with `extraction_mode="vision"`. Verify: (a) chunks have `extraction_mode="vision"` in metadata; (b) killing Ollama mid-run triggers ERROR log and aborts; (c) unsetting `KNOWLEDGE_VISION_MODEL` and re-running aborts immediately with a clear error message.

### Implementation

- [ ] T016 [P] [US2] Add `VisionLLMProvider(ABC)` to `packages/llm/llm/interface.py` with one abstract method: `async def extract_page(self, image_bytes: bytes, prompt: str) -> str` — docstring specifies: returns Markdown string (never None; may be empty string on no-output); raises `RuntimeError` on provider call failure
- [ ] T017 [US2] Implement `OllamaVisionProvider(VisionLLMProvider)` in `packages/llm/llm/providers/ollama.py`: `__init__(model: str, base_url: str, timeout_secs: int)`; `async extract_page()` sends `POST {base_url}/api/generate` with payload `{"model": model, "prompt": prompt, "images": [base64_png], "stream": false}`; reads `response_json["response"]`; raises `RuntimeError` on HTTP != 200, timeout (`aiohttp.ServerTimeoutError`), or missing `response` field; logs at DEBUG on success, ERROR on HTTP failure, WARNING on timeout (uses module-level `_log = logging.getLogger(__name__)`)
- [ ] T018 [P] [US2] Define `_VISION_EXTRACTION_PROMPT` constant and `KNOWLEDGE_VISION_MAX_RETRIES = int(os.getenv("KNOWLEDGE_VISION_MAX_RETRIES", "1"))` in `packages/rag/rag/knowledge/ingestor.py`; prompt text: "Extract all text from this image as structured Markdown. Preserve headings (# ## ###), bold (**text**), italic (*text*), and table structure (|col|col|). Output only the Markdown text — no explanations, preamble, or code fences."
- [ ] T019 [US2] Implement `VisionPdfIngestor` class in `packages/rag/rag/knowledge/ingestor.py`: `__init__(vision_provider: VisionLLMProvider)`; `async extract(file_path: str, config: IngestionConfig) -> list[str]` opens PDF via `import fitz; doc = fitz.open(file_path)`, iterates pages, renders each via `page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0)).tobytes("png")`, calls `vision_provider.extract_page(png_bytes, _VISION_EXTRACTION_PROMPT)`; on empty response or `RuntimeError` retries up to `KNOWLEDGE_VISION_MAX_RETRIES` times (logging WARNING per attempt); if all retries exhausted raises `IngestionAbortError(f"Vision extraction aborted after {attempts} attempts on page {page_num}: {reason}")`
- [ ] T020 [US2] Update `IngestionPipeline._extract()` (or equivalent extraction dispatch) in `packages/rag/rag/knowledge/pipeline.py`: when `config.extraction_mode == "vision"` check `KNOWLEDGE_VISION_MODEL = os.getenv("KNOWLEDGE_VISION_MODEL")`; if unset raise `IngestionAbortError("KNOWLEDGE_VISION_MODEL env var is required for extraction_mode='vision' but is not set")`; otherwise construct `OllamaVisionProvider(model=KNOWLEDGE_VISION_MODEL, ...)` and `VisionPdfIngestor(provider)` and call `await ingestor.extract(file_path, config)`; when `config.extraction_mode == "text"` call existing `PdfIngestor` path unchanged

**Checkpoint**: US2 complete — run quickstart.md Scenario 3 assertions (extraction_mode metadata, abort on model unavailable)

---

## Phase 5: User Story 3 — Benchmark Run Comparison Tool (Priority: P3)

**Goal**: `compare_benchmark_runs(selector_a, selector_b)` prints a side-by-side per-category diff table in under 2 seconds (reads JSONL only — no model calls).

**Independent Test**: Run `compare_benchmark_runs(-2, -1)` after having at least two records in `benchmark_results.jsonl`. Verify the output contains exactly 6 rows (5 categories + global) with columns MRR-A, MRR-B, ΔMRR, nDCG-A, nDCG-B, ΔnDCG, Recall-A, Recall-B, ΔRecall. Verify `compare_benchmark_runs(999, -1)` raises `ValueError` with a message listing available records.

### Implementation

- [ ] T021 [US3] Add `_load_benchmark_records(jsonl_path: str | None = None) -> list[dict]` to `harness/knowledge_qa/test_gold_standard.py`: reads all lines from `jsonl_path` (defaults to the same `benchmark_results.jsonl` path used by `run_gold_standard_benchmark()`), parses each as JSON, returns list; empty file returns `[]`
- [ ] T022 [US3] Add `_resolve_selector(records: list[dict], selector: int | str) -> dict` to `harness/knowledge_qa/test_gold_standard.py`: int selector → `records[selector]` (supports negative indexing); string selector → first record whose `timestamp` field starts with the selector string; if no match raises `ValueError` listing available timestamps; if `records` is empty raises `ValueError` with "No benchmark records found"
- [ ] T023 [US3] Add `compare_benchmark_runs(selector_a: int | str, selector_b: int | str, jsonl_path: str | None = None)` to `harness/knowledge_qa/test_gold_standard.py`: calls `_load_benchmark_records`, resolves both selectors via `_resolve_selector`, then prints a table to stdout with header row and one data row per category plus a "global" row; columns: Category | MRR-A | MRR-B | ΔMRR | nDCG-A | nDCG-B | ΔnDCG | Recall-A | Recall-B | ΔRecall; positive deltas printed with `+` prefix; missing `category_scores` entries in either record display `N/A` in relevant cells

**Checkpoint**: US3 complete — run quickstart.md Scenario 4 (error handling) and Scenario 2 (actual diff after US1 re-ingestion)

---

## Phase 6: Polish & Cross-Cutting Concerns

- [ ] T024 [P] Update `README.md` Knowledge Ingestion section: document the new `extraction_mode` option, `KNOWLEDGE_VISION_MODEL`, `KNOWLEDGE_VISION_MAX_RETRIES`, `KNOWLEDGE_VISION_TIMEOUT_SECS`, `KNOWLEDGE_MIN_CHUNK_CHARS`, `KNOWLEDGE_MAX_CHUNK_CHARS` env vars, and state explicitly that applying new cleaning rules or switching extraction mode requires full re-ingestion per FR-019
- [ ] T025 Validate all five quickstart.md scenarios end-to-end after all phases are complete (Scenario 1: text-path assertions; Scenario 2: benchmark delta; Scenario 3: vision metadata & abort; Scenario 4: comparison error handling; Scenario 5: breadcrumb stripping)
- [ ] T026 [P] Update `specs/011-pdf-extraction-quality/contracts/vision-llm-provider.md` and `data-model.md` if any implementation details diverged from the contract during coding (keep contracts in sync as living documentation)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS US1 (T015) and US2 (T019, T020)
- **US1 (Phase 3)**: Depends on Phase 2 (T002 for extraction_mode metadata on T015)
- **US2 (Phase 4)**: Depends on Phase 2 (T002 for routing, T003 for IngestionAbortError); can run in parallel with US1
- **US3 (Phase 5)**: Depends only on having benchmark records (T001); fully independent of US1 and US2
- **Polish (Phase 6)**: Depends on all user story phases complete

### User Story Dependencies

- **US1 (P1)**: Can start after Phase 2; no dependency on US2 or US3
- **US2 (P2)**: Can start after Phase 2 in parallel with US1; reads `IngestionConfig.extraction_mode` (T002) and uses `IngestionAbortError` (T003)
- **US3 (P3)**: Can start after T001 (baseline record exists); does not depend on US1 or US2 implementation

### Within US1

T004 → T005 (encoding map before repair function) → T006, T007, T008, T009, T010 (independent, same file, any order) → T011 (wires all into clean()) → T012 (independent, different file) → T013 → T014 → T015

### Within US2

T016 → T017 → T018 (independent of T017, different concern) → T019 (uses T016+T017+T018) → T020

### Within US3

T021 → T022 → T023

---

## Parallel Opportunities

```
# After Phase 2 completes, these can run concurrently:

[Terminal A - US1]
T004 → T005 → T006 → T007 → T008 → T009 → T010 → T011 → T012 → T013 → T014 → T015

[Terminal B - US2]
T016 → T017
T018 (in parallel with T017)
T019 → T020

[Terminal C - US3]
T021 → T022 → T023  (can start immediately after T001)
```

Within US1, T012 (breadcrumb, different file) can be done in parallel with any of T004–T010.

---

## Implementation Strategy

### MVP First (US1 Only)

1. Complete Phase 1: Baseline benchmark
2. Complete Phase 2: IngestionConfig + IngestionAbortError
3. Complete Phase 3: US1 text cleaning (T004–T015)
4. **STOP AND VALIDATE**: Re-ingest ED4_Players_Guide, run quickstart.md Scenario 1 assertions, run benchmark and confirm ΔRecall ≥ +0.05
5. Deliver US1 — corpus is already substantially cleaner

### Incremental Delivery

1. Setup + Foundational → done
2. US1 (text cleaning) → test → demo cleaner corpus
3. US2 (vision path) → test with short PDF → compare against US1
4. US3 (comparison tool) → use immediately to show US1 vs US2 delta
5. Polish → README and contract sync

### Quickstart Validation Checklist

| Scenario | Validates | Run After |
|----------|-----------|-----------|
| Scenario 1 (text cleaning assertions) | SC-001–SC-005 | Phase 3 (T015) |
| Scenario 2 (benchmark delta) | SC-006 | T023 (US3) + T025 (polish) |
| Scenario 3 (vision extraction) | SC-007, FR-015 | Phase 4 (T020) |
| Scenario 4 (comparison error handling) | FR-018 | T023 |
| Scenario 5 (breadcrumb stripping) | FR-009 | T012 |

---

## Notes

- All new functions must use the module-level `_log = logging.getLogger(__name__)` logger (Constitution VIII). Check existing files — if the logger is missing at module level, add it as part of the first task touching that file.
- `cleaner.py` tasks (T004–T011) all modify the same file; implement them sequentially in a single editing session rather than attempting parallelism within the file.
- `VisionPdfIngestor` uses `import fitz` inside the class (matching the existing pattern in `ingestor.py`) — do not add a top-level `import fitz` that would cause import errors when PyMuPDF is unavailable.
- The `IngestionAbortError` raised by US2 must propagate up through `IngestionPipeline.run()` without being caught — ensure no broad `except Exception` swallows it in the pipeline's enrichment or storage loops.
- Feature 010 deferred tasks (T023–T025 in that feature's tasks.md: enricher.py module-level logger, spec-plan FR-012 alignment, ABC type annotation) are out of scope here — address them in a separate feature 010 cleanup commit.
