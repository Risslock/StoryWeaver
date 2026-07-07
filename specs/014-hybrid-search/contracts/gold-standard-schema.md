# Contract: Gold-Standard & Benchmark-Results Schema Extensions

**Files**: `harness/knowledge_qa/rag_gold_standard.jsonl`, `harness/knowledge_qa/benchmark_results.jsonl`
**Purpose**: Add the `exact_term` tag needed for SC-002's subset metric, and hybrid-search provenance fields needed for SC-001/SC-004's baseline-vs-hybrid comparison

---

## `rag_gold_standard.jsonl` — added field

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `exact_term` | `bool` | No | `false` | Marks a question as referencing an exact rule name, item name, spell, or numeric value (per spec.md User Story 1 / SC-002). Orthogonal to `category` — a question may be both `"category": "direct_fact"` and `"exact_term": true`. |

Existing rows are unaffected (the field is optional, defaults to `false` via `TestQuestion.exact_term: bool = False`). Only the subset of questions that qualify need the field added.

Example row (existing fields unchanged, new field added):
```json
{"question": "What is the Movement Rate of a dwarf?", "keywords": ["dwarf", "Movement Rate", "10"], "reference_answer": "The base Movement Rate of a dwarf is 10.", "category": "direct_fact", "exact_term": true}
```

## `benchmark_results.jsonl` — added fields per record

| Field | Type | Description |
|---|---|---|
| `hybrid_search_enabled` | `bool` | Value of `HYBRID_SEARCH_ENABLED` at the time this benchmark ran |
| `hybrid_search_keyword_weight` | `float` | Value of `HYBRID_SEARCH_KEYWORD_WEIGHT` at the time this benchmark ran |
| `hybrid_search_vector_weight` | `float` | Value of `HYBRID_SEARCH_VECTOR_WEIGHT` at the time this benchmark ran |
| `exact_term_scores` | `object` | `CategoryMetrics`-shaped object (`mean_mrr`, `mean_ndcg`, `mean_recall_at_k`, `question_count`) computed over only the rows where `exact_term: true` |

Existing fields (`mean_mrr`, `mean_ndcg`, `mean_recall_at_k`, `category_scores`, etc.) are unchanged.

## `compare_benchmark_runs()` — updated output

The existing per-category diff table (`test_gold_standard.py::compare_benchmark_runs`) gains one additional row, `exact_term`, alongside the existing `direct_fact`/`comparison`/`holistic`/`numeric`/`relationship`/`uncategorized` rows — using the same `_row()` helper against `exact_term_scores` instead of `category_scores["exact_term"]`. The header additionally prints each run's `hybrid_search_enabled`/weight values so a reviewer can see at a glance which run is the baseline and which is hybrid.

## Threshold applied to comparisons (per spec.md Clarifications)

Per the `/speckit-clarify` session: a metric counts as **regressed** if it drops by more than 2 percentage points from Run A to Run B, and **improved** if it rises by more than 2 percentage points. This threshold is applied by the harness/analysis step that consumes `compare_benchmark_runs()` output (task-level detail — not a new field on the JSONL record itself).
