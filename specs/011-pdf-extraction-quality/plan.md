# Implementation Plan: PDF Extraction Quality & Corpus Cleaning v2

**Branch**: `011-pdf-extraction-quality` | **Date**: 2026-06-26 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/011-pdf-extraction-quality/spec.md`

---

## Summary

Seven empirically confirmed chunk quality problems degrade RAG retrieval across ED4_Players_Guide (1206 chunks). This plan addresses them in two parallel tracks: (1) enhanced text-path cleaning — new `CorpusCleaner` rules covering encoding repair, drop-cap rejoining, image placeholder stripping, page-number stripping, back-of-book structural noise detection, and a post-chunk quality gate; (2) an opt-in vision extraction path — `VisionLLMProvider` ABC + `OllamaVisionProvider`, a new `VisionPdfIngestor`, per-page fallback logic, and `extraction_mode` metadata stored on every chunk. A benchmark comparison function is added to the harness to measure the delta between runs.

---

## Technical Context

**Language/Version**: Python 3.11+

**Primary Dependencies**:
- `packages/llm/` — `LLMProvider` ABC, `OllamaProvider`; **new** `VisionLLMProvider` ABC + `OllamaVisionProvider`
- `packages/rag/` — `CorpusCleaner`, `BreadcrumbExtractor`, `IngestionPipeline`, `IngestionConfig`
- `pymupdf` / `fitz` — already a transitive dependency via `pymupdf4llm`; used for page rendering
- `pymupdf4llm` — existing text-extraction path; continues unchanged as the fallback
- `harness/knowledge_qa/` — gold standard benchmark and **new** comparison function

**Storage**: ChromaDB persistent collection `knowledge_global` at `./data/chroma`; metadata field `extraction_mode` added to every chunk record

**Testing**: `pytest` (unit tests per package); `/harness/knowledge_qa/test_gold_standard.py` for end-to-end benchmark evals

**Target Platform**: Local developer workstation; Linux Docker container (deploy/compose/)

**Project Type**: Library / pipeline — no Gradio UI surface; all new functionality is internal pipeline logic and CLI-accessible harness functions

**Performance Goals**: Text-path re-ingestion of a 500-page PDF must complete in under 10 minutes (same as current baseline). Vision-path ingestion is accepted to take 30–90 minutes for a 500-page PDF (documented in spec Assumptions).

**Constraints**:
- No new cloud dependencies — all new capabilities must run locally via Ollama
- No new Python package dependencies — `ftfy`, `chardet`, `pdf2image` are explicitly excluded; `fitz` is already present
- `KNOWLEDGE_VISION_MODEL` env var controls vision model selection; when absent, pipeline gracefully falls back to text mode
- `KNOWLEDGE_MIN_CHUNK_CHARS` (default 150) and `KNOWLEDGE_MAX_CHUNK_CHARS` (default 15000) are new env vars

**Scale/Scope**: Single-collection RAG system; current corpus 1206 chunks from 1 document. Feature adds pipeline-layer improvements; no schema migration required beyond adding a metadata field.

---

## Constitution Check

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Spec-Driven | ✅ PASS | Spec exists and is complete; this plan traces to FR-001–FR-019 |
| II. Provider Abstraction | ✅ PASS | `VisionLLMProvider` ABC added to `packages/llm/`; switching vision model requires only env-var change |
| III. Package Isolation | ✅ PASS | Vision provider in `packages/llm/`; cleaning rules in `packages/rag/`; no new packages |
| IV. Local-First | ✅ PASS | Ollama multimodal only; no cloud services introduced |
| V. Harness-Driven Quality | ✅ PASS | Benchmark comparison function added to harness; SC-001–SC-008 are verifiable assertions |
| VI. Product-First | ✅ PASS | Feature directly improves retrieval quality, which improves every chat answer |
| VII. Placeholder-First | ✅ PASS | Pipeline is not UI-facing; each cleaning rule is additive; vision path is opt-in with text fallback |
| VIII. Structured Logging | ✅ PASS | All new modules use `logging.getLogger(__name__)` at module level; no `print()` in new code |

---

## Project Structure

### Documentation (this feature)

```text
specs/011-pdf-extraction-quality/
├── plan.md              # This file
├── research.md          # Phase 0 decisions
├── data-model.md        # Entity model
├── quickstart.md        # Validation guide
├── contracts/           # Interface contracts
│   ├── vision-llm-provider.md
│   └── ingestion-config.md
└── tasks.md             # Phase 2 output (/speckit-tasks)
```

### Source Code (repository root)

```text
packages/llm/llm/
├── interface.py                       # ADD: VisionLLMProvider ABC
└── providers/
    └── ollama.py                      # ADD: OllamaVisionProvider

packages/rag/rag/knowledge/
├── cleaner.py                         # MODIFY: FR-001..FR-006 new cleaning rules
├── breadcrumb.py                      # MODIFY: FR-009 markdown stripping
├── interface.py                       # MODIFY: FR-010 extraction_mode on IngestionConfig
├── ingestor.py                        # ADD: VisionPdfIngestor class
└── pipeline.py                        # MODIFY: extraction routing + quality gate

harness/knowledge_qa/
└── test_gold_standard.py              # ADD: compare_benchmark_runs()

README.md                              # UPDATE: document new env vars and extraction modes
```

---

## Architecture Decisions

### AD-001: VisionLLMProvider ABC

A separate ABC for vision extraction rather than extending `LLMProvider` or calling the Ollama multimodal API directly from the ingestor.

**Rationale**: The Ollama multimodal API (`POST /api/generate` with `images` field) is structurally different from the text chat completions API (`POST /v1/chat/completions`). A single method on a dedicated ABC — `extract_page(image_bytes, prompt) -> str` — is the smallest interface that satisfies Constitution II (provider abstraction). Any future vision provider (OpenAI Vision, Claude Vision, Google Gemini) can implement the same ABC.

**Interface**:
```python
class VisionLLMProvider(ABC):
    @abstractmethod
    async def extract_page(self, image_bytes: bytes, prompt: str) -> str: ...
```

**Implementation** (`OllamaVisionProvider`):
- `POST http://localhost:11434/api/generate`
- Payload: `{"model": model_name, "prompt": prompt, "images": [b64_png], "stream": false}`
- Response: `response_json["response"]`
- Timeout: 120s per page (configurable via `KNOWLEDGE_VISION_TIMEOUT_SECS`, default 120)
- Error handling: raises `RuntimeError` on HTTP error / timeout; pipeline catches and falls back

### AD-002: Page Rendering via fitz

Use `fitz.open(path)` → `page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0))` → `pixmap.tobytes("png")` per page. No new dependency. DPI 144 (2× scale) balances readability against Ollama model image size limits.

### AD-003: Extraction Routing in IngestionPipeline

`IngestionPipeline._extract(file_path, config)` dispatches to either `PdfIngestor` (text) or `VisionPdfIngestor` (vision) based on `config.extraction_mode`. Both return `list[str]` (one string per page of extracted Markdown). The quality gate and all downstream steps are path-agnostic.

### AD-004: Post-Chunk Quality Gate Placement

The quality gate runs after chunking and before enrichment, inside `IngestionPipeline.run()`. This is the earliest point where chunk boundaries are stable and chunk lengths are known. Running it earlier (pre-chunking) would require predicting chunk sizes; running it later (post-enrichment) would waste enrichment LLM calls on stubs.

**Algorithm** (three passes):
1. Merge stubs: `len(chunk) < MIN_CHARS` → append to previous (or next if first)
2. Re-split giants: `len(chunk) > MAX_CHARS` → `create_chunker().chunk(chunk)` — sub-chunks are NOT recursively re-split to avoid infinite loops on unsplittable content
3. Merge stubs again (clean up any stubs produced by step 2)

### AD-005: Encoding Repair Without New Dependencies

Windows-1252 mojibake is fixed via a `str.maketrans()` replacement table covering the C1 control-point range (U+0080–U+009F) and known smart-punctuation sequences. This avoids adding `ftfy` or `chardet` as new project dependencies. The table covers all 25 characters observed in the ED4_Players_Guide corpus. Bare U+FFFD replacement characters (`�`) are stripped entirely.

### AD-006: Structural Noise Detection — Content-Pattern, Not Position-Based

The existing `_strip_toc()` is page-position-bounded (pages < 30). Back-of-book index and backer-list pages appear after page 480. New detection rules use content-pattern matching applied to all pages:

- **Index pages**: >80% of non-empty lines match `_INDEX_LINE_RE` (dot-leader or pipe-table row)
- **Backer-list pages**: >40 name-like tokens AND <5 sentences (detected by period/question/exclamation count)

Both rules are applied in `CorpusCleaner.clean(pages: list[str]) -> list[str]` — pages that match are replaced with an empty string so the chunker produces no content for them.

### AD-007: Breadcrumb Markdown Stripping

`BreadcrumbExtractor.extract()` applies `re.sub(r'[*_`#]', '', heading_text)` to each heading segment before assembling the breadcrumb path. The heading regex match and position matching continue to use the original markdown heading; only the stored path segment is plain-text.

### AD-008: extraction_mode Metadata on Every Chunk

`VisionPdfIngestor` tags each extracted page with `{"extraction_mode": "vision"}`. `PdfIngestor` tags pages with `{"extraction_mode": "text"}`. The pipeline merges this into the chunk metadata dict stored in ChromaDB. This enables `compare_benchmark_runs()` to filter runs by extraction mode.

### AD-009: Benchmark Comparison Selectors

`compare_benchmark_runs(selector_a, selector_b, jsonl_path)`:
- Integer selectors: index into the loaded records list (supports negative indexing)
- String selectors: matched against the `timestamp` field (exact or prefix match)
- Missing selector: `ValueError` with a list of available timestamps
- Missing `category_scores` field: displays `N/A` in affected cells

---

## Phase Plan

### Phase 1 — Text Cleaning Rules (FR-001–FR-006, FR-009) [P1]

**Files**: `packages/rag/rag/knowledge/cleaner.py`, `packages/rag/rag/knowledge/breadcrumb.py`

1. Add `_repair_encoding(text: str) -> str` — apply `_WIN1252_MAP` translation table + strip `�`
2. Add `_repair_dropcap(text: str) -> str` — apply `_DROPCAP_RE` (`^([A-Z])\n([a-z])`) substitution
3. Add `_strip_image_placeholders(text: str) -> str` — strip `==> picture ... <==` and fenced picture blocks
4. Add `_strip_page_numbers(text: str) -> str` — strip `^\s*\d{1,4}\s*$` lines between blank lines
5. Add `_is_index_page(page: str) -> bool` — `_INDEX_LINE_RE` density check (>80% threshold)
6. Add `_is_backer_page(page: str) -> bool` — name-token count + sentence count heuristic
7. Apply all rules in `CorpusCleaner.clean()` in this order: encoding → dropcap → image placeholder → page numbers; apply page-level filters (index, backer) to discard pages before text-level rules
8. In `BreadcrumbExtractor.extract()`: strip `[*_\`#]` from each heading segment before building the path string

### Phase 2 — Post-Chunk Quality Gate (FR-007–FR-008) [P1]

**Files**: `packages/rag/rag/knowledge/pipeline.py`, `packages/rag/rag/knowledge/interface.py`

1. Add `KNOWLEDGE_MIN_CHUNK_CHARS` and `KNOWLEDGE_MAX_CHUNK_CHARS` env-var reads
2. Add `_apply_quality_gate(chunks, min_chars, max_chars) -> list[str]` — three-pass stub-merge / giant-split
3. Wire `_apply_quality_gate()` into `IngestionPipeline.run()` after chunking, before enrichment
4. Log at INFO level: count of stubs merged, count of giants re-split

### Phase 3 — Vision Provider Abstraction (FR-010–FR-015) [P2]

**Files**: `packages/llm/llm/interface.py`, `packages/llm/llm/providers/ollama.py`, `packages/rag/rag/knowledge/interface.py`, `packages/rag/rag/knowledge/ingestor.py`, `packages/rag/rag/knowledge/pipeline.py`

1. Add `VisionLLMProvider(ABC)` to `packages/llm/llm/interface.py`
2. Add `OllamaVisionProvider` to `packages/llm/llm/providers/ollama.py` — implements `extract_page()` via `/api/generate`
3. Add `extraction_mode: Literal["text", "vision"] = "text"` to `IngestionConfig`
4. Add `VisionPdfIngestor` to `ingestor.py` — renders pages via fitz, calls `OllamaVisionProvider`, falls back per-page on error
5. Update `IngestionPipeline._extract()` to dispatch on `config.extraction_mode`
6. Add `extraction_mode` key to chunk metadata dict before ChromaDB upsert

### Phase 4 — Benchmark Comparison Tool (FR-016–FR-018) [P3]

**Files**: `harness/knowledge_qa/test_gold_standard.py`

1. Add `_load_benchmark_records(jsonl_path) -> list[dict]` — reads and parses all lines
2. Add `_resolve_selector(records, selector) -> dict` — handles int and string selectors
3. Add `compare_benchmark_runs(selector_a, selector_b, jsonl_path=None)` — resolves both, builds and prints the diff table
4. Table format: Category | MRR-A | MRR-B | ΔMRR | nDCG-A | nDCG-B | ΔnDCG | Recall-A | Recall-B | ΔRecall

### Phase 5 — Documentation (FR-019) [P1]

**Files**: `README.md`, `specs/010-contextual-retrieval-breadcrumbs/tasks.md` (T023–T025 deferred from feature 010)

1. Update `README.md` Knowledge section: document `extraction_mode`, `KNOWLEDGE_VISION_MODEL`, `KNOWLEDGE_MIN_CHUNK_CHARS`, `KNOWLEDGE_MAX_CHUNK_CHARS`, and the re-ingestion requirement
2. Note that re-ingestion is required to apply new cleaning rules or switch extraction modes
