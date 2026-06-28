# Data Model: Docling Ingestion Pipeline (012)

*Phase 1 output — entities introduced or modified by this feature.*

---

## New Entities

### DoclingIngestor

**Location**: `packages/rag/rag/knowledge/ingestor.py`

**Purpose**: Replaces `PdfIngestor` for the active ingestion path. Wraps Docling's `DocumentConverter` + `HybridChunker` to produce body chunks with pre-computed breadcrumbs from `meta.headings`.

**Interface**:
```python
class DoclingIngestor:
    async def extract(
        self,
        file_path: str,
        config: IngestionConfig,
    ) -> tuple[str, list[str], list[str]]:
        """
        Returns:
            full_text:   Docling document exported as Markdown (for logging/debug)
            chunks:      list of body-text strings (without breadcrumb prefix)
            breadcrumbs: parallel list of assembled " > "-joined heading strings
        """
```

**Key behaviours**:
- `DocumentConverter` instantiated with `do_ocr=False`, `generate_page_images=False`
- **Page-batch processing**: PDF is processed in batches of `KNOWLEDGE_DOCLING_PAGE_BATCH_SIZE` pages (default 10, 1-indexed). Each batch calls `converter.convert(..., page_range=(start, end))`. Chunks from all batches are concatenated before the quality gate. `HybridChunker` is constructed once and reused across batches.
- `HybridChunker` uses `AutoTokenizer.from_pretrained(KNOWLEDGE_EMBED_MODEL or "nomic-ai/nomic-embed-text-v1.5")` and `max_tokens=512`
- If `result.errors` is non-empty for a page batch, logs ERROR and raises `IngestionAbortError`
- Each heading in `meta.headings` has Markdown chars (`*`, `_`, `#`, `` ` ``) stripped before joining
- Empty `meta.headings` → breadcrumb is `""`
- `extraction_mode` field is set to `"docling"` via the IngestionConfig before this class is invoked

---

### DoclingChunker

**Location**: `packages/rag/rag/knowledge/docling_chunker.py`

**Purpose**: Thin wrapper around `HybridChunker` to encapsulate Docling chunking logic and tokenizer construction.

**Interface**:
```python
class DoclingChunker:
    def __init__(self, tokenizer_name: str = "nomic-ai/nomic-embed-text-v1", max_tokens: int = 512) -> None: ...

    def chunk(self, document: DoclingDocument) -> list[tuple[str, list[str]]]:
        """Returns list of (body_text, headings) pairs."""
```

**Validation rules**:
- `body_text` from `chunk.text` — raw string, no stripping applied here (quality gate handles size)
- `headings` from `chunk.meta.headings` — already a `list[str]`; Markdown-stripping applied at the breadcrumb assembly step in `DoclingIngestor`

---

### HuggingFaceEmbedFn

**Location**: `packages/rag/rag/knowledge/embedder.py`

**Purpose**: Embedding function for HuggingFace Inference API feature-extraction endpoint. Parallel to `OllamaEmbedFn`; selected when `KNOWLEDGE_EMBED_PROVIDER=huggingface`.

**Interface**:
```python
class HuggingFaceEmbedFn:
    def __init__(self, model: str, api_key: str) -> None: ...

    @property
    def name(self) -> str:
        return f"huggingface_{self._model}"

    def __call__(self, input: list[str]) -> list[list[float]]:
        """Sync HTTP call to HF Inference API feature-extraction endpoint."""

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Async wrapper using asyncio.to_thread."""
```

**Endpoint**: `POST https://api-inference.huggingface.co/models/{model}`
**Request body**: `{"inputs": ["text1", "text2", ...]}`
**Response body**: `[[float, ...], [float, ...]]`
**Auth**: `Authorization: Bearer {api_key}`
**Error handling**:
- HTTP 429 (rate limit): retry with exponential backoff — 3 attempts, initial delay 5 s, doubling each attempt. If all retries exhausted, raise `ProviderUnavailableError` (pipeline stores `failed` status + `chunks_processed` in SQLite for manual re-run).
- HTTP 4xx/5xx (other): raise `ProviderUnavailableError` immediately.

**Supported models** (set via `KNOWLEDGE_EMBED_MODEL` — no code changes needed):
- `nomic-ai/nomic-embed-text-v1.5` — preferred for Ollama; 256 dims via `truncate_dim: 256`. HF serverless availability unconfirmed.
- `BAAI/bge-m3` — strong multilingual model; 1024 dims; likely available on HF free serverless Inference API.
- `sentence-transformers/all-MiniLM-L6-v2` — confirmed HF free serverless; 384 dims; use as fallback if bge-m3 is unavailable.

---

### Factory Functions

**Location**: `packages/rag/rag/knowledge/factory.py`

**Purpose**: Provider selection factories following the `get_image_provider()` pattern in `packages/imagegen/imagegen/factory.py`.

#### `get_knowledge_enrich_provider(model: str) → LLMProvider`

```
Reads:  KNOWLEDGE_ENRICH_PROVIDER (required; "ollama" | "huggingface")
Reads:  OLLAMA_BASE_URL (when provider=ollama)
Reads:  HF_API_KEY (required when provider=huggingface)
Param:  model — caller passes KNOWLEDGE_ENRICH_MODEL value (required, no default)
```

**Validation**:
- `KNOWLEDGE_ENRICH_PROVIDER` absent/blank → log ERROR, raise `EnvironmentError`
- `KNOWLEDGE_ENRICH_PROVIDER` not in `{"ollama", "huggingface"}` → log ERROR, raise `EnvironmentError`
- `HF_API_KEY` absent/blank when `provider=huggingface` → log ERROR, raise `EnvironmentError`
- `model` blank → log ERROR, raise `EnvironmentError`

#### `get_knowledge_embed_fn() → OllamaEmbedFn | HuggingFaceEmbedFn`

```
Reads:  KNOWLEDGE_EMBED_PROVIDER (required; "ollama" | "huggingface")
Reads:  KNOWLEDGE_EMBED_MODEL (required; no code-level default)
Reads:  OLLAMA_BASE_URL (when provider=ollama)
Reads:  HF_API_KEY (required when provider=huggingface)
```

**Validation**: same pattern as enrich factory.

---

## Modified Entities

### IngestionConfig (interface.py)

**Change**: Add `"docling"` as a valid value for `extraction_mode`.

```
extraction_mode: "text" | "vision" | "docling"
```

The pipeline's `_extract()` now dispatches on `format == "pdf"` and `config.extraction_mode == "docling"` → `DoclingIngestor`.

---

## ChromaDB Metadata Schema (updated)

All fields below are stored per chunk in ChromaDB. New/changed fields are marked.

| Field | Type | Source | Notes |
|-------|------|--------|-------|
| `doc_id` | str | `IngestionPipeline.run()` arg | Unchanged |
| `doc_title` | str | SQLite `knowledge_documents.title` | Unchanged |
| `chunk_index` | int | 0-based global chunk index | Unchanged |
| `headline` | str | `ChunkEnricher` | Unchanged |
| `summary` | str | `ChunkEnricher` | Unchanged |
| `topic` | str | `ChunkEnricher` | Unchanged |
| `access_level` | str | `ChunkEnricher` or config override | Unchanged |
| `scope` | str | `"global"` or `"campaign"` | Unchanged |
| `campaign_id` | str | `IngestionPipeline.run()` arg | Unchanged |
| `original_text` | str | C-effective: `breadcrumb\n\nbody` | Unchanged in structure; now sourced from Docling body text |
| `breadcrumb` | str | `meta.headings` joined with `" > "` | Now sourced from HybridChunker instead of BreadcrumbExtractor |
| `source_type` | str | `IngestionConfig.source_type` | Unchanged |
| `extraction_mode` | str | `IngestionConfig.extraction_mode` | **Now includes `"docling"`** (was `"text"` \| `"vision"`) |

---

## Environment Variables (new or updated)

| Var | Required? | Default | Purpose |
|-----|-----------|---------|---------|
| `KNOWLEDGE_ENRICH_PROVIDER` | **Required** | none | `"ollama"` or `"huggingface"` — selects enrichment LLM |
| `KNOWLEDGE_EMBED_PROVIDER` | **Required** | none | `"ollama"` or `"huggingface"` — selects embedding function |
| `KNOWLEDGE_ENRICH_MODEL` | **Required** | none | Model name for enrichment LLM (no code-level fallback) |
| `KNOWLEDGE_EMBED_MODEL` | **Required** | none | Model name for embedding (no code-level fallback). Recommended: `nomic-ai/nomic-embed-text-v1.5` (Ollama) or `sentence-transformers/all-MiniLM-L6-v2` (HF) |
| `HF_API_KEY` | Conditional | none | Required when either provider is `"huggingface"` |
| `OLLAMA_BASE_URL` | Optional | `http://localhost:11434` | Ollama server URL (conventional default acceptable) |
| `KNOWLEDGE_DOCLING_PAGE_BATCH_SIZE` | Optional | `10` | Pages per Docling conversion batch (memory vs. throughput trade-off) |

**Breaking change**: `KNOWLEDGE_ENRICH_MODEL` and `KNOWLEDGE_EMBED_MODEL` are now required — the pipeline aborts with ERROR if either is absent. Previously, `settings.knowledge_enrich_model` / `settings.knowledge_embed_model` provided silent fallbacks.

---

## Deprecated Entities (retained, not deleted)

| Entity | Module | Deprecation notice |
|--------|--------|--------------------|
| `PdfIngestor` | `ingestor.py` | Module-level docstring + WARNING log on instantiation |
| `HeadingChunker` | `chunker.py` | Module-level docstring + WARNING log on instantiation |
| `SemanticChunker` | `chunker_semantic.py` | Module-level docstring + WARNING log on instantiation |
| `AgenticChunker` | `chunker_agentic.py` | Module-level docstring + WARNING log on instantiation |
| `BreadcrumbExtractor` | `breadcrumb.py` | Module-level docstring + WARNING log on instantiation |
| `CorpusCleaner` FR-003 rule | `cleaner.py` | Inline `# DEPRECATED(012)` comment; rule excluded from active Docling cleaning profile |
| `CorpusCleaner` FR-004 rule | `cleaner.py` | Inline `# DEPRECATED(012)` comment; rule excluded from active Docling cleaning profile |

All deprecated classes/functions continue to function — they are not removed. Invoking them emits a `WARNING`-level log.
