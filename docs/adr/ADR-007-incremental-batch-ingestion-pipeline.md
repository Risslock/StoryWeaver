# ADR-007: Incremental Batch Ingestion Pipeline

**Date**: 2026-06-22
**Status**: Accepted
**Deciders**: StoryWeaver project (portfolio)
**Feature**: `005-rag-qa-system`

---

## Context

The initial ingestion pipeline for the Knowledge Q&A feature used four sequential phases over
the entire document:

```
Phase 1 — Extract:  file → all raw text chunks
Phase 2 — Enrich:  all chunks → LLM enrichment (headline/summary/topic/access_level)
Phase 3 — Embed:   all compound texts → single /api/embed HTTP request to Ollama
Phase 4 — Store:   all vectors → single ChromaDB upsert call
```

Two concrete problems surfaced during first-run testing:

1. **HTTP 400 from Ollama's `/api/embed` endpoint**: Sending the entire document's compound
   texts in a single request body exceeded Ollama's payload or context limits for the embedding
   model. For a 200-page rulebook producing ~80–120 chunks, the JSON request body can exceed
   several MB and the combined token count across all texts can exceed the model's context
   window. Ollama returns `HTTP Error 400: Bad Request` with no further detail.

2. **All-or-nothing persistence**: With embed and store deferred to the end, a failure at any
   point in Phase 3 or Phase 4 discards all enrichment work and leaves the document in
   `"processing"` status with zero queryable chunks. For a 200-page PDF that takes 8–10 minutes
   to enrich, this is a significant reliability and UX problem.

A secondary concern: a document is not queryable at all until Phase 4 completes. Users uploading
large rulebooks see no evidence of progress beyond the enrichment counter.

## Decision

**Replace the four sequential phases with a single incremental batch loop.**

For each batch of `KNOWLEDGE_ENRICH_BATCH_SIZE` chunks (default 5):
1. **Enrich** the batch (one LLM call via `ChunkEnricher.enrich_batch`).
2. **Embed** the batch (one `/api/embed` call with ≤5 compound texts).
3. **Upsert** the batch to ChromaDB immediately.
4. **Persist progress** — update `chunks_processed` in SQLite.

The document's chunk IDs remain globally deterministic via a `chunk_offset` parameter
(`{doc_id_hex}_{global_idx:04d}`), so confirmed-overwrite re-ingestion still targets the
correct IDs regardless of batch size.

```python
# New pipeline loop (simplified)
for batch_idx, batch in enumerate(batches):
    chunk_offset = batch_idx * batch_size
    enrichments = await enricher.enrich_batch(batch)
    ids, compound_texts, metadatas = self._build_records(..., chunk_offset=chunk_offset)
    embeddings = await embed_fn.embed(compound_texts)        # small request
    await self._store.upsert(collection_name, ids, embeddings, compound_texts, metadatas)
    await self._set_progress(doc_id, stored)                 # incremental DB write
```

## Rationale

| Option | Verdict | Reason |
|--------|---------|--------|
| Batch embed in fixed-size groups (keep separate phases) | ✗ Rejected | Fixes the 400 but does not address all-or-nothing persistence; adds a second batch-size config variable |
| Keep sequential phases; increase Ollama timeout | ✗ Rejected | Does not fix payload size limit; timeout increase is a workaround, not a fix |
| Incremental batch loop (this ADR) | ✓ Accepted | Fixes both problems with a single structural change; reuses the existing `KNOWLEDGE_ENRICH_BATCH_SIZE` for all three sub-operations; simplifies the pipeline class |
| Stream chunks one-by-one to ChromaDB | ✗ Rejected | Maximises ChromaDB write overhead (N individual upserts); batch enrichment already amortises LLM round-trips at the same granularity |

The incremental loop naturally bounds every Ollama request to `KNOWLEDGE_ENRICH_BATCH_SIZE`
texts (default 5). The same env var controls both enrichment and embedding batch size — no new
configuration surface. `KNOWLEDGE_ENRICH_BATCH_SIZE` can be tuned down if a model has a smaller
context window or up if throughput is the priority.

## Alternatives Considered

### Streaming embed via Ollama's `/api/embeddings` (singular, legacy endpoint)

The legacy `/api/embeddings` endpoint accepts a single `prompt` string and returns a single
vector. Calling it per-chunk with `asyncio.gather` would parallelise embedding but overload a
single Ollama instance (same problem as the concurrent enrichment fix in T030). Rejected in
favour of batched sequential calls that respect Ollama's single-threaded model runner.

### Pre-chunking size cap to avoid large compound texts

Reducing `KNOWLEDGE_MAX_CHUNK_TOKENS` would shrink individual compound texts. Rejected: the
problem is aggregate payload size across all chunks, not individual chunk size. A cap would
require aggressive truncation that degrades embedding quality.

## Consequences

- **`pipeline.py`**: `_enrich_with_progress` method removed. `run()` now contains the
  incremental loop directly. `_build_records` gains a `chunk_offset: int = 0` parameter.
- **Partial queryability**: chunks are available for retrieval after each batch completes.
  A 100-chunk document is ~50% queryable after half the batches have processed.
- **Failure resilience**: if ingestion fails at batch N, batches 0..N-1 are already in
  ChromaDB. The document is marked `"failed"` in SQLite, but partially-stored chunks remain
  retrievable. A confirmed-overwrite re-ingestion will overwrite them by chunk ID.
- **Progress accuracy**: `chunks_processed` in SQLite now reflects the count of chunks that
  have been enriched, embedded, **and stored** — not just enriched. This is more meaningful
  for the UI progress indicator.
- **No new dependencies**: change is confined to `packages/rag/rag/knowledge/pipeline.py`.

## Compliance

- Constitution Principle II (Provider Abstraction): ✅ `OllamaEmbedFn` and `ChromaVectorStore`
  remain behind their existing abstraction layers; this ADR does not change interfaces.
- Constitution Principle VI (Product-First): ✅ No new infrastructure; incremental persistence
  directly improves user-observable reliability and progress visibility.
- Constitution Principle VII (Explicit Failures): ✅ Failure at any batch now stores a
  descriptive `error_message` and marks the document `"failed"` rather than leaving it
  silently in `"processing"` with zero stored chunks.
- Constitution § Technology Stack Constraints: ✅ No new framework or infrastructure component
  introduced; this is an algorithmic change within an existing module.
