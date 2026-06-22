# Research: Game Knowledge Q&A (RAG)

**Date**: 2026-06-22 | **Feature**: `005-rag-qa-system`

---

## 1. PDF → Markdown Conversion

**Decision**: `pymupdf4llm`

**Rationale**:
- Converts PDF to GitHub-flavored Markdown with heading hierarchy preserved, tables rendered as GFM table syntax, and image bytes extractable for downstream inline captioning.
- Pure Python, Apache 2.0 licensed, no cloud dependency — satisfies local-first constraint (Principle IV).
- Significantly outperforms `pypdf` + `pdfplumber` on table fidelity and heading detection for structured rulebook PDFs.
- `marker-pdf` produces higher quality output for scanned PDFs but requires ~2 GB ML model downloads; overkill for text-based rulebooks.

**Alternatives considered**:
- `marker-pdf` — higher quality for scanned content; deferred as an optional `Ingestor` implementation swap behind the abstraction if quality proves insufficient.
- `docling` (IBM) — good quality but heavier dependency footprint; not necessary for MVP.
- `pypdf` + `pdfplumber` — poor table extraction; loses heading structure.

**Scanned/image-only PDFs**: Out of scope for MVP. `PdfIngestor` will detect image-only pages and emit a visible warning in the document status rather than silently producing empty chunks.

---

## 2. Image Handling

**Decision**: Inline vision-LLM captions; no file storage

**Rationale**:
- `pymupdf4llm` yields raw image bytes per page. These are passed to `LLMProvider` when a vision-capable model is configured.
- The generated description is inserted as a Markdown paragraph at the image's position before chunking — searchable with zero filesystem overhead.
- Falls back to `[Figure: page {p}, image {n}]` when no vision provider is available — always visible, never silent (Principle VII).
- Storing image files was rejected: adds filesystem I/O complexity, images can't render in the Gradio chat UI, text captions serve retrieval better than raw bytes.

---

## 3. Collection Topology (Two-Tier)

**Decision**: Global shared collection + per-campaign collection; queries merge both

**Rationale**:
- Rulebooks and sourcebooks (Earthdawn core book, companion volumes) apply to every campaign of that game system. Indexing them once in a shared `knowledge_global` collection avoids redundant PDF ingestion every time a GM starts a new campaign — which would take minutes per book.
- Campaign-specific content (house rules, session notes, faction lore, GM secrets) belongs in a scoped `knowledge_{campaign_id_hex}` collection so it remains isolated between campaigns.
- At query time, the retriever searches both `knowledge_global` and the active campaign's collection, merges all result sets, then applies RRF ranking and access-level filtering. From the user's perspective, this is transparent — they get answers from both sources without any manual configuration.

**Collection naming**:
- `knowledge_global` — shared rulebooks and sourcebooks
- `knowledge_{campaign_id_hex}` — campaign-scoped content

**Document scope field**: `KnowledgeDocument.scope` — `"global"` | `"campaign"`. Global documents have `campaign_id = NULL`.

**Future game-system extension**: If multiple game systems are added, the global collection name would become `knowledge_global_{game_system}` (e.g., `knowledge_global_earthdawn_4e`). For MVP with one game system, `knowledge_global` is sufficient.

**Alternative rejected**: Single collection with `campaign_id` + `scope` in metadata `where` filter — grows unboundedly, complicates bulk deletion, and creates cross-campaign isolation risk.

---

## 4. Semantic Chunking Strategy

**Decision**: Heading-based structural chunking with table-atomic enforcement and configurable size cap

**Rationale**:
- Earthdawn rulebooks use `##`/`###` headings for rules sections, chapters, and subsections — heading-based splitting aligns chunks with semantic units naturally.
- True "LLM decides every boundary" chunking is too expensive for MVP (one LLM call per boundary across a 500-page book).
- The LLM is reserved for **enrichment** per chunk — not for boundary detection.
- Table-atomic rule: a table and its preceding heading form one indivisible chunk. Stat blocks and progression tables are meaningless when split.
- Max chunk size: 800 tokens (configurable via env var). Oversized sections split at blank-line paragraph boundaries. 50-token overlap between adjacent chunks for context continuity.

**Alternatives considered**:
- Fixed-size sliding window: ignores semantic boundaries; produces incoherent chunks for tables and lists.
- Full LLM boundary detection: high quality but O(N) LLM calls; deferred as optional `Chunker` variant behind the abstraction.
- `langchain` / `llama-index` chunkers: large framework dependency; rejected per Principle III.

---

## 5. Structured LLM Output for Chunk Enrichment

**Decision**: Pydantic-AI `Agent` with `result_type=ChunkEnrichment` Pydantic model

**Rationale**:
- `pydantic-ai` is already a workspace dependency (`packages/agents/pyproject.toml`). Adding it to `packages/rag/pyproject.toml` introduces no new external library.
- `result_type=` gives fully validated, type-safe structured output from the LLM with no manual JSON parsing — pydantic-ai handles prompt construction, retries on parse failure, and model validation automatically.
- `ChunkEnrichment` model: `headline: str`, `summary: str`, `topic: str`, `access_level: Literal["gm_only", "player_visible"]`.
- Access level override: if the uploader set a document-level default, it replaces the LLM-inferred `access_level` field after validation, before indexing.
- The same pattern applies for query expansion: `result_type=QueryExpansion` (a model containing `list[str]` of alternative phrasings).

**Alternative considered**:
- Manual `LLMProvider.generate()` + JSON prompt + `json.loads()` + Pydantic validation: fragile (parse errors on malformed output). Superseded by pydantic-ai `result_type` pattern already used in `packages/agents/`.

---

## 6. Query Expansion

**Decision**: Multi-query — generate 3 alternative phrasings via pydantic-ai agent, retrieve for each collection, merge all result sets before RRF

**Implementation**:
```
original_query → pydantic-ai Agent → QueryExpansion([alt_1, alt_2, alt_3])
For each query in [original, alt_1, alt_2, alt_3]:
    search(knowledge_global) + search(knowledge_{campaign_id})
Merge all results by chunk_id → RRF → top-K for answer synthesis
```

**Alternatives considered**:
- HyDE: more powerful but adds a full LLM answer generation step before retrieval, doubling latency. Deferred.
- Step-back prompting: useful for narrow technical questions but adds prompt engineering effort without clear MVP benefit.

---

## 7. Re-ranking Strategy

**Decision**: RRF for initial candidate scoring, followed by LLM re-ranking on the candidate pool

**Formula (RRF)**: `score(chunk) = Σ 1 / (k + rank_i)` where k=60, `rank_i` is chunk's rank in result list i.

**Two-pass re-ranking**:
1. RRF merges all multi-query × multi-collection result sets into a candidate pool of `top_k × 2` chunks, scored by combined rank signal.
2. `ChunkEnricher.rerank(question, candidate_texts)` sends the candidates to the LLM, which returns a `RankOrder` JSON object — chunk indices (1-based) ordered most to least relevant to the question. The list is then trimmed to `top_k`.
3. Falls back to RRF order on `ProviderUnavailableError` or `ValidationError` — retrieval degrades gracefully without error.

**Rationale**:
- RRF is fast and requires no extra model. LLM re-ranking on top adds query-aware relevance judgment beyond embedding similarity.
- The extra LLM round-trip (~1–3 s for a local llama3 model) is within the 30 s SC-001 budget for typical questions.
- Cross-encoder re-rankers (~80 MB model, ~200–500 ms) remain deferred as an optional `KnowledgeRetriever` variant — they offer higher precision but add a non-trivial download and latency.

---

## 8. Access-Level Filtering

**Decision**: ChromaDB `where` clause filter applied at retrieval time per collection

**Implementation**:
- Chunks stored with `access_level` in metadata: `"gm_only"` | `"player_visible"`.
- Player queries: `where={"access_level": {"$eq": "player_visible"}}` applied to both collections.
- GM queries: no `where` filter.
- Filter applied inside ChromaDB before scoring — fast, no post-processing.

---

## 9. Background Ingestion in Gradio

**Decision**: `asyncio.create_task` for non-blocking pipeline; SQLite status polling via `gr.Timer`

**Implementation**:
- `asyncio.create_task(pipeline.run(...))` launches ingestion without blocking the UI event loop.
- Pipeline updates `KnowledgeDocument.ingestion_status` in SQLite: `pending → processing → ready` (or `failed` with error message).
- `gr.Timer(value=5)` in the document list polls the DB every 5 seconds and refreshes the table.
- Stale detection: if `updated_at` is >15 minutes old and status is still `processing`, UI displays "Ingestion stalled — restart may be required." (Principle VII).

**Alternative rejected**: External task queue (Celery, RQ) — unnecessary infrastructure complexity for MVP (Principle VI).

---

## 10. Duplicate Document Detection

**Decision**: Title-based uniqueness per scope (global or campaign); confirmed overwrite re-ingests

**On confirmed overwrite**:
1. Delete all ChromaDB chunk IDs prefixed with `{doc_id}_` from the relevant collection.
2. Reset `KnowledgeDocument.ingestion_status` to `processing`.
3. Dispatch new ingestion task.

File-hash uniqueness was rejected: users may upload revised versions of a same-named document.

---

## 11. Incremental Batch Ingestion (ADR-007)

**Problem observed**: Ollama's `/api/embed` endpoint returns `HTTP 400: Bad Request` when sent the compound texts for an entire document in a single request. A 100-chunk PDF produces a request body of several MB whose total token count across all texts exceeds the embedding model's context window limit.

**Decision**: Incremental batch loop — see [ADR-007](../../docs/adr/ADR-007-incremental-batch-ingestion-pipeline.md) for the full analysis and alternatives considered.

**Summary**: each `/api/embed` call now carries at most `KNOWLEDGE_ENRICH_BATCH_SIZE` texts (default 5). The same batch boundary is used for enrichment, embedding, and ChromaDB upsert, so the document is partially queryable after each batch rather than only after the entire document is processed.

---

## 12. Custom Embedding Function (`embedder.py`)

**Decision**: Custom `OllamaEmbedFn` class instead of ChromaDB's built-in `OllamaEmbeddingFunction`

**Rationale**:
- ChromaDB's built-in `OllamaEmbeddingFunction` moved from `chromadb.utils.embedding_functions` to a separate `chromadb[ollama]` optional extra between versions 0.4 and 0.5. Depending on it creates a brittle transitive dependency that breaks silently on version bumps.
- `OllamaEmbedFn` in `packages/rag/rag/knowledge/embedder.py` calls Ollama's `/api/embed` endpoint directly via `urllib.request` (Python stdlib — no extra install required).
- It implements `__call__(input: list[str]) -> list[list[float]]` matching ChromaDB's embedding function protocol, so it is passed as `embedding_function=` to `get_or_create_collection` for the retrieval (read) path.
- For the ingestion (write) path, `OllamaEmbedFn.embed(texts)` pre-computes vectors before calling `col.upsert(embeddings=[...])` — ChromaDB receives pre-computed vectors and does not embed again.

**Split-embed consistency**: Both paths use the same `KNOWLEDGE_EMBED_MODEL` env var (default `nomic-embed-text`) and `OLLAMA_BASE_URL`. Changing the model invalidates the existing vector store (embeddings are not cross-model compatible) — this is an operator responsibility documented in quickstart.md.

**Alternatives rejected**:
- `chromadb[ollama]` optional extra: requires declaring an optional dependency and breaks if `chromadb` drops or renames the extra.
- `sentence-transformers` local embedding: adds ~500 MB model download; overkill for MVP.
