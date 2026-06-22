# Implementation Plan: Game Knowledge Q&A (RAG)

**Branch**: `005-rag-qa-system` | **Date**: 2026-06-22 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/005-rag-qa-system/spec.md`

## Summary

A two-tier RAG knowledge base that lets GMs and players ask natural-language questions about game rules, lore, and world content — and receive synthesized answers citing the exact source passages. A shared `knowledge_global` ChromaDB collection holds rulebooks and sourcebooks indexed once for all campaigns; a per-campaign collection holds campaign-specific notes and lore. GMs ingest PDF rulebooks (converted to Markdown with table preservation and inline image descriptions) or Markdown notes; players contribute Markdown files. The pipeline enriches every chunk with LLM-generated metadata (headline, summary, topic, access level) validated via Pydantic models; access levels are inferred per-chunk by the LLM with a document-level default override set at upload time. Retrieval uses multi-query expansion (3 alternative phrasings) and Reciprocal Rank Fusion (RRF) across both collections. Embeddings use `nomic-embed-text` via Ollama through ChromaDB's `OllamaEmbeddingFunction`. The Gradio UI provides a Q&A chat pane on both dashboards, plus upload/management (GM: PDF + MD; player: MD only), with real-time ingestion status via DB polling.

## Technical Context

**Language/Version**: Python 3.11+

**Primary Dependencies**:
- `chromadb>=0.4` — vector store (already in `packages/rag/pyproject.toml`)
- `pymupdf4llm` — PDF → Markdown conversion with table extraction and image byte extraction (Apache 2.0); **new, add to `packages/rag/pyproject.toml`**
- `pydantic-ai` — structured Pydantic model validation of LLM outputs (`ChunkEnrichment`, `QueryExpansion`); already a workspace dependency, **add to `packages/rag/pyproject.toml`**
- `storyweaver-llm` — text generation for enrichment, query expansion, and answer synthesis (existing abstraction)
- `gradio>=4.0` — UI (existing)
- `storyweaver-core` — ORM models, SQLite backend

**Storage**:
- SQLite (existing) — new `knowledge_documents` table for document registry and ingestion status
- ChromaDB persistent store at `./data/chroma` — two-tier collections:
  - `knowledge_global` — shared rulebooks/sourcebooks, indexed once for all campaigns
  - `knowledge_{campaign_id_hex}` — campaign-specific notes and lore
- Both collections created with `OllamaEmbeddingFunction(model_name="nomic-embed-text", url=OLLAMA_BASE_URL)` — **not** ChromaDB's default `all-MiniLM-L6-v2` embedding. Existing `RulesRetriever` and `CharacterRetriever` use the ChromaDB default; the knowledge collections use Ollama embeddings via a separate collection configuration. The two embedding spaces are not mixed.

**Testing**: pytest + pytest-asyncio (existing); harness evals in `harness/knowledge_qa/`

**Target Platform**: Local desktop (same as existing app — no new deployment requirements)

**Performance Goals**:
- Q&A answer with citations: ≤30 seconds end-to-end (SC-001)
- PDF ingestion fully queryable: ≤10 minutes for typical 200-page rulebook (SC-002)
- Markdown ingestion fully queryable: ≤2 minutes (SC-003)

**Constraints**:
- No FastAPI or separate backend service (constitution Principle VI)
- Local-only by default; vector store and LLM provider swappable via env var (Principle II, IV)
- No new auth stack; role determined from `CampaignSession.role` (existing mock auth)
- IP compliance: chunks and inline captions only; raw original content not redistributed
- Background ingestion via `asyncio.create_task`; status polled from SQLite via `gr.Timer`

**Scale/Scope**: Two-tier retrieval (global + campaign); MVP targets ≥3 documents total, up to ~500-page PDFs. Global rulebooks shared across all campaigns with no re-ingestion cost.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Principle | Status | Notes |
|---|---|---|
| I. Spec-Driven | ✅ Pass | Spec + clarifications complete in `specs/005-rag-qa-system/` |
| II. Provider Abstraction | ✅ Pass | `KnowledgeRetriever` and `Ingestor` behind ABCs; vector store and LLM swappable via env var |
| III. Package Isolation | ✅ Pass | New `knowledge/` sub-module inside existing `packages/rag/`; no unjustified new top-level package |
| IV. Local-First | ✅ Pass | ChromaDB local persistent; Ollama LLM; no mandatory cloud path |
| V. Harness-Driven Quality | ✅ Pass | Harness evals required before milestone; see quickstart.md |
| VI. Product-First | ✅ Pass | No new auth; mock session role for access filter; Gradio-only |
| VII. Placeholder-First | ✅ Pass | Both new tabs render visible placeholder before real logic is wired |
| IP Compliance | ✅ Pass | Chunks + LLM-generated captions stored; originals not redistributed |

## PDF Content Extraction Strategy

Rulebook PDFs contain three content types that require distinct handling:

### Tables (stat blocks, talent circles, attribute progressions)
- `pymupdf4llm` converts tables to GitHub-flavored Markdown table syntax automatically.
- The chunker treats tables as **atomic units** — a table is never split across chunk boundaries.
- A heading immediately preceding a table is included in the same chunk (heading + table = one chunk).
- Very large standalone tables get their own dedicated chunk with an LLM-generated headline.

### Images (maps, character art, diagrams, rule illustrations)
- `pymupdf4llm` extracts image bytes per page. The `PdfIngestor` accepts an optional `image_captioner: Callable[[bytes], str] | None` parameter.
- When provided, the callable is invoked per image to produce a short description; the description is **inserted as a Markdown paragraph at the image's position** before chunking — no image files are stored.
- When `None` (default), the system emits `[Figure: page {p}, image {n}]` — always visible, never silent (Principle VII).
- The existing `LLMProvider` interface (`packages/llm/llm/interface.py`) only accepts `str` prompts and has no multi-modal path. Rather than extend the interface now, the image captioner is injected as a plain async callable at construction time. A concrete Ollama vision helper function can be added to `packages/llm/` in a future spec when multi-modal models are validated. For MVP, the placeholder fallback is sufficient.
- This keeps the module lightweight: images produce searchable text, no filesystem I/O beyond the PDF itself.

### Plain Text and Headings
- Heading-based splitting: each `##` / `###` section boundary triggers a new candidate chunk.
- Chunks are bounded by a configurable max token length (default 800 tokens); oversized sections split at paragraph breaks.
- ~50-token overlap between adjacent chunks preserves cross-boundary context.

## Structured Output Pattern

LLM calls that must return structured data (chunk enrichment, query expansion) use the following pattern to avoid fragile text parsing:

1. The `LLMProvider.generate()` call uses a prompt that instructs the model to respond with valid JSON matching a defined schema.
2. The response string is parsed with `Model.model_validate_json(raw)` (Pydantic v2).
3. On `ValidationError`, the call is retried once with a corrective prompt. If it fails again, a safe fallback is used (e.g. `access_level="player_visible"`, empty `summary`).

This approach reuses the existing `LLMProvider` abstraction (Principle II) while benefiting from Pydantic's validation and type-safety. The `pydantic-ai` dependency is added to `packages/rag/pyproject.toml` to provide the Pydantic models used as result schemas (`ChunkEnrichment`, `QueryExpansion`).

**Models** (defined in `packages/rag/rag/knowledge/interface.py`):

```python
class ChunkEnrichment(BaseModel):
    headline: str                                    # ≤80 chars
    summary: str                                     # 1–2 sentences
    topic: str                                       # e.g. "combat/initiative"
    access_level: Literal["gm_only", "player_visible"]

class BatchEnrichment(BaseModel):
    chunks: list[ChunkEnrichment]                    # N enrichments in a single LLM call

class QueryExpansion(BaseModel):
    alternatives: list[str]                          # exactly 3 items

class RankOrder(BaseModel):
    order: list[int]                                 # 1-based chunk indices, most → least relevant
```

**Batch enrichment**: Instead of one LLM call per chunk (`enrich_chunk`), `ChunkEnricher.enrich_batch(texts)` sends up to `KNOWLEDGE_ENRICH_BATCH_SIZE` chunks (default 5, env-configurable) in a single LLM call returning a `BatchEnrichment` JSON response. Falls back to per-chunk enrichment if the batch response fails validation. This saves N−1 LLM round-trips per document.

**LLM re-ranking**: After RRF produces a candidate pool of `top_k × 2` chunks, `ChunkEnricher.rerank(question, chunks)` calls the LLM to produce a `RankOrder` — chunk indices sorted by relevance to the question. The re-ranked list is trimmed to `top_k`. Falls back to RRF order on `ProviderUnavailableError` or `ValidationError`. This adds one LLM call per Q&A query; the 30 s SC-001 budget includes this call.

## Ingestion Pipeline Design

See **[ADR-007](../../docs/adr/ADR-007-incremental-batch-ingestion-pipeline.md)** for the full decision record.

The pipeline processes each document in a single incremental loop. All chunks are extracted upfront (to establish the total count for the progress indicator), then processed batch-by-batch:

```
Phase 1 — Extract (once):  file → all raw text chunks

For each batch of KNOWLEDGE_ENRICH_BATCH_SIZE chunks:
  Phase 2 — Enrich:  batch → LLM → ChunkEnrichment objects
  Phase 3 — Embed:   compound texts → OllamaEmbedFn → float vectors
  Phase 4 — Store:   upsert batch to ChromaDB immediately
  → persist chunks_processed to SQLite
```

**Why incremental**: a single all-at-once `/api/embed` request for a 100-chunk document exceeds Ollama's payload/context limits and returns HTTP 400. Incremental batching keeps each embed request to `KNOWLEDGE_ENRICH_BATCH_SIZE` texts (default 5), well within limits. As a side effect, chunks become queryable batch-by-batch during ingestion rather than only after the entire document is stored.

**Chunk ID determinism**: `{doc_id_hex}_{global_idx:04d}` where `global_idx = batch_offset + local_batch_position`. Changing batch size does not alter chunk IDs; confirmed-overwrite re-ingestion targets the same IDs.

**Failure resilience**: if ingestion fails mid-document, batches already stored remain in ChromaDB and are queryable. The document is marked `"failed"` with a descriptive `error_message`; a confirmed-overwrite re-ingestion overwrites all chunks by ID.

## Embedding Architecture

ChromaDB's built-in `OllamaEmbeddingFunction` has moved across package versions and requires an explicit sub-package install in `chromadb >= 0.5`. To avoid a brittle transitive dependency, the implementation uses a custom `OllamaEmbedFn` in `packages/rag/rag/knowledge/embedder.py` that calls Ollama's `/api/embed` endpoint directly via `urllib.request` (stdlib-only, no extra install).

**Pre-computed embeddings strategy** — both paths pre-compute vectors via `OllamaEmbedFn` and pass them directly to ChromaDB. No embedding function is ever registered on a collection, avoiding ChromaDB 0.5+ protocol requirements (`is_legacy`, `create_collection_configuration`) that break custom embedding classes.

| Path | Embedding | ChromaDB call |
|---|---|---|
| **Ingestion (write)** | `OllamaEmbedFn.embed(texts)` pre-computes vectors for the whole batch | `ChromaVectorStore.upsert(embeddings=[...])` — no embedding function on the collection |
| **Retrieval (read)** | `OllamaEmbedFn.embed([query])` pre-computes the query vector | `ChromaVectorStore.query(query_embeddings=[vec], ...)` — no embedding function on the collection |

Both paths must use the same `KNOWLEDGE_EMBED_MODEL` and `OLLAMA_BASE_URL` or retrieval quality degrades silently. `ChromaVectorStore` (`vector_store.py`) centralises client initialisation and `upsert`/`query`/`delete_by_doc` async helpers shared by `pipeline.py` and `retriever.py`.

## Project Structure

### Documentation (this feature)

```text
specs/005-rag-qa-system/
├── plan.md              # This file
├── research.md          # Phase 0 — technology decisions
├── data-model.md        # Phase 1 — entities and DB schema
├── quickstart.md        # Phase 1 — validation guide
├── contracts/
│   └── knowledge-qa-ui.md   # Phase 1 — UI contract
└── tasks.md             # Phase 2 output (/speckit-tasks)
```

### Source Code (repository root)

```text
packages/rag/
├── pyproject.toml                   # add pymupdf4llm and pydantic-ai dependencies
└── rag/
    └── knowledge/
        ├── __init__.py
        ├── interface.py             # KnowledgeRetriever ABC, KnowledgeChunk dataclass, ChunkEnrichment, QueryExpansion, BatchEnrichment, RankOrder
        ├── enricher.py              # LLM chunk enrichment (single + batch), LLM re-ranking, query expansion
        ├── chunker.py               # Heading-based MD splitter, table-atomic + image inline
        ├── ingestor.py              # Ingestor ABC + PdfIngestor + MarkdownIngestor
        ├── embedder.py              # Custom OllamaEmbedFn (replaces ChromaDB built-in; see §Embedding Architecture)
        ├── pipeline.py              # Orchestrator: extract all → (enrich → embed → store) per batch; incremental SQLite status tracking (see ADR-007)
        ├── retriever.py             # ChromaDB KnowledgeRetriever with multi-query, RRF, LLM re-ranking, access filter
        └── vector_store.py          # ChromaVectorStore wrapper (shared by pipeline write path and retriever read path)

packages/core/
└── core/
    ├── models.py                    # Add KnowledgeDocument ORM model
    └── migrations/versions/
        └── 0005_knowledge_documents.py

apps/web/
├── pages/
│   ├── gm/
│   │   └── knowledge_qa.py          # GM tab: Q&A chat + PDF & MD upload + status list
│   └── player/
│       └── knowledge_qa.py          # Player tab: Q&A chat + MD upload only
├── services/
│   └── knowledge.py                 # Bridge: background ingest dispatch, status queries
└── app.py                           # Wire new tabs into GM and player Tabs

harness/
└── knowledge_qa/
    ├── test_ingestion.py             # Eval: ingest produces expected chunk count and metadata
    ├── test_retrieval.py             # Eval: Q&A accuracy, RRF ranking, access filter enforcement
    ├── test_integration.py           # NEW — three live-Ollama integration flows (Phase 10)
    └── fixtures/
        ├── sample_rules.md           # Plain rules text for ingestion tests
        └── sample_gm_only.md         # GM-only content for access-filter tests

packages/rag/tests/knowledge/
    └── test_embedder.py              # Unit tests for OllamaEmbedFn (no Ollama required)
```

---

## Phase 10: Integration Test Design

**Added**: 2026-06-22 | **Branch**: `005-rag-qa-system`

Existing harness tests (`test_ingestion.py`, `test_retrieval.py`) rely entirely on mocked LLM and ChromaDB. This phase adds **three live-Ollama integration tests** in `harness/knowledge_qa/test_integration.py` that exercise the real stack end-to-end.

### Guiding Constraints

- **Ollama skip guard**: All three tests require Ollama to be running with `nomic-embed-text` (and at least one text model for Test 3). Tests are automatically skipped if Ollama is unreachable — a `pytest.fixture(scope="module")` named `ollama_available` calls `GET /api/tags` on `OLLAMA_BASE_URL`; a reachable-but-model-missing scenario fails with a `ProviderUnavailableError` (verifying Principle VII).
- **ChromaDB isolation**: A `tmp_path`-scoped pytest fixture creates a fresh directory per test module. `ChromaVectorStore(chroma_path=tmp_chroma)` directs all reads and writes there — the production `./data/chroma` directory is never touched.
- **SQLite isolation**: `IngestionPipeline._get_doc_title` and `_set_status/_set_progress` hit SQLite via the module-level `_backend`. Tests patch these three private helpers with `AsyncMock` stubs — the helpers return a fixed title and silently no-op on status writes. This decouples Ollama integration from database state without requiring a live database.
- **Deterministic fixture content**: `sample_rules.md` contains a short Earthdawn rules section with the phrase "DEX step" (unique enough that a targeted query will reliably retrieve it). This phrase is the retrieval oracle for Test 2.

### Test 1 — Ingestion Flow: MD → chunks → embeddings → ChromaDB

**File**: `harness/knowledge_qa/test_integration.py::TestIngestionFlow`

**What it exercises**:
- `MarkdownIngestor.ingest()` — file read and `MarkdownChunker` splitting
- `ChunkEnricher.enrich_batch()` — real LLM call producing `ChunkEnrichment` objects
- `OllamaEmbedFn.embed()` — real `/api/embed` call producing float vectors
- `ChromaVectorStore.upsert()` — writes to temp ChromaDB collection
- `KnowledgeDocument` metadata stored correctly in each chunk

**Assertions**:
```
collection.count() >= 1
for each chunk id:
    metadata contains: doc_id, doc_title, headline, summary, topic, access_level, scope, original_text
    access_level in {"gm_only", "player_visible"}
    headline is not empty
```

**Fixture requirements**: `ollama_available`, `tmp_chroma`, patched `_get_doc_title` / `_set_status` / `_set_progress`

---

### Test 2 — Retrieval Flow: query text → embedding → ChromaDB search → KnowledgeChunks

**File**: `harness/knowledge_qa/test_integration.py::TestRetrievalFlow`

**Depends on**: ingestion from Test 1 (same `tmp_chroma` fixture, module scope)

**What it exercises**:
- `ChromaKnowledgeRetriever._get_collection()` — opens temp collection with `OllamaEmbedFn`
- `OllamaEmbedFn.__call__()` — real Ollama embedding of query text
- `col.query(query_texts=[q], ...)` — ChromaDB cosine similarity search
- Multi-query expansion via `ChunkEnricher.expand_query()` — real LLM call
- RRF merge and `ChunkEnricher.rerank()` — real LLM re-ranking call
- Returns `list[KnowledgeChunk]` with `rrf_score > 0`

**Assertions**:
```
len(chunks) >= 1
chunks[0].rrf_score > 0
"dex step" in chunks[0].text.lower()   # known phrase from sample_rules.md
chunks[0].headline is not empty
chunks[0].doc_title == "Sample Rules"
```

**Query**: `"How does initiative work in combat?"` — targets the DEX step passage in `sample_rules.md`.

---

### Test 3 — End-to-End: LLM synthesises answer from retrieved knowledge

**File**: `harness/knowledge_qa/test_integration.py::TestEndToEndQA`

**Depends on**: Test 2 (same `tmp_chroma` fixture, module scope — assumes chunks already ingested)

**What it exercises**:
- `services/knowledge.ask_question()` full code path
- `ChromaKnowledgeRetriever.search()` (real Ollama embedding + ChromaDB query)
- `OllamaProvider.generate()` — real LLM synthesis call with retrieved context
- Citation building and `KnowledgeChunk` list returned alongside answer

**Assertions**:
```
len(answer) > 0
"couldn't find" not in answer.lower()      # FR-011 must not fire when content exists
len(chunks) >= 1                            # at least one citation
chunks[0].doc_title is not empty
```

**Query**: `"What step is used for initiative?"` — answerable only from ingested content.

---

### Test Architecture Summary

```text
harness/knowledge_qa/test_integration.py

Module-scoped fixtures:
  ollama_available   — GET /api/tags → skip if unreachable
  tmp_chroma         — tmp_path_factory.mktemp("chroma")
  ingested_doc_id    — uuid4 for the test document row

Per-test class:
  TestIngestionFlow  — patches _get_doc_title/_set_status/_set_progress; runs pipeline
  TestRetrievalFlow  — depends on TestIngestionFlow having run in same module session
  TestEndToEndQA     — patches _backend in services.knowledge; uses same tmp_chroma
```

### Embedding Consistency Guarantee

Both the pipeline write path (`embed_fn` passed to `upsert`) and the retriever read path (`embed_fn` passed to `collection`) use `get_embed_fn()`, which reads `KNOWLEDGE_EMBED_MODEL` from the environment. The integration tests inherit whatever model is configured — if the model changes between a write and a read within one test session, the `OllamaEmbedFn.name` mismatch will cause ChromaDB to raise a `ValueError`, surfacing the problem before it silently corrupts retrieval results.

## Complexity Tracking

No constitution violations. Adding `knowledge/` as a sub-module of `packages/rag/` is justified because it shares the existing `Retriever` ABC and ChromaDB dependency already declared in `packages/rag/pyproject.toml`. No new top-level package is introduced.