# Quickstart: LLM-as-Judge Response Evaluation

**Feature**: 013-llm-judge-eval | **Date**: 2026-06-28

This guide walks through validating that the feature works end-to-end.
See [data-model.md](data-model.md) for schemas and [contracts/](contracts/) for full CLI and UI references.

---

## Prerequisites

- Ollama running locally with `llama3.1` (or another instruction-following model) pulled
- Embedding model available (e.g., `nomic-embed-text` via Ollama)
- ChromaDB populated with at least one ingestion run
- At least one campaign created and its `campaign_id` UUID known
- `data/` directory exists at repo root (created by the storage layer on first run)

Verify Ollama is reachable:
```bash
curl http://localhost:11434/api/tags
```

---

## Scenario 1: Smoke Test — Harness CLI (3 questions, local Ollama)

### Step 1 — Generate answers and write EvaluationRecords

```bash
KNOWLEDGE_EMBED_PROVIDER=ollama \
KNOWLEDGE_EMBED_MODEL=nomic-embed-text \
KNOWLEDGE_LLM_MODEL=llama3.1 \
python harness/knowledge_qa/eval_runner.py \
  --campaign-id <YOUR_CAMPAIGN_UUID> \
  --role gm \
  --limit 3
```

**Expected output**:
```
[INFO] Run ID: 20260628-XXXXXX-XXXXXXXX
[INFO] Campaign: <YOUR_CAMPAIGN_UUID> | Role: gm
[INFO] Processing 3 questions...
[INFO] Done. 3 EvaluationRecords written in ~Xs
```

Note the printed Run ID for Step 2.

### Step 2 — Score the records with the judge

```bash
JUDGE_PROVIDER=ollama \
JUDGE_MODEL=llama3.1 \
python harness/knowledge_qa/judge_runner.py \
  --run-id <RUN_ID_FROM_STEP_1> \
  --summary
```

**Expected output**:
```
[INFO] Scoring 3 records for run <RUN_ID>
[INFO] Scored: 3 | Error: 0 | Parse error: 0 | No response: 0
[INFO] Judge coverage: 3/3 (100%)
[INFO] Mean faithfulness:          0.XX
[INFO] Mean relevance:             0.XX
[INFO] Mean context_utilization:   0.XX
[INFO] Mean aggregate:             0.XX
```

**Pass criteria**: All 3 records scored, numeric scores in [0, 1], no errors in logs.

---

## Scenario 2: Full Gold-Standard Run — Harness CLI (118 questions)

### Step 1 — Generate answers

```bash
KNOWLEDGE_EMBED_PROVIDER=ollama \
KNOWLEDGE_EMBED_MODEL=nomic-embed-text \
KNOWLEDGE_LLM_MODEL=llama3.1 \
python harness/knowledge_qa/eval_runner.py \
  --campaign-id <YOUR_CAMPAIGN_UUID> \
  --role gm
```

### Step 2 — Score all records from this run

```bash
JUDGE_PROVIDER=ollama \
JUDGE_MODEL=llama3.1 \
python harness/knowledge_qa/judge_runner.py \
  --run-id <RUN_ID> \
  --summary
```

**Pass criteria (SC-003)**: Summary includes mean scores for all four judge fields. Judge coverage ≥ 90% (allows for a small number of parse errors from local models).

---

## Scenario 3: Skip Already-Scored Records (Re-run Safety)

Run the judge command twice against the same run ID, **without** `--force`:

```bash
JUDGE_PROVIDER=ollama JUDGE_MODEL=llama3.1 \
  python harness/knowledge_qa/judge_runner.py --run-id <RUN_ID>

# Second run immediately after:
JUDGE_PROVIDER=ollama JUDGE_MODEL=llama3.1 \
  python harness/knowledge_qa/judge_runner.py --run-id <RUN_ID>
```

**Expected second-run output**:
```
[INFO] No unscored records found for run <RUN_ID>
```

**Pass criteria (FR-014)**: Second run exits 0, processes 0 records, makes 0 LLM calls.

---

## Scenario 4: Graceful Failure on Unreachable Judge

Point the judge at a non-existent endpoint:

```bash
JUDGE_PROVIDER=ollama \
JUDGE_MODEL=llama3.1 \
OLLAMA_BASE_URL=http://localhost:9999 \
python harness/knowledge_qa/judge_runner.py \
  --run-id <RUN_ID_WITH_3_UNSCORED_RECORDS>
```

**Expected output**:
```
[INFO] Scored: 0 | Error: 3 | Parse error: 0 | No response: 0
```

**Pass criteria (FR-010-a, SC-006)**: Run completes (exit code 0). All 3 records have `judge_status = "error"` and a populated `judge_error` field. No crash.

---

## Scenario 5: Force Re-score with a Different Provider (SC-005)

```bash
JUDGE_PROVIDER=claude \
JUDGE_MODEL=claude-haiku-4-5-20251001 \
ANTHROPIC_API_KEY=<KEY> \
python harness/knowledge_qa/judge_runner.py \
  --run-id <RUN_ID> \
  --force \
  --summary
```

**Pass criteria**: Scores are overwritten with Claude-judged values. `judge_provider = "claude"` in all updated records. Exit code 0.

---

## Scenario 6: UI Validation — Response Quality in RAG Evaluation Tab

Prerequisites:
- App running (`python apps/web/app.py` or `uv run python apps/web/app.py`)
- `JUDGE_PROVIDER=ollama` and `JUDGE_MODEL=llama3.1` set before app start
- Logged in as GM, active campaign with rulebook ingested

**Step 1**: Open the RAG Evaluation tab.

**Expected**: A "Response Quality" accordion/section is visible below the retrieval results section. `run_judge_btn` is initially disabled with tooltip "Configure JUDGE_PROVIDER and JUDGE_MODEL env vars to enable response quality evaluation" (or enabled if env vars are set). If env vars are set, the button is disabled only until a JSONL file is uploaded.

**Step 2**: Upload `harness/knowledge_qa/rag_gold_standard.jsonl` (or any JSONL with test questions). Limit to 3 questions by uploading a 3-question file.

**Expected**: `run_judge_btn` becomes enabled.

**Step 3**: Click "Run Response Quality Eval".

**Expected**: 
- Progress updates appear after each question: "Evaluating question 1 / 3…"
- Results table populates row-by-row with `Faithfulness`, `Relevance`, `Context Util`, `Aggregate`, `Status` columns.
- On completion, summary shows mean scores and run ID.
- No crash, no blank panel, no silent failure.

**Step 4**: Click on a result row.

**Expected**: Detail panel shows the generated response text and per-dimension rationales.

**Step 5**: Verify records in SQLite.

```bash
sqlite3 data/eval.db \
  "SELECT run_id, campaign_id, role, question, judge_status, judge_aggregate FROM response_eval_records ORDER BY id DESC LIMIT 3;"
```

**Pass criteria**: 3 records exist with `judge_status = "scored"`, `campaign_id` matches the active session, `role = "gm"`.

---

## Inspecting Records Directly

```bash
sqlite3 data/eval.db \
  "SELECT run_id, question, judge_status, judge_aggregate FROM response_eval_records LIMIT 5;"
```

```bash
sqlite3 data/eval.db \
  "SELECT COUNT(*), judge_status FROM response_eval_records GROUP BY judge_status;"
```

---

## Debugging

Set `LOG_LEVEL=DEBUG` to see the full judge prompt, raw LLM response, and per-question scores:

```bash
LOG_LEVEL=DEBUG JUDGE_PROVIDER=ollama JUDGE_MODEL=llama3.1 \
  python harness/knowledge_qa/judge_runner.py --run-id <RUN_ID> --limit 1
```
