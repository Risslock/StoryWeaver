# Data Model: Hybrid Search for Knowledge Retrieval

**Feature**: 014-hybrid-search | **Date**: 2026-07-07

---

## Persistent Storage

### `knowledge_lexical` (SQLite FTS5 virtual table)

The Lexical Index (per spec.md → Key Entities). One row per chunk, mirroring the same chunks stored in ChromaDB. Lives in the existing SQLite database (`_cfg.database_url`), managed by a new `SQLiteLexicalStore` in `packages/rag/rag/knowledge/lexical_store.py`.

```sql
CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_lexical USING fts5(
    chunk_id UNINDEXED,
    doc_id UNINDEXED,
    scope UNINDEXED,
    campaign_id UNINDEXED,
    access_level UNINDEXED,
    text,
    tokenize = 'porter unicode61'
);
```

| Column | Indexed by FTS5? | Description |
|---|---|---|
| `chunk_id` | No (`UNINDEXED`) | Same value as `KnowledgeChunk.chunk_id` / the Chroma document id (`"{doc_id_hex}_{index:04d}"`) — primary correlation key between the two stores |
| `doc_id` | No | Same as Chroma metadata `doc_id`; used by `delete_by_doc` |
| `scope` | No | `"global"` or the campaign UUID string — same semantics as Chroma metadata `scope` |
| `campaign_id` | No | Same as Chroma metadata `campaign_id` (empty string for global scope) |
| `access_level` | No | `"gm_only"` \| `"player_visible"` — same semantics as Chroma metadata `access_level`, filtered identically |
| `text` | Yes (full-text indexed) | `original_text` from `pipeline.py`'s `_build_records` — literal document text (breadcrumb-prefixed), **not** the LLM-enriched `compound` embedding text |

**Uniqueness**: `chunk_id` is the natural key. `SQLiteLexicalStore.upsert()` deletes-then-inserts by `chunk_id` (FTS5 has no native `UNIQUE`/`INSERT OR REPLACE` support on indexed columns, so upsert is implemented as `DELETE WHERE chunk_id = ? ; INSERT ...` per row, executed inside one transaction per batch) — this makes both ingestion-time sync and the backfill migration idempotent.

**Query pattern**:

```sql
SELECT chunk_id, doc_id, scope, campaign_id, access_level, text, bm25(knowledge_lexical) AS score
FROM knowledge_lexical
WHERE knowledge_lexical MATCH :query
  AND scope = :scope
  AND (:role != 'player' OR access_level = 'player_visible')
ORDER BY score ASC   -- FTS5 bm25(): more negative = more relevant
LIMIT :top_k;
```

`:query` is built by tokenizing the raw user query into words and quoting each individually (`"word1" OR "word2" OR ...`) so that punctuation/operators in free-text user input can never be interpreted as FTS5 query-syntax; this is a correctness/robustness measure, not a security boundary (the query text originates from the same trusted app-internal caller as vector search).

---

## `SQLiteLexicalStore` (`packages/rag/rag/knowledge/lexical_store.py`)

Mirrors the existing `ChromaVectorStore` interface shape so `retriever.py` and `pipeline.py` can call both stores the same way.

```python
class SQLiteLexicalStore:
    def __init__(self, database_url: str | None = None) -> None: ...

    async def ensure_table(self) -> None:
        """Idempotent CREATE VIRTUAL TABLE IF NOT EXISTS."""

    async def upsert(
        self,
        ids: list[str],
        texts: list[str],
        metadatas: list[dict[str, object]],
    ) -> None:
        """Delete-then-insert by chunk_id, one transaction per batch."""

    async def query(
        self,
        query_text: str,
        scope: str,
        role: str,
        top_k: int,
    ) -> list[tuple[str, dict[str, object], str]]:
        """Returns [(chunk_id, metadata, text), ...] ordered best-first, same shape as
        the tuples ChromaKnowledgeRetriever.search() already builds from Chroma results."""

    async def delete_by_doc(self, doc_id: str) -> None: ...

    async def get_all(self, scope: str) -> list[tuple[str, dict[str, object], str]]:
        """Used only by backfill verification / debugging, not the query hot path."""
```

Unlike `ChromaVectorStore`, there is no per-collection `collection_name` parameter — scope/campaign filtering happens via the `scope`/`campaign_id`/`access_level` `WHERE` columns in the single shared table (see [research.md](research.md) → Decision 1).

---

## In-Memory Models

### `KnowledgeChunk` (`packages/rag/rag/knowledge/interface.py`) — extended

```python
@dataclass
class KnowledgeChunk:
    chunk_id: str
    doc_id: str
    doc_title: str
    headline: str
    summary: str
    topic: str
    access_level: str
    scope: str
    text: str
    rrf_score: float
    breadcrumb: str = ""
    source_type: str = "rulebook"
    matched_signals: list[str] = field(default_factory=list)   # NEW — "vector" and/or "lexical"
```

`matched_signals` is the Fused Candidate concept from spec.md's Key Entities — implemented as an added field rather than a new class, since spec.md explicitly describes it as "extend[ing] the existing retrieved-chunk representation rather than replacing it."

### Hybrid Search Configuration (`packages/core/core/config.py` — extended `Settings`)

| Field | Env Var | Type | Default | Validation |
|---|---|---|---|---|
| `hybrid_search_enabled` | `HYBRID_SEARCH_ENABLED` | `bool` | `False` | — |
| `hybrid_search_keyword_weight` | `HYBRID_SEARCH_KEYWORD_WEIGHT` | `float` | `1.0` | Must be `> 0.0`; `Settings` raises `ValueError` at startup otherwise (`@model_validator(mode="after")`) |
| `hybrid_search_vector_weight` | `HYBRID_SEARCH_VECTOR_WEIGHT` | `float` | `1.0` | Must be `> 0.0`; same validator |

See [contracts/config-contract.md](contracts/config-contract.md) for the full contract.

---

## Evaluation Harness Extensions

### `TestQuestion` (`packages/rag/rag/knowledge/test_questions.py`) — extended

```python
class TestQuestion(BaseModel):
    question: str
    keywords: list[str]
    reference_answer: str
    category: str
    exact_term: bool = False   # NEW — orthogonal tag for SC-002's exact-term subset
```

`load_test_questions()` treats `exact_term` as optional (defaults to `False` when the JSONL row omits it), so the existing 118-question file only needs the new field added to the subset of rows that qualify — no reformatting of the whole file.

### `EvalSummary` (`packages/rag/rag/knowledge/evaluator.py`) — extended

```python
class EvalSummary(BaseModel):
    mean_mrr: float
    mean_ndcg: float
    mean_recall_at_k: float
    total_questions: int
    k: int
    category_scores: dict[str, CategoryMetrics] = {}
    exact_term_scores: CategoryMetrics | None = None   # NEW — filtered on TestQuestion.exact_term, not category
```

`aggregate_results()` computes `exact_term_scores` by filtering the same `RetrievalEvalResult` list on a new `is_exact_term: bool` field added to `RetrievalEvalResult` (populated in `evaluate_question()` from `test.exact_term`), reusing the existing `CategoryMetrics` mean-computation logic rather than duplicating it.

### `benchmark_results.jsonl` — new fields per record

```json
{
  "...": "... all existing fields unchanged ...",
  "hybrid_search_enabled": false,
  "hybrid_search_keyword_weight": 1.0,
  "hybrid_search_vector_weight": 1.0,
  "exact_term_scores": {"mean_mrr": 0.0, "mean_ndcg": 0.0, "mean_recall_at_k": 0.0, "question_count": 0}
}
```

Added for provenance so `compare_benchmark_runs()` (`test_gold_standard.py`) can show whether two compared records differ in hybrid configuration, and so the exact-term subset (SC-002) appears in the same comparison table as the standard categories.
