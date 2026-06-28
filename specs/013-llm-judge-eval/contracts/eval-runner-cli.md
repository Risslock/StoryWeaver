# Contract: eval_runner.py CLI

**File**: `harness/knowledge_qa/eval_runner.py`
**Purpose**: Calls `ask_question()` for each gold-standard question and writes EvaluationRecords to `data/eval.db`

---

## Invocation

```
python harness/knowledge_qa/eval_runner.py --campaign-id UUID --role ROLE [OPTIONS]
```

## Required CLI Arguments

| Argument | Description |
|---|---|
| `--campaign-id UUID` | UUID of the campaign to evaluate against; must have the target rulebook ingested |
| `--role ROLE` | Role used for retrieval: `"gm"` or `"player"` |

## Required Environment Variables

| Variable | Description |
|---|---|
| `KNOWLEDGE_EMBED_PROVIDER` | Embedding provider (existing, used by `ask_question()`) |
| `KNOWLEDGE_EMBED_MODEL` | Embedding model (existing, used by `ask_question()`) |
| `KNOWLEDGE_LLM_MODEL` | LLM model for answer synthesis (existing, used by `ask_question()`) |

## Optional Environment Variables

| Variable | Default | Description |
|---|---|---|
| `EVAL_DB_PATH` | `data/eval.db` | Path to SQLite eval database |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama endpoint |

## Options

| Flag | Default | Description |
|---|---|---|
| `--gold-standard PATH` | `harness/knowledge_qa/rag_gold_standard.jsonl` | Gold-standard question file |
| `--run-id ID` | Auto-generated (`YYYYMMDD-HHMMSS-{uuid8}`) | Assign a specific run identifier |
| `--limit N` | None (all questions) | Process only the first N questions (for smoke-testing) |
| `--retrieval-k N` | `10` | Number of chunks to retrieve per question (passed to retriever) |

## Behaviour

1. Validates required CLI args (`--campaign-id`, `--role`) and env vars; exits with code 1 and an ERROR-level message if any are missing.
2. Validates `--campaign-id` is a parseable UUID; exits 1 if not.
3. Validates `--role` is `"gm"` or `"player"`; exits 1 if not.
4. Generates a `run_id` (or uses `--run-id` if supplied) and logs it at INFO level.
5. For each question in the gold-standard file:
   a. Calls `ask_question(question, campaign_id, role)` from `apps/web/services/knowledge.py`.
   b. Receives `(answer_text, list[KnowledgeChunk])`.
   c. Serialises chunk texts to JSON.
   d. Writes one `ResponseEvalRecord` with `judge_status = "unscored"`, `campaign_id`, and `role` to `data/eval.db`.
6. On completion, prints: run ID, `--campaign-id`, `--role`, questions processed, wall-clock time.

## Exit Codes

| Code | Meaning |
|---|---|
| 0 | All records written successfully |
| 1 | Configuration error (missing arg/env var, invalid UUID, invalid role, bad gold-standard path, DB error) |

## Example

```bash
KNOWLEDGE_EMBED_PROVIDER=ollama \
KNOWLEDGE_EMBED_MODEL=nomic-embed-text \
KNOWLEDGE_LLM_MODEL=llama3.1 \
python harness/knowledge_qa/eval_runner.py \
  --campaign-id a1b2c3d4-e5f6-7890-abcd-ef1234567890 \
  --role gm \
  --limit 10
```

Expected stdout:
```
[INFO] Run ID: 20260628-143022-a3f8c1b9
[INFO] Campaign: a1b2c3d4-e5f6-7890-abcd-ef1234567890 | Role: gm
[INFO] Processing 10 questions...
[INFO] Done. 10 EvaluationRecords written in 47.3s
```
