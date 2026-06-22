# Contract: Evaluation Module Public Interface

These are the stable Python function contracts that the Gradio service layer and harness
tests depend on. Implementations MUST honour these signatures and return-type invariants.

---

## `packages/rag/rag/knowledge/evaluator.py`

### `calculate_mrr(keyword: str, chunks: list[KnowledgeChunk]) -> float`

**Returns**: Reciprocal rank of the first chunk whose `.text` contains `keyword`
(case-insensitive substring match). Returns `0.0` if not found.

**Invariants**:
- Return value ∈ [0, 1]
- Empty `chunks` → `0.0`

---

### `calculate_ndcg(keyword: str, chunks: list[KnowledgeChunk], k: int) -> float`

**Returns**: Binary nDCG for `keyword` across the first `k` chunks.

**Invariants**:
- Return value ∈ [0, 1]
- If IDCG == 0 (keyword not in any chunk) → `0.0`
- `k > len(chunks)` → compute over available chunks, no error

---

### `calculate_recall_at_k(keyword: str, chunks: list[KnowledgeChunk], k: int) -> float`

**Returns**: `1.0` if `keyword` (case-insensitive) found in any of `chunks[:k]`, else `0.0`.

**Invariants**:
- Return value ∈ {0.0, 1.0}
- `k > len(chunks)` → check all available chunks

---

### `evaluate_question(test: TestQuestion, chunks: list[KnowledgeChunk], k: int) -> RetrievalEvalResult`

**Returns**: Fully populated `RetrievalEvalResult` for one question given pre-retrieved chunks.

**Invariants**:
- `result.mrr` = mean of `calculate_mrr` across all keywords
- `result.ndcg` = mean of `calculate_ndcg(k=k)` across all keywords
- `result.recall_at_k` = fraction of keywords for which `calculate_recall_at_k` returned 1.0
- `result.keywords_found` = count of keywords with MRR > 0
- `result.retrieved_chunks` = the passed-in `chunks` list (unmodified)
- `result.keyword_ranks` maps each keyword → first rank (1-indexed) or `None`
- Empty `test.keywords` → all metrics = 0.0, `recall_at_k` = 0.0

---

### `aggregate_results(results: list[RetrievalEvalResult]) -> EvalSummary`

**Returns**: `EvalSummary` with mean metrics across all results.

**Invariants**:
- Empty `results` → `EvalSummary(mean_mrr=0.0, mean_ndcg=0.0, mean_recall_at_k=0.0, total_questions=0, k=0)`
- `total_questions` = `len(results)`

---

## `packages/rag/rag/knowledge/test_questions.py`

### `load_test_questions(file_path: str) -> list[TestQuestion]`

**Returns**: Ordered list of `TestQuestion` parsed from JSONL, one object per non-empty line.

**Raises**:
- `ValueError("Row N: missing field '<field>'")` if a required field is absent
- `json.JSONDecodeError` propagated for malformed JSON lines
- `FileNotFoundError` if path does not exist

**Invariants**:
- Empty file → `[]`
- Line order preserved

---

## `apps/web/services/eval.py`

### `async run_evaluation(file_path: str, campaign_id: uuid.UUID, k: int) -> tuple[list[RetrievalEvalResult], EvalSummary]`

**Returns**: `(per_question_results, summary)` where `per_question_results` has one entry per
JSONL line and `summary` aggregates them.

**Raises**:
- `ValueError` (propagated from `load_test_questions`) for malformed JSONL
- `ProviderUnavailableError` if ChromaDB / Ollama is unreachable

**Contract**:
- Calls `ChromaKnowledgeRetriever.search(query, campaign_id, role="gm", top_k=k)` for each question
- Calls `evaluate_question(test, chunks, k)` for each question
- Logs run start and completion at `INFO`; per-question errors at `ERROR` (Principle VIII)

---

## `apps/web/services/knowledge.py` — modified return

### `async ask_question(...) -> tuple[str, list[KnowledgeChunk]]`  *(unchanged)*

The function signature and return type are **unchanged**. The UI layer is responsible for
splitting the answer text and chunk list into separate display components. No service-layer
change is required.
