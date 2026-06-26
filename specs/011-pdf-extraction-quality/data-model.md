# Data Model: PDF Extraction Quality & Corpus Cleaning v2

---

## Entities

### ExtractionMode

A discriminator value stored on every ingested chunk to record which extraction strategy produced its text.

| Field | Type | Values | Notes |
|-------|------|--------|-------|
| mode | string | `"text"` \| `"vision"` | `"text"` is the default; backward-compatible with chunks ingested before feature 011 (which have no `extraction_mode` key) |

**Stored as**: ChromaDB metadata field `"extraction_mode"` on every chunk record.

**Not stored as**: A separate entity or table — it is a metadata attribute on the existing chunk schema.

---

### IngestionConfig (updated)

Extends the dataclass introduced in feature 010. This feature adds one new field.

| Field | Type | Default | Source | Notes |
|-------|------|---------|--------|-------|
| `source_type` | string | `"pdf"` | existing | Unchanged |
| `access_level_default` | string | `"public"` | existing | Unchanged |
| `enable_breadcrumbs` | bool | `True` | existing | Unchanged |
| `enable_contextual_summaries` | bool | `True` | existing | Unchanged |
| `cleaning` | CleaningConfig | — | existing | Unchanged |
| `extraction_mode` | Literal[`"text"`, `"vision"`] | `"text"` | **NEW** | Controls which ingestor is used. `"vision"` requires `KNOWLEDGE_VISION_MODEL` to be set; falls back to `"text"` with a WARNING if not. |

---

### VisionLLMProvider (new ABC)

Abstract base class for vision extraction backends. Defined in `packages/llm/llm/interface.py`.

| Method | Signature | Semantics |
|--------|-----------|-----------|
| `extract_page` | `async (image_bytes: bytes, prompt: str) -> str` | Sends a rendered page image to the vision model; returns Markdown text for that page. Raises `RuntimeError` on failure — callers handle the fallback. |

---

### OllamaVisionProvider (new concrete)

Implements `VisionLLMProvider`. Defined in `packages/llm/llm/providers/ollama.py`.

| Attribute | Type | Source |
|-----------|------|--------|
| `model` | str | `KNOWLEDGE_VISION_MODEL` env var |
| `base_url` | str | `OLLAMA_BASE_URL` env var (default `http://localhost:11434`) |
| `timeout_secs` | int | `KNOWLEDGE_VISION_TIMEOUT_SECS` env var (default `120`) |

**API call**: `POST {base_url}/api/generate` with payload `{"model": model, "prompt": prompt, "images": [b64_png], "stream": false}`. Response field: `response`.

---

### VisionPdfIngestor (new class)

Implements the page-rendering and per-page vision extraction loop. Defined in `packages/rag/rag/knowledge/ingestor.py`.

| Responsibility | Detail |
|----------------|--------|
| Open PDF | `fitz.open(file_path)` |
| Render page | `page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0)).tobytes("png")` |
| Extract page | `await vision_provider.extract_page(image_bytes, _VISION_EXTRACTION_PROMPT)` |
| Retry | On failure: retry up to `KNOWLEDGE_VISION_MAX_RETRIES` times; log WARNING per attempt |
| Abort | If all retries exhausted or empty response: log ERROR and raise `IngestionAbortError` |
| Assemble | Returns `list[str]` — one Markdown string per page, same interface as `PdfIngestor` |

**Abort condition**: empty string after `strip()` or any exception from `OllamaVisionProvider.extract_page()` after exhausting retries. **No fallback to pymupdf4llm**.

---

### ChunkQualityGate (pipeline step, not a stored entity)

A three-pass algorithm applied in `IngestionPipeline.run()` between chunking and enrichment.

| Parameter | Env Var | Default | Semantics |
|-----------|---------|---------|-----------|
| `min_chars` | `KNOWLEDGE_MIN_CHUNK_CHARS` | `150` | Chunks shorter than this are merged with the preceding chunk (or the following chunk if there is no preceding chunk). |
| `max_chars` | `KNOWLEDGE_MAX_CHUNK_CHARS` | `15000` | Chunks longer than this are re-split using `create_chunker().chunk(text)`. |

**Pass order**:
1. Stub merge (left-to-right, merge into previous)
2. Giant re-split (replacing oversized chunks with sub-chunks; sub-chunks are not recursively re-split)
3. Stub merge again (handles stubs produced by re-splitting)

**Logging**: `INFO` with counts of stubs merged and giants split per document.

---

### StructuralNoisePage (pipeline classification, not a stored entity)

A page discarded before chunking because its content matches a structural noise pattern.

| Pattern | Detection Rule | Threshold |
|---------|---------------|-----------|
| Back-of-book index | >80% of non-empty lines match `_INDEX_LINE_RE` (dot-leader or pipe-table row) | 0.80 |
| Backer list | >40 name-like tokens AND <5 sentences | 40 names, <5 sentences |

**Effect**: The page is replaced with an empty string in the page list before the chunker runs. Zero chunks are produced for that page.

**Logging**: `WARNING` with page number and pattern that matched.

---

### BenchmarkRecord

The schema of a single record in `benchmark_results.jsonl`. Feature 011 adds `extraction_mode` to the top-level metadata.

| Field | Type | Source |
|-------|------|--------|
| `timestamp` | ISO 8601 string | Added by `run_gold_standard_benchmark()` |
| `global_mrr` | float | Existing |
| `global_ndcg` | float | Existing |
| `global_recall_at_10` | float | Existing |
| `category_scores` | dict[str, CategoryMetrics] | Added in feature 010 |
| `extraction_mode` | str \| None | **NEW** — `"text"` or `"vision"`; `None` for pre-011 records |
| `notes` | str \| None | Free-text tag passed by the caller |

---

### BenchmarkComparison (transient, printed to stdout)

The output of `compare_benchmark_runs()`. Not persisted.

| Column | Notes |
|--------|-------|
| Category | One of the 5 standard categories + `"global"` |
| MRR-A | Score from record A |
| MRR-B | Score from record B |
| ΔMRR | B − A, prefixed with `+` if positive |
| nDCG-A | Score from record A |
| nDCG-B | Score from record B |
| ΔnDCG | B − A, prefixed with `+` if positive |
| Recall-A | Score from record A |
| Recall-B | Score from record B |
| ΔRecall | B − A, prefixed with `+` if positive |

Missing category scores (pre-010 records) show `N/A` in the relevant cells.

---

## Environment Variables (new in feature 011)

| Variable | Default | Purpose |
|----------|---------|---------|
| `KNOWLEDGE_VISION_MODEL` | *(none)* | Name of the Ollama vision model (e.g., `minicpm-v`). Required for `extraction_mode="vision"`. If absent, pipeline falls back to text mode. |
| `KNOWLEDGE_VISION_TIMEOUT_SECS` | `120` | Per-page timeout (seconds) for vision model calls. |
| `KNOWLEDGE_VISION_MAX_RETRIES` | `1` | Number of retry attempts after a vision call failure before aborting. Set to `0` to abort on first failure. |
| `KNOWLEDGE_MIN_CHUNK_CHARS` | `150` | Minimum chunk character count; stubs below this are merged. |
| `KNOWLEDGE_MAX_CHUNK_CHARS` | `15000` | Maximum chunk character count; giants above this are re-split. |

Existing variables (`KNOWLEDGE_MAX_CHUNK_TOKENS`, `OLLAMA_BASE_URL`, `OLLAMA_MODEL`, etc.) are unchanged.
