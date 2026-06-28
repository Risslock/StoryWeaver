# Contract: judge_runner.py CLI

**File**: `harness/knowledge_qa/judge_runner.py`
**Purpose**: Reads EvaluationRecords from `data/eval.db`, runs the judge LLM, writes scores back.

---

## Invocation

```
python harness/knowledge_qa/judge_runner.py [OPTIONS]
```

## Required Environment Variables

| Variable | Description |
|---|---|
| `JUDGE_PROVIDER` | `"ollama"` or `"claude"` |
| `JUDGE_MODEL` | Model name for judging |

## Optional Environment Variables

| Variable | Default | Description |
|---|---|---|
| `JUDGE_PROMPT_PATH` | `packages/rag/rag/evaluation/prompts/judge_prompt.txt` | Path to judge prompt template |
| `JUDGE_MAX_CONTEXT_CHARS` | `8000` | Character budget for context passed to judge |
| `EVAL_DB_PATH` | `data/eval.db` | Path to SQLite eval database |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama endpoint |
| `ANTHROPIC_API_KEY` | — | Required if `JUDGE_PROVIDER=claude` |

## Options

| Flag | Default | Description |
|---|---|---|
| `--run-id ID` | None (all runs) | Scope to a specific run identifier |
| `--force` | Off | Re-score already-scored records (overwrite `judge_status = "scored"` rows); always retries `"error"` and `"parse_error"` rows |
| `--limit N` | None | Process only N records (for smoke-testing) |
| `--summary` | Off | Print an aggregate score summary after completion |

## Behaviour

1. Validates required env vars; exits with code 1 and an ERROR-level message if any are missing.
2. If `--run-id` is provided and no matching records exist in the DB, exits with code 1 and names the unknown ID.
3. Queries records to process:
   - If `--run-id` given: records with that `run_id`
   - Otherwise: all records in DB
   - Without `--force`: filters to `judge_status IN ("unscored", "error", "parse_error")`
   - With `--force`: no status filter (processes everything in scope)
4. If no records remain after filtering (e.g., all already scored without `--force`), logs INFO "No unscored records found" and exits 0.
5. For each record:
   a. If `generated_response` is empty → writes `judge_status = "no_response"`, skips LLM call.
   b. Truncates context to `JUDGE_MAX_CONTEXT_CHARS`; sets `judge_context_truncated = true` if truncation occurred.
   c. Calls judge LLM via `generate_structured(prompt, JudgeScore)`.
   d. On success → writes all dimension scores + rationales, `judge_status = "scored"`, `scored_at = now()`.
   e. On `ValidationError` → writes `judge_status = "parse_error"`, `judge_raw_response = raw_text`.
   f. On network/timeout exception → writes `judge_status = "error"`, `judge_error = str(exc)`.
   g. Continues to next record regardless of outcome.
6. On completion, logs: records processed, scored, error, parse_error, no_response counts.
7. If `--summary` flag: prints mean scores per dimension, aggregate mean, and judge coverage %.

## Exit Codes

| Code | Meaning |
|---|---|
| 0 | Run completed (even if some records errored — errors are recorded, not fatal) |
| 1 | Configuration error or unknown `--run-id` |

## Example — Score a specific run

```bash
JUDGE_PROVIDER=ollama \
JUDGE_MODEL=llama3.1 \
python harness/knowledge_qa/judge_runner.py \
  --run-id 20260628-143022-a3f8c1b9 \
  --summary
```

Expected stdout:
```
[INFO] Scoring 10 records for run 20260628-143022-a3f8c1b9
[INFO] Scored: 9 | Error: 0 | Parse error: 1 | No response: 0
[INFO] Judge coverage: 9/10 (90%)
[INFO] Mean faithfulness:          0.82
[INFO] Mean relevance:             0.88
[INFO] Mean context_utilization:   0.74
[INFO] Mean aggregate:             0.81
```

## Example — Re-score with a different judge model

```bash
JUDGE_PROVIDER=claude \
JUDGE_MODEL=claude-haiku-4-5-20251001 \
ANTHROPIC_API_KEY=sk-... \
python harness/knowledge_qa/judge_runner.py \
  --run-id 20260628-143022-a3f8c1b9 \
  --force \
  --summary
```
