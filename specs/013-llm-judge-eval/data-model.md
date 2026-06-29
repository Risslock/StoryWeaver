# Data Model: LLM-as-Judge Response Evaluation

**Feature**: 013-llm-judge-eval | **Date**: 2026-06-28

---

## Persistent Storage

### `ResponseEvalRecord` (SQLAlchemy model — `data/eval.db`)

The primary persistence unit. One row per question per eval run. Written by both the harness CLI (`eval_runner.py`) and the Gradio UI (`response_eval.py` service).

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `id` | INTEGER PK | No | Auto-increment primary key |
| `run_id` | TEXT (indexed) | No | Run identifier (`YYYYMMDD-HHMMSS-{uuid8}`); groups all records from one eval run |
| `campaign_id` | TEXT (indexed) | No | UUID of the campaign evaluated; passed via `--campaign-id` CLI arg or read from session state |
| `role` | TEXT | No | Role used for retrieval: `"gm"` or `"player"` |
| `question` | TEXT | No | Full question text from the gold standard |
| `question_source` | TEXT | No | `"gold_standard"` or `"ad_hoc"` |
| `question_category` | TEXT | Yes | Category label from gold standard (e.g., `"direct_fact"`, `"comparison"`) |
| `generated_response` | TEXT | No | LLM-generated answer from `ask_question()` |
| `context_chunks_json` | TEXT | No | JSON array of chunk texts passed to the answer LLM (pre-truncation) |
| `judge_status` | TEXT | No | `"unscored"` \| `"scored"` \| `"error"` \| `"parse_error"` \| `"no_response"` (default: `"unscored"`) |
| `judge_provider` | TEXT | Yes | Provider used for judging (populated when judge runs) |
| `judge_model` | TEXT | Yes | Model name used for judging |
| `judge_faithfulness` | REAL | Yes | Faithfulness score [0, 1] |
| `judge_faithfulness_rationale` | TEXT | Yes | Natural language explanation for faithfulness score |
| `judge_relevance` | REAL | Yes | Answer relevance score [0, 1] |
| `judge_relevance_rationale` | TEXT | Yes | Natural language explanation for relevance score |
| `judge_context_utilization` | REAL | Yes | Context utilization score [0, 1] |
| `judge_context_utilization_rationale` | TEXT | Yes | Natural language explanation for context utilization score |
| `judge_aggregate` | REAL | Yes | Equally-weighted mean of the three dimension scores |
| `judge_error` | TEXT | Yes | Error description when `judge_status` is `"error"` |
| `judge_raw_response` | TEXT | Yes | Raw LLM output when `judge_status` is `"parse_error"` |
| `judge_context_truncated` | INTEGER (bool) | No | `1` if context was truncated to fit budget; `0` otherwise (default: `0`) |
| `created_at` | TEXT (ISO-8601) | No | Timestamp when record was written by eval runner |
| `scored_at` | TEXT (ISO-8601) | Yes | Timestamp when judge scores were last written |

**Indexes**: `run_id` (for scoped filtering), `campaign_id` (for campaign-scoped queries), `judge_status` (for skip/retry logic).

**Lifecycle state machine**:
```
[eval_runner.py or response_eval.py writes record] → judge_status = "unscored"
                                                       ↓
[judge_runner.py or response_eval.py judges]       → judge_status = "scored"       (all three dimension scores populated)
                                                   → judge_status = "error"         (network/timeout; judge_error populated)
                                                   → judge_status = "parse_error"   (invalid JSON; judge_raw_response populated)
                                                   → judge_status = "no_response"   (empty generated_response detected)

[judge_runner.py re-run, default]  → skips records where judge_status = "scored"
[judge_runner.py re-run, --force]  → overwrites all records in the target run_id
[judge_runner.py re-run, default]  → retries records where judge_status IN ("error", "parse_error")
```

---

## Pydantic Models (`packages/rag/rag/evaluation/models.py`)

### `JudgeScore` — structured output parsed from LLM response

```python
class DimensionScore(BaseModel):
    score: float          # [0.0, 1.0] — clamped on validation
    rationale: str        # Non-empty explanation

class JudgeScore(BaseModel):
    faithfulness: DimensionScore
    relevance: DimensionScore
    context_utilization: DimensionScore

    @property
    def aggregate(self) -> float:
        return (self.faithfulness.score + self.relevance.score + self.context_utilization.score) / 3
```

Validation rules:
- `DimensionScore.score` is clamped to [0.0, 1.0] via a `@field_validator`; out-of-range values are clamped (not rejected) and a WARNING is logged.
- `DimensionScore.rationale` must be non-empty; a missing rationale raises `ValidationError` → `"parse_error"`.

### `EvaluationInput` — in-memory representation passed to `JudgeEvaluator`

```python
class EvaluationInput(BaseModel):
    record_id: int
    run_id: str
    question: str
    generated_response: str
    context_chunks: list[str]    # Already-truncated list of chunk texts
    context_truncated: bool
```

### `JudgeResult` — returned by `JudgeEvaluator`

```python
class JudgeStatus(str, Enum):
    scored = "scored"
    error = "error"
    parse_error = "parse_error"
    no_response = "no_response"

class JudgeResult(BaseModel):
    record_id: int
    status: JudgeStatus
    score: JudgeScore | None         # Populated on status = "scored"
    error: str | None                # Populated on status = "error"
    raw_response: str | None         # Populated on status = "parse_error"
    judge_provider: str
    judge_model: str
```

---

## UI State Models (`apps/web/services/response_eval.py`)

These are in-memory only — not persisted. Used by the Gradio handler in `rag_eval.py`.

### `ResponseEvalRow` — one row in the Gradio results table

```python
@dataclass
class ResponseEvalRow:
    index: int                   # 1-based row number
    question: str
    faithfulness: float | str    # float when scored; "—" / "error" / "no_response" otherwise
    relevance: float | str
    context_utilization: float | str
    aggregate: float | str
    status: str                  # judge_status value
```

### `ResponseEvalSummary` — aggregate shown in the summary panel

```python
@dataclass
class ResponseEvalSummary:
    total: int
    scored: int
    error: int
    parse_error: int
    no_response: int
    mean_faithfulness: float | None
    mean_relevance: float | None
    mean_context_utilization: float | None
    mean_aggregate: float | None
    run_id: str
```

---

## Prompt Schema

The judge prompt template (`packages/rag/rag/evaluation/prompts/judge_prompt.txt`) uses Python `str.format()` placeholders:

| Placeholder | Filled with |
|---|---|
| `{question}` | `EvaluationInput.question` |
| `{context}` | Newline-joined `EvaluationInput.context_chunks` |
| `{response}` | `EvaluationInput.generated_response` |

The template instructs the judge to return a JSON object matching the `JudgeScore` schema. Example expected output format embedded in the prompt:

```json
{
  "faithfulness": {"score": 0.85, "rationale": "..."},
  "relevance": {"score": 0.90, "rationale": "..."},
  "context_utilization": {"score": 0.75, "rationale": "..."}
}
```

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `JUDGE_PROVIDER` | Yes | — | Provider for judge evaluation: `"ollama"` or `"claude"` |
| `JUDGE_MODEL` | Yes | — | Model name for judge evaluation |
| `JUDGE_PROMPT_PATH` | No | `packages/rag/rag/evaluation/prompts/judge_prompt.txt` | Path to judge prompt template |
| `JUDGE_MAX_CONTEXT_CHARS` | No | `8000` | Character budget for context passed to judge |
| `EVAL_DB_PATH` | No | `data/eval.db` | Path to SQLite evaluation database |
| `OLLAMA_BASE_URL` | No | `http://localhost:11434` | Ollama endpoint (existing) |
| `ANTHROPIC_API_KEY` | Conditional | — | Required when `JUDGE_PROVIDER=claude` |

> **Note**: Generation uses `ask_question()` which is governed by `KNOWLEDGE_LLM_MODEL`, `KNOWLEDGE_EMBED_MODEL`, and related existing env vars. No new `ANSWER_PROVIDER` / `ANSWER_MODEL` variables are introduced.
