# Contract: Hybrid Search Configuration

**File**: `packages/core/core/config.py` (`Settings` class)
**Purpose**: Toggle hybrid search and control keyword/vector fusion weighting via environment variables only — no code changes (FR-004, FR-005)

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `HYBRID_SEARCH_ENABLED` | No | `false` | When `false`, `ChromaKnowledgeRetriever.search()` behaves exactly as it does today — no lexical query lists are added to the RRF fusion, `matched_signals` is always `["vector"]`. |
| `HYBRID_SEARCH_KEYWORD_WEIGHT` | No | `1.0` | Per-list weight multiplier applied to each lexical (FTS5/BM25) result list before RRF accumulation. Must be `> 0.0`. |
| `HYBRID_SEARCH_VECTOR_WEIGHT` | No | `1.0` | Per-list weight multiplier applied to each vector result list before RRF accumulation. Must be `> 0.0`. Defaults to `1.0` to exactly match today's un-weighted behavior. |

## Validation Rules (User Story 3, Acceptance Scenario 3)

A `@model_validator(mode="after")` on `Settings` enforces, at process startup (not at query time):

- `hybrid_search_keyword_weight > 0.0` — else raise `ValueError("HYBRID_SEARCH_KEYWORD_WEIGHT must be > 0.0")`
- `hybrid_search_vector_weight > 0.0` — else raise `ValueError("HYBRID_SEARCH_VECTOR_WEIGHT must be > 0.0")`

These are validation errors, not silent fallbacks: an out-of-range value must prevent the app/harness from starting, per spec.md's edge case requirement ("it fails with a clear configuration error rather than silently falling back to a default").

## Documentation Requirement

All three variables MUST be added to `.env.example` in a new `# ── Hybrid Search (feature 014) ──` section, following the same style as the existing `# ── Knowledge Pipeline — Retrieval ──` and `# ── LLM-as-Judge Response Evaluation (feature 013) ──` sections (short comment per var, defaults shown, alternatives commented out). The developer's local `.env` gets the same three lines added with working defaults. This must land in the same change that introduces the settings — not as follow-up cleanup.

## Behavior Matrix

| `HYBRID_SEARCH_ENABLED` | Lexical query lists added? | `matched_signals` possible values | Behavior vs. today |
|---|---|---|---|
| `false` (default) | No | `["vector"]` only | Identical to pre-014 behavior |
| `true` | Yes (one per collection, original query only) | `["vector"]`, `["lexical"]`, or `["vector", "lexical"]` | Weighted-RRF fusion includes lexical signal |

## Example

```bash
# Baseline run (today's behavior)
HYBRID_SEARCH_ENABLED=false python -m pytest harness/knowledge_qa/test_gold_standard.py

# Hybrid run, equal weighting (default weights)
HYBRID_SEARCH_ENABLED=true python -m pytest harness/knowledge_qa/test_gold_standard.py

# Hybrid run, keyword-favored
HYBRID_SEARCH_ENABLED=true HYBRID_SEARCH_KEYWORD_WEIGHT=1.5 python -m pytest harness/knowledge_qa/test_gold_standard.py

# Invalid — must fail fast at startup, not silently fall back
HYBRID_SEARCH_ENABLED=true HYBRID_SEARCH_KEYWORD_WEIGHT=0 python -m pytest harness/knowledge_qa/test_gold_standard.py
# → ValueError: HYBRID_SEARCH_KEYWORD_WEIGHT must be > 0.0
```
