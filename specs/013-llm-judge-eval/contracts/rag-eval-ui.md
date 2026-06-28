# Contract: RAG Evaluation Tab — Response Quality Section

**File**: `apps/web/pages/gm/rag_eval.py` (extended), `apps/web/services/response_eval.py` (new)
**Purpose**: Interactive judge evaluation within the existing RAG Evaluation Gradio tab

---

## Overview

A new "Response Quality" accordion section is appended below the existing retrieval results section in the RAG Evaluation tab. It reuses the JSONL question file already loaded in the tab and the `campaign_id` / `role` from the active `CampaignSession` in `session_state`. Results are streamed per question using Gradio's async generator pattern and persisted to `data/eval.db`.

---

## Gradio Components (new, within `rag_eval.py`)

### Inputs (read-only — shared with existing retrieval section)

| Component | Source | Description |
|---|---|---|
| `file_input` | Existing `gr.File` | JSONL file with test questions (already loaded by retrieval section) |
| `session_state` | Existing `gr.State` | Active `CampaignSession` providing `campaign_id` and `role` |

### New UI Components

| Component | Type | Description |
|---|---|---|
| `run_judge_btn` | `gr.Button` | "Run Response Quality Eval" — enabled only when a file is loaded AND a campaign session is active |
| `judge_progress_md` | `gr.Markdown` | Live progress: "Evaluating question N / M…" |
| `judge_summary_md` | `gr.Markdown` | Post-run summary: mean scores, coverage, run ID |
| `judge_results_table` | `gr.Dataframe` | Columns: `#`, `Question`, `Faithfulness`, `Relevance`, `Context Util`, `Aggregate`, `Status` |
| `judge_detail_md` | `gr.Markdown` | Drill-down for selected row: generated response + per-dimension rationales |
| `judge_results_state` | `gr.State` | `list[ResponseEvalRow]` — in-memory accumulator for row selection |

### Placeholder State (before first run)

When the accordion is first rendered (before any judge run has completed), `judge_results_table` is empty and `judge_progress_md` shows:

```
Response Quality Evaluation — select a question file and active campaign, then click "Run Response Quality Eval".
```

---

## Event Handlers

### `on_run_judge(session_state, file_input) → AsyncGenerator`

Triggered by `run_judge_btn`. Returns an async generator that yields UI updates after each question.

**Validation (before iteration)**:
1. If `session_state` is `None` or has no `campaign_id` → yields error message in `judge_progress_md`; stops.
2. If `file_input` is `None` → yields error message; stops.
3. If `JUDGE_PROVIDER` or `JUDGE_MODEL` env vars are missing → yields error message naming the missing variable; stops.

**Per-question loop**:
```
for idx, question in enumerate(questions, start=1):
    yield (progress update, empty table, current accumulated rows, state)
    try:
        answer, chunks = await ask_question(question, campaign_id, role)
        judge_result = await judge_evaluator.evaluate(question, answer, chunks)
        store.write_record(...)
        accumulated.append(ResponseEvalRow(...))
    except ProviderUnavailableError as e:
        accumulated.append(ResponseEvalRow(status="error", ...))
    yield (progress update, updated table, accumulated, state)
```

**On completion**: yields final `judge_summary_md` with mean scores and run ID.

### `on_judge_row_select(evt, state) → str`

Triggered on `judge_results_table` row selection. Returns markdown for `judge_detail_md` showing:
- The generated response text
- Per-dimension rationales (or error/raw response if status ≠ "scored")

---

## Service Interface (`apps/web/services/response_eval.py`)

```python
async def run_response_eval_question(
    question: str,
    category: str | None,
    campaign_id: uuid.UUID,
    role: str,
    judge_evaluator: JudgeEvaluator,
    store: EvaluationStore,
    run_id: str,
) -> ResponseEvalRow:
    """
    Calls ask_question(), runs judge, writes record to store.
    Returns a ResponseEvalRow for the Gradio table.
    Catches all exceptions and returns a row with status="error" rather than raising.
    """

def build_judge_summary(rows: list[ResponseEvalRow], run_id: str) -> ResponseEvalSummary:
    """Aggregates ResponseEvalRow list into ResponseEvalSummary."""
```

---

## Environment Variables (consumed at UI startup)

| Variable | Required | Description |
|---|---|---|
| `JUDGE_PROVIDER` | Yes | Provider for judge: `"ollama"` or `"claude"` |
| `JUDGE_MODEL` | Yes | Model name for judging |
| `JUDGE_PROMPT_PATH` | No | Path to judge prompt template (default: bundled `judge_prompt.txt`) |
| `JUDGE_MAX_CONTEXT_CHARS` | No | Character budget for context (default: `8000`) |
| `EVAL_DB_PATH` | No | Path to SQLite database (default: `data/eval.db`) |

If `JUDGE_PROVIDER` or `JUDGE_MODEL` is missing when the UI starts, the Run Response Quality Eval button is disabled with a tooltip: "Configure JUDGE_PROVIDER and JUDGE_MODEL env vars to enable response quality evaluation."

---

## Shared Store

Both the CLI harness and the UI write to `data/eval.db` (`ResponseEvalRecord` table). UI-triggered runs produce `run_id` values identical in format to CLI runs (`YYYYMMDD-HHMMSS-{uuid8}`), so all records can be queried together via `judge_runner.py --summary`.

---

## Error Display

All exceptions caught in the UI handler MUST be displayed in `judge_progress_md` with a descriptive message following Principle VII:

| Error | User-visible message |
|---|---|
| Missing `JUDGE_PROVIDER` | "Response quality evaluation is not configured — set JUDGE_PROVIDER and JUDGE_MODEL env vars and restart the app." |
| `ProviderUnavailableError` | "Judge LLM unavailable — check that Ollama is running (or verify your API key for cloud providers). Remaining questions will be marked as error." |
| `EnvironmentError` on unknown provider | "Unknown judge provider '<value>' — supported values: ollama, claude." |
| No active campaign | "No active campaign — join or create a campaign before running response quality evaluation." |
| No question file | "No question file loaded — upload a JSONL question file in the retrieval section above." |
