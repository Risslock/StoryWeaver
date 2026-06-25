# Data Model: RAG Evaluation Tab & Q&A Source Visibility

## Entities

### TestQuestion
Represents one evaluation case loaded from the JSONL file. In-memory only — no DB table.

| Field | Type | Description |
|-------|------|-------------|
| `question` | `str` | The question to send to the retriever |
| `keywords` | `list[str]` | Keywords that MUST appear in retrieved chunks |
| `reference_answer` | `str` | Gold-standard answer (for future LLM-judge use) |
| `category` | `str` | Label for grouping (e.g., `direct_fact`, `spanning`, `temporal`) |

**Validation**: All fields are required. Empty `keywords` list is valid (Recall@k = 1.0 trivially).

**Source**: `packages/rag/rag/knowledge/test_questions.py` — Pydantic `BaseModel`, loaded from `.jsonl`.

---

### RetrievalEvalResult
Per-question retrieval evaluation output. In-memory only.

| Field | Type | Description |
|-------|------|-------------|
| `question` | `str` | The question (copied from TestQuestion for display) |
| `category` | `str` | Category (copied from TestQuestion) |
| `mrr` | `float` | Mean Reciprocal Rank across all keywords, range [0, 1] |
| `ndcg` | `float` | Mean nDCG at k across all keywords, range [0, 1] |
| `recall_at_k` | `float` | Fraction of keywords found in top-k chunks, range [0, 1] |
| `keywords_found` | `int` | Count of keywords found |
| `total_keywords` | `int` | Total keyword count |
| `k` | `int` | The k value used for this evaluation run |
| `retrieved_chunks` | `list[KnowledgeChunk]` | The actual top-k chunks (for drill-down view) |
| `keyword_ranks` | `dict[str, int \| None]` | Map of keyword → first rank (1-indexed) or None if not found |

**Source**: `packages/rag/rag/knowledge/evaluator.py` — Pydantic `BaseModel`.

---

### EvalSummary
Aggregate metrics across all evaluated questions. In-memory only.

| Field | Type | Description |
|-------|------|-------------|
| `mean_mrr` | `float` | Mean MRR across all questions |
| `mean_ndcg` | `float` | Mean nDCG across all questions |
| `mean_recall_at_k` | `float` | Mean Recall@k across all questions |
| `total_questions` | `int` | Total number of questions evaluated |
| `k` | `int` | The k value used |

**Source**: `packages/rag/rag/knowledge/evaluator.py` — Pydantic `BaseModel`.

---

### KnowledgeChunk (existing, referenced)
Returned by `ChromaKnowledgeRetriever.search()`. Defined in `packages/rag/rag/knowledge/interface.py`.

Relevant fields for evaluation:

| Field | Type | Description |
|-------|------|-------------|
| `chunk_id` | `str` | Unique chunk identifier |
| `doc_title` | `str` | Source document title (for sources display) |
| `headline` | `str` | LLM-extracted section headline |
| `topic` | `str` | LLM-extracted topic |
| `text` | `str` | Full chunk text — used for keyword matching |
| `rrf_score` | `float` | Reciprocal Rank Fusion score from retrieval |

---

### SourceChunk (view model, Q&A tab)
A display-only structure derived from `KnowledgeChunk` for the Q&A sources accordion.
Not a Pydantic model — constructed inline in the UI rendering function.

| Field | Derived From | Description |
|-------|-------------|-------------|
| display title | `chunk.doc_title + " — " + chunk.headline` | Section label in sources panel |
| excerpt | `chunk.text[:200]` truncated | Preview text shown to user |
| topic | `chunk.topic` | Topic label |

---

## Relationships

```
JSONL file  ──loads──►  list[TestQuestion]
TestQuestion  ──drives──►  ChromaKnowledgeRetriever.search()
                                  │
                                  ▼
                         list[KnowledgeChunk]   ◄── existing entity
                                  │
                    ┌─────────────┤
                    ▼             ▼
          RetrievalEvalResult   Q&A sources accordion (SourceChunk view)
                    │
                    ▼
             EvalSummary (aggregated)
```

---

## State Management

All evaluation state is ephemeral Gradio `gr.State`:

| Gradio State | Type | Scope |
|-------------|------|-------|
| `eval_results_state` | `list[RetrievalEvalResult]` | Per-browser-tab; cleared on session change |
| `selected_result_state` | `RetrievalEvalResult \| None` | Currently selected row for drill-down |
| `sources_state` | `str` | Markdown string of citations for last Q&A answer |

No new SQLite tables or Alembic migrations are required — all evaluation data is transient.
