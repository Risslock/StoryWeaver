# Quickstart Validation Guide: RAG Evaluation Tab & Q&A Source Visibility

## Prerequisites

1. StoryWeaver running locally (`uv run uvicorn apps.web.main:app --reload`)
2. Ollama running with models loaded (`KNOWLEDGE_LLM_MODEL`, `KNOWLEDGE_EMBED_MODEL`)
3. At least one document ingested into the knowledge base
4. A GM user account + campaign created
5. A JSONL test file prepared (see schema below)

## JSONL Test File Schema

Each line must be a JSON object:

```json
{"question": "What is the maximum Strain per action?", "keywords": ["Strain", "Toughness"], "reference_answer": "Up to Toughness rating.", "category": "direct_fact"}
{"question": "How does Initiative work?", "keywords": ["Initiative", "Dexterity", "step"], "reference_answer": "Roll Initiative step equal to Dexterity step.", "category": "direct_fact"}
```

Save as e.g. `harness/knowledge_qa/tests.jsonl`.

---

## Scenario 1: Run Retrieval Evaluation (US1 — P1)

**Goal**: Verify MRR, nDCG, and Recall@k are computed and displayed for all questions.

1. Sign in as a GM user and resume a campaign
2. Navigate to the **Knowledge Q&A** tab → then **RAG Evaluation** tab
3. Upload the `tests.jsonl` file via the file picker
4. Verify: the question table populates with category labels
5. Set k = 10 (default) and click **Run Evaluation**
6. Verify: each row shows numeric MRR, nDCG, Recall@k values (≥ 3 decimal places)
7. Verify: aggregate mean scores appear at the top or bottom of the table

**Expected**: No crash; all metrics are floats ∈ [0, 1]; row count matches JSONL line count.

---

## Scenario 2: Drill-Down on a Low-Scoring Question (US2 — P2)

**Goal**: Verify per-question detail view shows retrieved chunks and keyword ranks.

1. After running evaluation (Scenario 1), identify a row with low MRR or Recall@k
2. Select/click that row
3. Verify: a detail panel appears showing:
   - The top-k retrieved chunks (title + excerpt)
   - Per-keyword breakdown: `keyword → rank N` or `keyword → not found`

**Expected**: Keywords with rank show the 1-indexed position in the retrieved list.
Keywords not found show "not found" and contributed 0 to MRR/nDCG.

---

## Scenario 3: GM Access Only

**Goal**: Verify non-GM users cannot access the Evaluation tab.

1. Sign in as a **player** and join a campaign
2. Navigate the player dashboard
3. Verify: no "RAG Evaluation" tab is visible anywhere in the UI

**Expected**: The tab is absent from the player view — the Gradio navigation state machine
only renders `gm_col` for role="gm".

---

## Scenario 4: Q&A Sources Hidden by Default (US3 — P3)

**Goal**: Verify the LLM answer appears without inline citations.

1. Sign in as any user (GM or player) and navigate to the Knowledge Q&A tab
2. Ask a question that returns results
3. Verify: the chatbot shows the LLM answer text only — no "**Sources:**" block inline
4. Verify: a collapsed **"Show sources"** accordion appears below the chatbot
5. Click **"Show sources"**
6. Verify: source citations appear (doc title, headline, excerpt)
7. Click to collapse the accordion
8. Verify: sources disappear; chatbot answer is unchanged

**Expected**: Exactly one interaction (click) to reveal sources; one click to hide.

---

## Scenario 5: Edge Cases

### Malformed JSONL
1. Upload a JSONL file with a row missing the `keywords` field
2. Verify: a user-visible error message identifies the row number and field name
3. Verify: evaluation does not proceed past the malformed file

### k Larger Than Retrieved Docs
1. Set k = 50 and run evaluation on a small KB (< 50 docs ingested)
2. Verify: metrics are computed without error
3. Verify: Recall@k reflects actual retrieval depth, not a crash

### Zero Retrieved Documents
1. Ask an evaluation question on an empty knowledge base
2. Verify: all metrics score 0.0 for that question
3. Verify: no crash or Python exception visible in UI

---

## Harness Tests

After implementation, run:

```bash
uv run pytest harness/knowledge_qa/test_evaluator.py -v
uv run pytest harness/knowledge_qa/test_eval_service.py -v
```

These tests validate metric calculations (unit) and the evaluation service (integration)
independently of the Gradio UI.
