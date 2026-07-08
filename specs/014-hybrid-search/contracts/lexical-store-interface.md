# Contract: SQLiteLexicalStore + Weighted-RRF Fusion

**Files**: `packages/rag/rag/knowledge/lexical_store.py` (new), `packages/rag/rag/knowledge/retriever.py` (modified)
**Purpose**: Define the lexical-index interface and exactly how it plugs into the existing RRF fusion loop

---

## `SQLiteLexicalStore` Interface

See [data-model.md](../data-model.md) for the full method signatures and FTS5 schema. Summary of the contract each method must uphold:

| Method | Contract |
|---|---|
| `ensure_table()` | Idempotent. Safe to call on every process start (mirrors `ChromaVectorStore`'s implicit `get_or_create_collection`). |
| `upsert(ids, texts, metadatas)` | Idempotent per `chunk_id` (delete-then-insert). Must not raise on an empty batch. Raises `ProviderUnavailableError` on unrecoverable SQLite errors, matching `ChromaVectorStore.upsert`'s exception contract so `retriever.py`/`pipeline.py` can catch both stores identically. |
| `query(query_text, scope, role, top_k)` | Returns `[]` (not an error) when the table has zero rows for `scope`, or when `query_text` tokenizes to zero terms (e.g., pure punctuation) — mirrors `ChromaVectorStore.query`'s `None`-on-empty-collection behavior, adapted to a list return type. Bounded to `top_k` rows, consistent with the "candidate pool size per signal before fusion must remain bounded" edge case. |
| `delete_by_doc(doc_id)` | Deletes all rows for `doc_id` regardless of scope. Safe to call for a `doc_id` with zero matching rows (no-op, no error) — mirrors `ChromaVectorStore.delete_by_doc`. |

## `ChromaKnowledgeRetriever.search()` — Fusion Contract

**Current behavior** (`retriever.py:158-167`, unchanged when `HYBRID_SEARCH_ENABLED=false`):

```python
for ranked in result_sets:                              # each ranked = one vector query × collection
    for rank, (chunk_id, meta, doc) in enumerate(ranked):
        rrf_scores[chunk_id] = rrf_scores.get(chunk_id, 0.0) + 1.0 / (rrf_k + rank + 1)
```

**New behavior when `HYBRID_SEARCH_ENABLED=true`**:

1. After building `result_sets` from vector queries (unchanged), append one additional ranked list per collection from `SQLiteLexicalStore.query(query, col_scope, role, top_k)` — using the *original* `query` string only (not the expanded alternatives; see [research.md](../research.md) Decision 3).
2. Track, per list, whether it is a `"vector"` or `"lexical"` source.
3. Accumulate with a per-list weight:

   ```python
   for signal, ranked in tagged_result_sets:              # signal: "vector" | "lexical"
       weight = vector_weight if signal == "vector" else keyword_weight
       for rank, (chunk_id, meta, doc) in enumerate(ranked):
           rrf_scores[chunk_id] = rrf_scores.get(chunk_id, 0.0) + weight / (rrf_k + rank + 1)
           matched_signals.setdefault(chunk_id, set()).add(signal)
   ```

4. `KnowledgeChunk.matched_signals` is populated from `sorted(matched_signals[chunk_id])` when building each candidate (same loop as today at `retriever.py:170-188`).
5. Everything downstream — `retrieval_k = min(top_k + 4, len(sorted_ids))`, the reranking call, and the final `candidates[:top_k]` truncation — is **unchanged**. `ChunkEnricher.rerank()` never sees `matched_signals` or raw scores; it only receives `_rerank_repr(c)` text snippets, exactly as today.

## Non-Goals (explicitly out of scope for this contract)

- No change to `ChunkEnricher.rerank()`'s signature or prompt.
- No change to `rrf_k` (`KNOWLEDGE_RRF_K`) — one fusion constant shared by both signals.
- No per-query-variant lexical expansion (Decision 3).
- No score normalization between BM25 and cosine-similarity scores — fusion happens purely on rank position via RRF, never on raw scores.
