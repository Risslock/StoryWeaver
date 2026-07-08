# Research: Hybrid Search for Knowledge Retrieval

**Feature**: 014-hybrid-search | **Date**: 2026-07-07

No `NEEDS CLARIFICATION` markers remain in the Technical Context — this feature integrates entirely with existing, already-researched infrastructure (`packages/rag/`, `packages/core/`, `packages/storage/`). The decisions below resolve the implementation-level choices the spec deliberately deferred to planning.

---

## Decision 1: Lexical index technology — SQLite FTS5 (built-in `bm25()`)

**Decision**: Use a SQLite FTS5 virtual table with the `porter unicode61` tokenizer. Rank via FTS5's native `bm25(table)` auxiliary function.

**Rationale**:
- `packages/rag/pyproject.toml` has no BM25/full-text dependency today (`rank_bm25`, `whoosh`, etc. are absent); `sqlite3`/`aiosqlite` are already dependencies, and FTS5 is compiled into Python's stdlib `sqlite3` module on all supported platforms — zero new dependencies (Constitution IV: Local-First).
- FTS5's `bm25()` function implements the actual BM25 ranking formula (term frequency, inverse document frequency, length normalization) — this **is** BM25, not an approximation of it, satisfying the requirement to use BM25 specifically.
- The existing storage layer (`packages/storage/storage/sqlite/adapter.py`) already manages a SQLAlchemy + `aiosqlite` connection to the same database file; the lexical table lives in that same database rather than introducing a second storage engine.
- Porter stemming improves recall for morphological variants of rule/item names (e.g., "Sturdy" / "Sturdiness") without needing a separate stemming library.

**Alternatives considered**:
- `rank-bm25` (pure-Python `BM25Okapi`): explicit, resume-visible "I wrote BM25 scoring" code, but has no built-in persistence — the corpus would need to be loaded into memory (or a custom on-disk cache built) on every process start, which is unnecessary complexity for a project that already has a working embedded-database story. Rejected in favor of FTS5's built-in, persistent, already-BM25 ranking.
- Elasticsearch/OpenSearch: introduces a new external service dependency, violating Constitution IV (Local-First) for zero added benefit at this project's scale (hundreds to low thousands of chunks).
- One FTS5 virtual table per collection (mirroring ChromaDB's per-collection model): rejected as unnecessary complexity — a single table with `scope`/`campaign_id` as `UNINDEXED` filter columns achieves identical isolation with one schema to migrate/backfill instead of one per campaign.

---

## Decision 2: Weighted RRF fusion — extend the existing formula, don't replace it

**Decision**: Extend the existing RRF accumulation loop (`retriever.py:158-167`) with a per-result-list weight multiplier:

```
rrf_scores[chunk_id] += weight_for_this_list * (1.0 / (rrf_k + rank + 1))
```

Every existing vector query list (one per query-expansion alternative × collection) gets `vector_weight`. Each lexical query list (one per collection — lexical search runs once per collection on the *original* query only, not the expanded alternatives) gets `keyword_weight`. Default: `vector_weight = 1.0`, `keyword_weight = 1.0` — i.e., identical treatment to how today's multiple vector-query lists already combine with implicit weight 1 each. This is what the spec's assumption ("equal contribution... consistent with the equal-weighting behavior of the existing multi-query RRF fusion") calls for: no renormalization, lexical lists simply join the same undifferentiated pool of ranked lists that vector lists already occupy.

**Rationale**:
- Preserves exact current behavior when `HYBRID_SEARCH_ENABLED=false` (no lexical lists are added, weights don't matter) and when weights are left at their 1.0 defaults with hybrid enabled (the fusion math is unchanged from today's for every list already present).
- Reuses the existing `rrf_k` constant (`KNOWLEDGE_RRF_K`, default 30) — one fusion knob, not two independent ones for vector vs. lexical.
- A single scalar weight per signal (rather than per-query-variant weights) keeps the config surface small and matches the "adjustable via configuration" requirement (FR-005) without overfitting to a specific weighting scheme.

**Alternatives considered**:
- Single `alpha` blend parameter (`keyword_weight = alpha`, `vector_weight = 1 - alpha`, `alpha ∈ [0,1]`): rejected because it forces the two signals to always sum to a constant, which doesn't match "equal contribution by default" as cleanly (0.5/0.5 is not equivalent to today's un-weighted 1.0-per-list fusion — it would halve every existing vector list's contribution the moment hybrid search is turned on, changing today's baseline behavior even in the equal-weight case).
- Score-based fusion (weighted sum of normalized BM25 + cosine-similarity scores instead of RRF): rejected — BM25 and cosine-similarity scores are not on comparable scales without additional normalization/calibration work, whereas RRF only needs rank position and is what the project already uses and the spec explicitly calls out as the integration point (Assumptions section of spec.md).

**Validation rule** (User Story 3 AC3 — invalid config must fail loudly): both `HYBRID_SEARCH_KEYWORD_WEIGHT` and `HYBRID_SEARCH_VECTOR_WEIGHT` must be `> 0.0`; a `@model_validator` on `Settings` raises at startup (not silently defaulting) if either is `<= 0`.

---

## Decision 3: Lexical retrieval uses the original query only, not the expanded alternatives

**Decision**: `ChunkEnricher.expand_query()`'s paraphrase alternatives are used for vector search only. Lexical search runs once per collection against the user's original query text.

**Rationale**: Query expansion exists specifically to catch *semantic* variants that literal keyword matching would miss — that's the reason vector search needs it. Running lexical search against paraphrased alternatives would dilute literal-term matching (the whole point of adding a lexical signal per User Story 1) and roughly double the lexical work for no recall benefit, since FTS5 already does stemming.

---

## Decision 4: Sync strategy for new/updated/deleted chunks — hook the existing single upsert point

**Decision**: `IngestionPipeline._build_records()` (`pipeline.py:273-328`) already builds one `(ids, compound_texts, metadatas)` tuple per batch before the single `self._store.upsert(...)` call at `pipeline.py:222`. Add a parallel `self._lexical_store.upsert(...)` call immediately after it, using `original_text` (not the enrichment-augmented `compound` embedding text) as the indexed text — the same field already used to populate `KnowledgeChunk.text` at query time. Mirror `delete_chunks_by_doc` (`retriever.py:59-67`) to delete from both stores.

**Rationale**: There is exactly one write path today (batch-at-a-time upsert during ingestion) and exactly one delete path (`delete_by_doc`, keyed on `doc_id` + collection). Hooking both keeps the two indexes trivially in sync (FR-006) without introducing a second ingestion pipeline or an eventual-consistency mechanism. Indexing `original_text` rather than the LLM-enriched `compound` text means lexical search matches literal document text — this is what User Story 1 wants ("the chunk containing the literal term"), whereas `compound` mixes in headline/summary paraphrase that could dilute exact-term matching.

---

## Decision 5: Backfilling pre-existing collections — explicit CLI migration (per spec clarification)

**Decision**: `packages/rag/rag/knowledge/backfill_lexical_index.py`, a standalone script (same `if __name__ == "__main__"` + `argparse` convention as `harness/knowledge_qa/eval_runner.py`/`judge_runner.py`), invoked manually by the developer. It calls `ChromaVectorStore.get_all(collection_name)` for `knowledge_global` and every `knowledge_{campaign_id}` collection found, and upserts each into `SQLiteLexicalStore` using the `original_text` and metadata already stored in Chroma — no re-embedding, no re-ingestion, satisfying SC-004/SC-005.

**Rationale**: This was the explicit outcome of the `/speckit-clarify` session (see spec.md → Clarifications) — the project's existing CLI-driven-by-developer pattern (spec 013's `eval_runner.py`/`judge_runner.py`) was preferred over an implicit/automatic backfill for predictability and debuggability.

**Idempotency**: The migration is safe to re-run — `SQLiteLexicalStore.upsert` uses `INSERT OR REPLACE` keyed on `chunk_id`, so re-running after a partial failure or after new content has been ingested normally (which already writes to both stores per Decision 4) does not duplicate rows.

---

## Decision 6: Signal-provenance field on `KnowledgeChunk`

**Decision**: Add `matched_signals: list[str]` to `KnowledgeChunk` (values drawn from `{"vector", "lexical"}`), populated during RRF accumulation by tracking, per `chunk_id`, which result lists (vector vs. lexical) contributed a rank to it — independent of the weight applied.

**Rationale**: Directly satisfies FR-010 ("expose... whether it was surfaced via the keyword signal, the vector signal, or both") with a minimal, additive dataclass field. No new "Fused Candidate" class is introduced — the spec's Key Entities section describes it as extending the existing retrieved-chunk representation, and `KnowledgeChunk` already is that representation.

---

## Decision 7: Gold-standard tagging for the exact-term subset (SC-002)

**Decision**: Add `exact_term: bool = False` to `TestQuestion` (`test_questions.py`) and to the corresponding subset of rows in `rag_gold_standard.jsonl`. `evaluator.aggregate_results()` gains a filtered `exact_term_scores: CategoryMetrics | None` field computed the same way as the existing per-category buckets, but filtered on the new boolean tag rather than `category` (a question can be both, e.g., `category="direct_fact", exact_term=true`).

**Rationale**: `exact_term` is orthogonal to the existing `category` taxonomy (`direct_fact`, `comparison`, `holistic`, `numeric`, `relationship`) — an exact-term question can fall into any of those categories — so it's modeled as an independent boolean tag rather than a sixth category value, avoiding double-counting or reclassifying existing questions.
