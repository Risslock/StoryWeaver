# Data Model: Smart Chunking Strategy & Gold Standard Eval

**Feature**: `007-chunking-strategy-gold-standard`

---

## Entities

### BaseChunker (Abstract)

The unified interface for all chunking strategies. Replaces the concrete `MarkdownChunker`
as the dependency accepted by `PdfIngestor` and `MarkdownIngestor`.

| Attribute / Method | Type | Description |
|--------------------|------|-------------|
| `chunk(text)` | `str → list[str]` | Synchronous split. Must not return empty strings. |
| `async_chunk(text)` | `str → Awaitable[list[str]]` | Async split. Default: runs `chunk()` in thread pool. |
| `strategy_name` | `str` (property) | One of `"heading"`, `"semantic"`, `"agentic"`. Logged at ingestion start. |

**Invariants**:
- No chunk in the returned list may be empty or whitespace-only.
- Table atomicity: a Markdown table and its immediately preceding heading MUST remain in the
  same chunk unless the table alone exceeds `max_tokens`.
- All three concrete subclasses must satisfy the same invariants.

---

### HeadingChunker

Current `MarkdownChunker` logic, renamed. No behaviour change.

| Configuration Env Var | Default | Description |
|-----------------------|---------|-------------|
| `KNOWLEDGE_MAX_CHUNK_TOKENS` | 800 | Hard cap per chunk. |
| `KNOWLEDGE_CHUNK_OVERLAP_TOKENS` | 50 | Overlap appended from previous chunk tail. |

---

### SemanticChunker

| Configuration Env Var | Default | Description |
|-----------------------|---------|-------------|
| `KNOWLEDGE_MAX_CHUNK_TOKENS` | 800 | Shared with `HeadingChunker`. |
| `KNOWLEDGE_SEMANTIC_BREAKPOINT_PERCENTILE` | 95 | Percentile of similarity distribution used as split threshold. Lower = fewer, larger chunks. |
| `KNOWLEDGE_SEMANTIC_MIN_CHUNK_TOKENS` | 50 | Chunks below this are merged with their neighbour. |

**Algorithm state** (internal, not persisted):

| Field | Type | Description |
|-------|------|-------------|
| `_sentences` | `list[str]` | Sentence-split text units. |
| `_embeddings` | `list[list[float]]` | One embedding vector per sentence. |
| `_similarities` | `list[float]` | Cosine similarity between sentence[i] and sentence[i+1]. |
| `_breakpoints` | `list[int]` | Indices where similarity falls below the threshold. |

---

### AgenticChunker

| Configuration Env Var | Default | Description |
|-----------------------|---------|-------------|
| `KNOWLEDGE_MAX_CHUNK_TOKENS` | 800 | Shared cap. |
| `KNOWLEDGE_ENRICH_MODEL` | (existing) | LLM used for proposition boundary detection. Reuses the enricher's model. |
| `KNOWLEDGE_AGENTIC_BATCH_SECTIONS` | 1 | Number of heading sections processed per LLM call. Increase to trade LLM call count for prompt size. |

---

### ChunkingStrategyFactory

Not a persisted entity — a module-level function.

```
create_chunker(embed_fn=None, llm_provider=None) → BaseChunker
```

Reads `KNOWLEDGE_CHUNKING_STRATEGY` (default `"heading"`), instantiates the correct subclass.
`embed_fn` and `llm_provider` are injected for `SemanticChunker` and `AgenticChunker`
respectively; if not provided, each chunker fetches them lazily.

---

### ChunkBenchmarkResult

Persisted to `harness/knowledge_qa/benchmark_results.jsonl`, one record per evaluation run.

| Field | Type | Description |
|-------|------|-------------|
| `strategy` | `str` | `"heading"` \| `"semantic"` \| `"agentic"` |
| `timestamp` | `str` | ISO 8601 UTC datetime of the run |
| `gold_standard_path` | `str` | Path to the JSONL file used |
| `k` | `int` | Top-k used for retrieval |
| `total_questions` | `int` | Number of questions evaluated |
| `mean_mrr` | `float` | Mean Reciprocal Rank across all questions |
| `mean_ndcg` | `float` | Mean Normalised Discounted Cumulative Gain |
| `mean_recall_at_k` | `float` | Mean Recall@k |
| `notes` | `str` | Optional human note (e.g., corpus version, model, date of ingestion) |

---

## State Transitions

### Ingestion document status (existing)

No change to the `KnowledgeDocument` state machine (`processing → ready | failed`).
The chunking strategy does not add new states; a chunking failure transitions to `failed`
with an error message that includes the strategy name.

### Benchmark run lifecycle

```
start: harness invoked
  → load gold standard file (error if absent/malformed)
  → skip if Ollama unreachable
  → run all N questions through retriever
  → compute per-question metrics
  → aggregate
  → append ChunkBenchmarkResult to benchmark_results.jsonl
end: assert recall_at_k >= 0.40 (sanity gate only)
```

---

## Relationships to Existing Models

- `ChunkBenchmarkResult` uses `EvalSummary` fields (`mean_mrr`, `mean_ndcg`,
  `mean_recall_at_k`) but is not a subtype — it is a standalone JSONL record.
- `BaseChunker.chunk()` output feeds directly into the existing `ChunkEnricher` without
  schema changes. The enricher contract is unchanged.
- `GoldStandardQuestion` is structurally identical to the existing `TestQuestion` Pydantic
  model; both share the same `load_test_questions()` loader. No new model is needed.
