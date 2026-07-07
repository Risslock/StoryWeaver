# Implementation Plan: Hybrid Search for Knowledge Retrieval

**Branch**: `014-hybrid-search` | **Date**: 2026-07-07 | **Spec**: [spec.md](spec.md)

## Summary

Add a lexical (BM25 keyword) search signal alongside the existing vector search in `ChromaKnowledgeRetriever.search()`, fused with vector results in the same weighted-RRF step that today only combines multi-query vector result lists. The lexical index is a SQLite FTS5 virtual table (`packages/rag/rag/knowledge/lexical_store.py`) whose built-in `bm25()` ranking function provides BM25 scoring, kept in sync with ChromaDB during ingestion/update/delete, and backfilled for pre-existing collections via a one-time CLI migration. Hybrid search is off by default and togglable via config (`HYBRID_SEARCH_ENABLED` + a keyword/vector weight pair), so the existing gold-standard retrieval + LLM-judge harness can produce a baseline-vs-hybrid comparison with no code changes and no re-ingestion.

## Technical Context

**Language/Version**: Python 3.11+

**Primary Dependencies**:
- *Existing*: `packages/rag/` (`ChromaKnowledgeRetriever`, `ChromaVectorStore`, `IngestionPipeline`, `ChunkEnricher`), `packages/core/` (`Settings`), `packages/storage/` (SQLAlchemy 2.x + `aiosqlite`)
- *New*: none — SQLite FTS5 (and its native `bm25()` ranking function, i.e. real BM25 scoring) is built into Python's stdlib `sqlite3` module and reachable through `aiosqlite`, already a dependency; no external BM25/full-text library is added

**Storage**: A new SQLite FTS5 virtual table (`knowledge_lexical`) in the existing SQLite database (`_cfg.database_url` — same DB as `Campaign`/`KnowledgeDocument`, not a separate file), storing chunk text plus `chunk_id`/`doc_id`/`scope`/`campaign_id`/`access_level` as `UNINDEXED` columns for filtering. ChromaDB collections (`knowledge_global`, `knowledge_{campaign_id}`) are unchanged.

**Testing**: `pytest` + `pytest-asyncio`, following the existing pattern in `harness/knowledge_qa/test_retrieval.py` and `packages/rag/tests/`. Real-Ollama integration test for end-to-end hybrid retrieval, mirroring `test_integration.py`.

**Target Platform**: Local (Windows/Linux), Ollama for embeddings; SQLite FTS5 requires no external service.

**Project Type**: Single-project monorepo (`packages/*` + `apps/web/` + `harness/`) — no new top-level package.

**Performance Goals**: Not a stated requirement for this feature (no ingestion-speed goals are set for the local Ollama pipeline). Lexical query cost is bounded by the same `top_k` used for vector search per collection, so it does not change the asymptotic shape of `search()`.

**Constraints**:
- `HYBRID_SEARCH_ENABLED` defaults to `false` — must produce byte-for-byte-equivalent behavior to today's vector-only pipeline when disabled (User Story 3 AC1)
- Weight config must fail fast with a clear error at startup if out of range, not silently fall back (User Story 3 AC3)
- Lexical search is a retrieval technique, not a swappable AI provider, so it does not need a `packages/rag` provider-factory indirection like `JUDGE_PROVIDER`; it does need the SQLite table to be creatable/backfillable independent of ChromaDB re-ingestion (SC-004, SC-005, FR-011)
- `ChunkEnricher.rerank()` is unchanged — it only ever sees the already-fused candidate list
- Every new setting added to `packages/core/core/config.py` MUST be mirrored in both `.env.example` (documented, following the existing per-feature section style — see the `KNOWLEDGE_*`/`JUDGE_*` blocks) and the developer's local `.env` (actual working defaults), in the same commit/PR that introduces the setting — not deferred to a follow-up. This is a repo-wide practice (not new to this feature), called out here because this feature adds new settings.

**Scale/Scope**: Same 118-question gold-standard set (`harness/knowledge_qa/rag_gold_standard.jsonl`) used for the retrieval benchmark; a subset gets a new `exact_term: bool` tag for SC-002. Existing ingested collections (however many exist locally) need a one-time backfill via FR-011's migration command.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Spec-Driven Development | ✅ PASS | Spec exists at `specs/014-hybrid-search/spec.md`; both clarifications resolved |
| II. Provider Abstraction | ✅ PASS | Hybrid search is togglable and weighted purely via `core/config.py` env vars (`HYBRID_SEARCH_ENABLED`, `HYBRID_SEARCH_KEYWORD_WEIGHT`, `HYBRID_SEARCH_VECTOR_WEIGHT`); disabling it requires no code change and reverts to today's exact vector-only path |
| III. Package Isolation | ✅ PASS | All new code lives inside the existing `packages/rag/` package (`rag/knowledge/lexical_store.py`, extensions to `retriever.py`/`pipeline.py`/`interface.py`); no new top-level package |
| IV. Local-First, Cloud-Optional | ✅ PASS | SQLite FTS5 is local, built into the stdlib, adds no cloud dependency and no new external service |
| V. Harness-Driven Agent Quality | ✅ PASS | Feature's own acceptance criteria (SC-001..004) are expressed as harness/eval comparisons; `test_gold_standard.py` and the judge harness are extended, not replaced |
| VI. Product-First Development | ✅ PASS | Directly improves retrieval quality (the product's core Knowledge Q&A feature); no new auth/API/infra layer introduced |
| VII. Placeholder-First & Explicit Failures | ✅ PASS | No new UI surface is introduced (retrieval-stage change only); the backfill CLI fails loudly (non-zero exit + message) rather than silently producing partial state |
| VIII. Structured Logging & Observability | ✅ PASS | New modules use `logging.getLogger(__name__)`; lexical query failures log at WARNING (mirroring `retriever.py`'s existing ChromaDB failure handling) and are non-fatal — falls back to vector-only for that query |

**Gate Result**: ✅ ALL PASS — No violations require justification.

## Project Structure

### Documentation (this feature)

```text
specs/014-hybrid-search/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md         # Phase 1 output
├── quickstart.md         # Phase 1 output
├── contracts/
│   ├── config-contract.md          # New env vars, defaults, validation rules
│   ├── lexical-store-interface.md  # SQLiteLexicalStore + weighted-RRF fusion contract
│   ├── backfill-cli.md             # One-time migration CLI contract
│   └── gold-standard-schema.md     # rag_gold_standard.jsonl / benchmark_results.jsonl schema extensions
└── tasks.md              # Phase 2 output (via /speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
packages/rag/rag/knowledge/
├── lexical_store.py        # NEW: SQLiteLexicalStore — upsert/query/delete_by_doc/get_all over FTS5 (BM25 via bm25())
├── retriever.py             # MODIFIED: add lexical query lists into the RRF fusion, weighted; add matched_signals
├── pipeline.py               # MODIFIED: _build_records / upsert call also writes to SQLiteLexicalStore
├── interface.py               # MODIFIED: KnowledgeChunk gets a `matched_signals: list[str]` field
├── backfill_lexical_index.py  # NEW: one-time migration CLI (explicit migration command per spec clarification)
└── evaluator.py                # MODIFIED: exact_term subset aggregation for SC-002

packages/rag/rag/knowledge/test_questions.py   # MODIFIED: TestQuestion gets `exact_term: bool = False`

packages/core/core/config.py    # MODIFIED: HYBRID_SEARCH_ENABLED / _KEYWORD_WEIGHT / _VECTOR_WEIGHT + validator

.env.example                     # MODIFIED: new "Hybrid Search (feature 014)" section documenting the 3 vars above
.env                              # MODIFIED: same 3 vars added to local dev config, defaulted off (not committed — gitignored)

packages/rag/tests/knowledge/
├── test_lexical_store.py        # NEW: unit tests for SQLiteLexicalStore
├── test_retriever_hybrid.py     # NEW: unit tests for weighted fusion + matched_signals
└── test_backfill.py              # NEW: unit tests for backfill idempotency

harness/knowledge_qa/
├── rag_gold_standard.jsonl        # MODIFIED: subset of questions tagged exact_term: true
├── test_gold_standard.py          # MODIFIED: records hybrid_search_enabled + weights in benchmark_results.jsonl; prints exact_term subset row
└── test_integration.py             # MODIFIED/EXTENDED: hybrid-enabled integration case
```

**Structure Decision**: Single-project layout, no new top-level package. All retrieval/ingestion changes stay inside the existing `packages/rag/` subpackage boundary (Principle III); the new lexical index is an implementation detail of `rag.knowledge`, not a sibling package, because it has no independent public interface beyond what `ChromaKnowledgeRetriever` already exposes. The backfill CLI follows the same "standalone script under the owning package, `if __name__ == "__main__"`" convention already used by `harness/knowledge_qa/eval_runner.py` / `judge_runner.py`, but lives in `packages/rag/rag/knowledge/` because it operates on production data (not eval harness data) and needs to be run by any operator, not just during a benchmark.

## Complexity Tracking

No constitution violations. No entries required.
