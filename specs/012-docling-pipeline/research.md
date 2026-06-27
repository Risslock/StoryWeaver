# Research: Docling Ingestion Pipeline (012)

*Phase 0 output — all NEEDS CLARIFICATION items resolved before design.*

---

## Docling Python API

**Decision**: Use `docling.document_converter.DocumentConverter` + `docling.chunking.HybridChunker` directly, as validated by the spike notebook (`notebooks/docling_spike.ipynb`).

**Rationale**: The spike confirmed correctness against ED4_Players_Guide (1439 chunks, 96.7% heading coverage, 0 image placeholders, 0 furniture lines, 86 structured tables). No integration gaps remain.

**Alternatives considered**: PyMuPDF4LLM (current baseline, retired) — spike showed 30× slower, 96 image placeholder chunks, no structured tables.

### DocumentConverter instantiation

```python
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.pipeline_options import PdfPipelineOptions

pipeline_opts = PdfPipelineOptions()
pipeline_opts.do_ocr = False
pipeline_opts.images_scale = 0.5
pipeline_opts.generate_page_images = False
pipeline_opts.generate_picture_images = False

converter = DocumentConverter(
    format_options={"pdf": PdfFormatOption(pipeline_options=pipeline_opts)}
)
result = converter.convert(str(pdf_path), raises_on_error=False)
# result.document → DoclingDocument
# result.errors   → list of errors (empty on success)
```

- First call downloads layout ML models to `~/.cache/docling` (~1–2 GB). Subsequent calls use cache.
- `raises_on_error=False` allows inspecting errors before aborting; pipeline should check `result.errors` and log + abort if non-empty.
- **Page-batch processing is required**: Docling's neural layout analysis is memory-intensive. `DoclingIngestor` MUST process the PDF in page-range batches and concatenate the resulting chunks. Default batch size: 10 pages (configurable via `KNOWLEDGE_DOCLING_PAGE_BATCH_SIZE`). Pages are 1-indexed: `converter.convert(..., page_range=(1, 10))`, `(11, 20)`, etc. Chunking runs on each batch's document object; chunks from all batches are concatenated before the quality gate.
- `HybridChunker` is constructed once and reused across page batches — tokenizer loading is expensive.

### HybridChunker instantiation

```python
from docling.chunking import HybridChunker
from transformers import AutoTokenizer

tokenizer = AutoTokenizer.from_pretrained("nomic-ai/nomic-embed-text-v1.5")
chunker = HybridChunker(tokenizer=tokenizer, max_tokens=512)
chunk_objects = list(chunker.chunk(result.document))
```

- `tokenizer` is required; must match the embedding model to keep chunk sizes coherent.
- `max_tokens=512` is appropriate for `nomic-embed-text-v1.5` (supports up to 8,192 tokens; 512 is the RAG sweet spot).
- Returns a list of chunk objects (not strings).
- Construct the chunker once and reuse across page batches — tokenizer loading is expensive.

### Chunk object schema

```python
chunk.text            # str: body text
chunk.meta            # DocMeta (Pydantic)
chunk.meta.headings   # list[str]: heading path, e.g. ["Chapter 5", "Elementalist", "Thread Weaving"]
                      # Empty list for root-level content; never None
chunk.meta.captions   # optional list — not used in this feature
```

`meta.headings` values from the spike were already plain text (no Markdown formatting in the `nomic-embed-text-v1` spike run). FR-008 still requires stripping `*`, `_`, `#`, `` ` `` as a safety measure for other PDFs.

---

## HuggingFace Inference API — Feature-Extraction (Embedding)

**Decision**: Implement `HuggingFaceEmbedFn` in `packages/rag/rag/knowledge/embedder.py` calling the HF Inference API feature-extraction endpoint.

**Rationale**: `OllamaEmbedFn` is the structural reference; the HF endpoint accepts the same list-of-strings input and returns a list of embedding vectors. No third-party SDK needed — `httpx` (already a dependency) suffices.

**Alternatives considered**: Using the `huggingface_hub` Python SDK — rejected, no existing SDK dependency; `httpx` already present and sufficient.

### Embedding model selection

**Preferred model (Ollama)**: `nomic-ai/nomic-embed-text-v1.5` — same model used for Ollama embeddings. Supports Matryoshka dimensionality reduction; target dimension is **256** (via `truncate_dim=256` in the Ollama embed request body). 256 dimensions reduce storage and query latency with minimal quality loss for dense retrieval.

**HF Inference API — candidate models** (all selectable via `KNOWLEDGE_EMBED_MODEL` with no code changes):

| Model | Dims | HF serverless | Notes |
|-------|------|--------------|-------|
| `sentence-transformers/all-MiniLM-L6-v2` | 384 | ✅ Confirmed | Most reliable free-tier option |
| `BAAI/bge-m3` | 1024 | Likely ✅ | Strong multilingual retrieval; MTEB top performer; larger response payload |
| `nomic-ai/nomic-embed-text-v1.5` | 768 | ⚠️ Unconfirmed | Requires `trust_remote_code`; serverless availability must be tested |

**Dimensionality note**: ChromaDB creates the collection dimension on first upsert. Switching embedding models requires clearing or renaming the collection — models with different output dims are not compatible with an existing collection.

**Recommendation**: Start with `BAAI/bge-m3` on HF (strong quality, likely available) or `nomic-embed-text-v1.5` on Ollama with `truncate_dim=256` for local development. Document in `.env.example` that `sentence-transformers/all-MiniLM-L6-v2` is the confirmed HF fallback if bge-m3 is unavailable.

### Endpoint details

```
POST https://api-inference.huggingface.co/models/{KNOWLEDGE_EMBED_MODEL}
Authorization: Bearer {HF_API_KEY}
Content-Type: application/json

Request body:  {"inputs": ["text chunk 1", "text chunk 2"]}
Response body: [[0.123, ...], [0.456, ...]]  ← list of embedding vectors (one per input)
```

### Rate-limit handling (HTTP 429)

**Decision**: Retry with exponential backoff (max 3 retries, initial delay 5s, doubling each attempt). If all retries exhausted, log ERROR with the failed batch index and raise `ProviderUnavailableError`. The pipeline's existing SQLite `chunks_processed` tracking means a re-run of `IngestionPipeline.run()` for the same document can resume from the last successfully stored batch — providing a manual "store state, retry later" path.

**Rationale**: HF free-tier 429s are typically transient (per-minute quota). Three retries with backoff resolve most transient bursts without operator intervention. If the quota is exhausted for the day, storing the `failed` status lets the operator re-run after the quota resets. Immediate abort would lose progress on multi-thousand-chunk documents.

**Alternatives considered**: Immediate abort — rejected (loses progress on large documents). Infinite retry — rejected (hangs ingestion indefinitely if the quota is truly exhausted).

- HF also uses `HF_TOKEN` for model hub access (Docling's gated model downloads). `HF_API_KEY` and `HF_TOKEN` may refer to the same token; the pipeline should set `HF_TOKEN = os.environ.get("HF_API_KEY")` when Docling initialises if gated models are needed. For the ED4_Players_Guide run in the spike, non-gated models were used, so this is a documentation note only.

---

## Existing Code Analysis

### Call sites where OllamaProvider / OllamaEmbedFn are hardcoded

| File | Line | Current code | Required change |
|------|------|-------------|-----------------|
| `packages/rag/rag/knowledge/pipeline.py` | 140–142 | `from llm.providers.ollama import OllamaProvider` / `enricher = ChunkEnricher(OllamaProvider(model=enrich_model))` | Use `get_knowledge_enrich_provider(enrich_model)` |
| `packages/rag/rag/knowledge/pipeline.py` | 136 | `enrich_model = os.environ.get("KNOWLEDGE_ENRICH_MODEL", settings.knowledge_enrich_model)` | Must be required — abort if absent (no settings fallback) |
| `packages/rag/rag/knowledge/retriever.py` | 57–62 | `from llm.providers.ollama import OllamaProvider` / `enricher = ChunkEnricher(OllamaProvider(model=llm_model))` | Use `get_knowledge_enrich_provider(llm_model)` |
| `packages/rag/rag/knowledge/embedder.py` | 49–55 | `get_embed_fn()` always returns `OllamaEmbedFn` | Become `get_knowledge_embed_fn()` (provider-aware) |

### extraction_mode metadata field

`extraction_mode` is stored in ChromaDB metadata from `config.extraction_mode` (pipeline.py:268). The Docling pipeline sets `config.extraction_mode = "docling"` before calling `run()`. Existing values `"text"` and `"vision"` remain valid for legacy and vision paths.

### BreadcrumbExtractor removal from active path

`pipeline.py:150–154` currently calls `BreadcrumbExtractor().extract(full_text, chunks, doc_title)` when `config.enable_breadcrumbs` is True. For the Docling path, this step is replaced: DoclingIngestor returns `(full_text, chunks, breadcrumbs)` where breadcrumbs come from `meta.headings`. The BreadcrumbExtractor call is skipped; the returned breadcrumbs are used directly.

### Quality gate applicability

`_apply_quality_gate()` in `pipeline.py` operates on `list[str]` (body text). After the Docling path assembles body chunks (without breadcrumb prefix — prefix is added in `_build_records`), the quality gate applies normally. No changes to `_apply_quality_gate()` are needed.

---

## Dependency status

| Package | Current status | Required action |
|---------|---------------|----------------|
| `docling` | Not in `packages/rag/pyproject.toml` | Add `"docling>=2.0.0"` |
| `transformers` | Not in `packages/rag/pyproject.toml` | Add `"transformers>=4.40"` (for AutoTokenizer) |
| `pymupdf4llm` | Present | Retain (deprecated, not removed) |
| `httpx` | Present in `packages/llm/` | Also needed in `packages/rag/` for `HuggingFaceEmbedFn`; verify it is listed |
