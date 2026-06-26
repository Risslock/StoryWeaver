# Contract: benchmark_results.jsonl Schema

**File**: `harness/knowledge_qa/benchmark_results.jsonl`

---

## Record Schema (feature 010+)

```json
{
  "strategy": "agentic",
  "timestamp": "2026-06-26T10:00:00+00:00",
  "gold_standard_path": "harness/knowledge_qa/rag_gold_standard.jsonl",
  "k": 10,
  "total_questions": 118,
  "mean_mrr": 0.623,
  "mean_ndcg": 0.587,
  "mean_recall_at_k": 0.712,
  "notes": "",
  "category_scores": {
    "direct_fact":   {"mean_mrr": 0.71, "mean_ndcg": 0.68, "mean_recall_at_k": 0.82, "question_count": 40},
    "comparison":    {"mean_mrr": 0.55, "mean_ndcg": 0.52, "mean_recall_at_k": 0.65, "question_count": 25},
    "holistic":      {"mean_mrr": 0.48, "mean_ndcg": 0.45, "mean_recall_at_k": 0.58, "question_count": 30},
    "numeric":       {"mean_mrr": 0.62, "mean_ndcg": 0.60, "mean_recall_at_k": 0.75, "question_count": 15},
    "relationship":  {"mean_mrr": 0.50, "mean_ndcg": 0.47, "mean_recall_at_k": 0.60, "question_count": 8},
    "uncategorized": {"mean_mrr": 0.0,  "mean_ndcg": 0.0,  "mean_recall_at_k": 0.0,  "question_count": 0}
  }
}
```

## Backward Compatibility

- Records produced before feature 010 do not contain `category_scores` — this is valid. Consumers must use `.get("category_scores", {})`.
- The five standard category keys (`direct_fact`, `comparison`, `holistic`, `numeric`, `relationship`) are always present in new records, even when a category has 0 questions (zero-score entry).
- `uncategorized` is included when any question lacks a `category` field; omitted when all questions are categorised.

## EvalSummary model (packages/rag/rag/knowledge/evaluator.py)

```python
class CategoryMetrics(BaseModel):
    mean_mrr: float
    mean_ndcg: float
    mean_recall_at_k: float
    question_count: int

class EvalSummary(BaseModel):
    mean_mrr: float
    mean_ndcg: float
    mean_recall_at_k: float
    total_questions: int
    k: int
    category_scores: dict[str, CategoryMetrics] = {}
```

## Terminal output format

```
=== Per-Category Results ===
Category        Questions  MRR     nDCG    Recall@10
direct_fact     40         0.710   0.680   0.820
comparison      25         0.550   0.520   0.650
holistic        30         0.480   0.450   0.580
numeric         15         0.620   0.600   0.750
relationship    8          0.500   0.470   0.600
uncategorized   0          0.000   0.000   0.000
=== Global ===
Total: 118   MRR: 0.623   nDCG: 0.587   Recall@10: 0.712
```
