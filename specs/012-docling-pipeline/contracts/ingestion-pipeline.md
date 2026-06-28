# Contract: Knowledge Ingestion Pipeline (012)

*Public interfaces exposed by the knowledge ingestion system after the Docling adoption.*

---

## 1. IngestionPipeline.run()

**File**: `packages/rag/rag/knowledge/pipeline.py`

**Signature** (unchanged from feature 011):

```python
async def run(
    self,
    doc_id: str,            # UUID of the KnowledgeDocument record
    file_path: str,         # Absolute path to the source file
    format: str,            # "pdf" | "md"
    scope: str,             # "global" | "campaign"
    campaign_id: str | None,
    config: IngestionConfig | None = None,
) -> None
```

**IngestionConfig fields relevant to this feature**:

```python
@dataclass
class IngestionConfig:
    extraction_mode: str = "docling"     # "text" | "vision" | "docling" — NEW: "docling" added
    source_type: str = "rulebook"        # "rulebook" | "supplement" | "novel" | "handwritten_note"
    enable_breadcrumbs: bool = True      # Ignored for Docling path (breadcrumbs always populated)
    enable_contextual_summaries: bool = False
    access_level_default: str | None = None
```

**Caller responsibility**: Set `config.extraction_mode = "docling"` to use the Docling pipeline. The pipeline selects the provider and embed function automatically from env vars.

**Postconditions**:
- ChromaDB collection contains chunks with all required metadata fields (see [data-model.md](../data-model.md#chromadb-metadata-schema-updated))
- `extraction_mode` metadata field is `"docling"` for all chunks produced by this path
- `breadcrumb` metadata field is present on every chunk (empty string if `meta.headings` was empty)
- `original_text` is the C-effective format: `{breadcrumb}\n\n{body}` when breadcrumb is non-empty, else `{body}`
- SQLite `knowledge_documents` record has `ingestion_status="ready"` on success

**Error behaviour**: Raises `IngestionAbortError` on unrecoverable failures. Logs ERROR before raising. SQLite record has `ingestion_status="failed"` and `error_message` set.

---

## 2. ChromaKnowledgeRetriever.search()

**File**: `packages/rag/rag/knowledge/retriever.py`

**Signature** (unchanged):

```python
async def search(
    self,
    query: str,
    campaign_id: str,
    role: str,          # "gm" | "player"
    top_k: int = 8,
) -> list[KnowledgeChunk]
```

**Post-012 behaviour**: The enrichment LLM used for query expansion and reranking is now selected via `KNOWLEDGE_ENRICH_PROVIDER` factory instead of hardcoded `OllamaProvider`. `KnowledgeChunk` fields are unchanged.

**KnowledgeChunk schema** (returned by retriever):

```python
@dataclass
class KnowledgeChunk:
    chunk_id: str
    doc_id: str
    doc_title: str
    headline: str
    summary: str
    topic: str
    access_level: str           # "gm_only" | "player_visible"
    scope: str                  # "global" | "campaign"
    text: str                   # C-effective original_text — heading path + body, or body-only
    rrf_score: float
    breadcrumb: str             # " > "-joined heading path, or ""
    source_type: str            # "rulebook" | "supplement" | "novel" | "handwritten_note"
    extraction_mode: str        # "docling" for new chunks, "text" or "vision" for legacy
```

Note: `extraction_mode` is now returned as part of `KnowledgeChunk`. If the existing dataclass does not include it, add it (it is stored in ChromaDB metadata and available to the retriever).

---

## 3. Provider Factory Interfaces

**File**: `packages/rag/rag/knowledge/factory.py`

### get_knowledge_enrich_provider

```python
def get_knowledge_enrich_provider(model: str) -> LLMProvider:
    """
    Select the LLM provider for knowledge enrichment and query expansion/reranking.

    Reads:
        KNOWLEDGE_ENRICH_PROVIDER — required; "ollama" | "huggingface"
        HF_API_KEY               — required if KNOWLEDGE_ENRICH_PROVIDER=huggingface
        OLLAMA_BASE_URL          — used if KNOWLEDGE_ENRICH_PROVIDER=ollama

    Args:
        model: model name to use (caller reads from KNOWLEDGE_ENRICH_MODEL or KNOWLEDGE_LLM_MODEL)

    Raises:
        EnvironmentError: if any required env var is absent, blank, or unrecognised
    """
```

### get_knowledge_embed_fn

```python
def get_knowledge_embed_fn() -> OllamaEmbedFn | HuggingFaceEmbedFn:
    """
    Select the embedding function for knowledge ingestion and retrieval.

    Reads:
        KNOWLEDGE_EMBED_PROVIDER — required; "ollama" | "huggingface"
        KNOWLEDGE_EMBED_MODEL    — required; no code-level default
        HF_API_KEY               — required if KNOWLEDGE_EMBED_PROVIDER=huggingface
        OLLAMA_BASE_URL          — used if KNOWLEDGE_EMBED_PROVIDER=ollama

    Raises:
        EnvironmentError: if any required env var is absent, blank, or unrecognised
    """
```

---

## 4. ChromaDB Collection Schema

**Collection names** (unchanged):
- Global: `knowledge_global`
- Campaign-scoped: `knowledge_{campaign_id_no_hyphens}`

**Stored per document** (ChromaDB `upsert` call):
- `ids`: `list[str]` — `"{doc_id_hex}_{chunk_index:04d}"`
- `embeddings`: `list[list[float]]` — pre-computed; not registered on collection
- `documents`: `list[str]` — compound text for similarity search (breadcrumb + enrichment fields + body)
- `metadatas`: `list[dict]` — see [data-model.md](../data-model.md#chromadb-metadata-schema-updated)

---

## 5. .env.example Block

The `.env.example` file MUST document this block after this feature:

```bash
# ── Knowledge Pipeline — Provider Selection ───────────────────────────────────
# Required: select enrichment LLM and embedding providers
KNOWLEDGE_ENRICH_PROVIDER=ollama          # ollama | huggingface
KNOWLEDGE_EMBED_PROVIDER=ollama           # ollama | huggingface

# Required: model names (no code-level defaults — pipeline aborts if absent)
KNOWLEDGE_ENRICH_MODEL=llama3.2
KNOWLEDGE_EMBED_MODEL=nomic-ai/nomic-embed-text-v1.5   # Ollama: also pass truncate_dim=256

# Optional: Docling page-batch size (default 10; increase for speed, decrease for low-RAM)
# KNOWLEDGE_DOCLING_PAGE_BATCH_SIZE=10

# Required only when any provider is "huggingface":
# HF_API_KEY=hf_...

# ── HuggingFace configuration (comment out Ollama values above) ───────────────
# KNOWLEDGE_ENRICH_PROVIDER=huggingface
# KNOWLEDGE_EMBED_PROVIDER=huggingface
# KNOWLEDGE_ENRICH_MODEL=mistralai/Mistral-7B-Instruct-v0.3
#
# Embedding model options on HF Inference API (pick one):
# KNOWLEDGE_EMBED_MODEL=sentence-transformers/all-MiniLM-L6-v2   # 384-dim, confirmed serverless
# KNOWLEDGE_EMBED_MODEL=BAAI/bge-m3                               # 1024-dim, strong multilingual
# KNOWLEDGE_EMBED_MODEL=nomic-ai/nomic-embed-text-v1.5            # 768-dim (HF serverless availability unconfirmed)
# HF_API_KEY=hf_...
```
