# Quickstart: Hybrid Search for Knowledge Retrieval

**Feature**: 014-hybrid-search | **Date**: 2026-07-07

This guide walks through validating that hybrid search works end-to-end and demonstrably improves retrieval/answer quality. See [data-model.md](data-model.md) for schemas and [contracts/](contracts/) for full interface references.

---

## Prerequisites

- Ollama running locally with an embedding model pulled (e.g., `nomic-embed-text`) and an LLM pulled (e.g., `llama3.1`)
- At least one campaign ingested with the Earthdawn rulebook (or equivalent) — ChromaDB populated
- `data/` directory exists at repo root (created by the storage layer on first run)

Verify Ollama is reachable:
```bash
curl http://localhost:11434/api/tags
```

---

## Scenario 1: Backfill existing content (one-time)

Before comparing baseline vs. hybrid, the lexical index must exist for already-ingested collections (SC-004/SC-005 — no re-ingestion required).

```bash
python -m rag.knowledge.backfill_lexical_index
```

**Expected output**:
```
[INFO] Processing knowledge_global — N chunks found
[INFO] Processing knowledge_global — N chunks written
[INFO] Done. 1+ collections, N chunks backfilled in ~Xs
```

**Pass criteria (FR-011)**: Exit code 0. Re-running the same command immediately produces the same chunk counts with no errors (idempotent).

---

## Scenario 2: Toggle hybrid search with no code changes (User Story 3)

**Step 1 — Disabled (default), confirm identical behavior to today**:
```bash
HYBRID_SEARCH_ENABLED=false python -m pytest harness/knowledge_qa/test_gold_standard.py -v
```
**Expected**: Same Recall@10/MRR/nDCG as any pre-014 run (sanity gate `Recall@10 >= 0.40` still passes).

**Step 2 — Enabled, default weights**:
```bash
HYBRID_SEARCH_ENABLED=true python -m pytest harness/knowledge_qa/test_gold_standard.py -v
```
**Expected**: A second `benchmark_results.jsonl` record is appended with `hybrid_search_enabled: true`, `hybrid_search_keyword_weight: 1.0`, `hybrid_search_vector_weight: 1.0`.

**Step 3 — Invalid config fails fast**:
```bash
HYBRID_SEARCH_ENABLED=true HYBRID_SEARCH_KEYWORD_WEIGHT=0 python -c "from core.config import settings"
```
**Expected**: Raises `ValueError: HYBRID_SEARCH_KEYWORD_WEIGHT must be > 0.0` — process does not start, no silent fallback.

**Pass criteria (User Story 3, all 3 acceptance scenarios)**: Step 1 output is unchanged from a pre-014 baseline; Step 2 runs successfully with different config; Step 3 fails loudly.

---

## Scenario 3: Exact-term recall improvement (User Story 1, SC-002)

**Step 1** — Run a single exact-term query through both configurations and compare:
```bash
python - <<'EOF'
import asyncio
from rag.knowledge.retriever import ChromaKnowledgeRetriever

async def main():
    r = ChromaKnowledgeRetriever()
    chunks = await r.search(query="What does the Second Wind talent do?", campaign_id="", role="gm", top_k=10)
    for c in chunks:
        print(c.chunk_id, c.matched_signals, c.headline)

asyncio.run(main())
EOF
```
Run once with `HYBRID_SEARCH_ENABLED=false` and once with `HYBRID_SEARCH_ENABLED=true`.

**Expected**: With hybrid enabled, the chunk containing the literal term "Second Wind" appears in the candidate set with `matched_signals` including `"lexical"` (possibly both `"vector"` and `"lexical"`). If it was missing from the vector-only run, it is now present.

**Step 2** — Run the full gold-standard benchmark (Scenario 2, both configs) and inspect the `exact_term` row:
```bash
python -c "
from harness.knowledge_qa.test_gold_standard import compare_benchmark_runs
compare_benchmark_runs(-2, -1)
"
```
**Expected**: The `exact_term` row shows Recall@10/MRR improving by more than 2 percentage points from the vector-only run to the hybrid run (per spec.md's regression/improvement threshold), with no other category regressing by more than 2 percentage points.

**Pass criteria (SC-002)**: `exact_term` Recall@10 in the hybrid run exceeds the vector-only run by > 2 percentage points.

---

## Scenario 4: Downstream answer-quality comparison (User Story 2, SC-001/SC-003)

Reuses the spec 013 judge pipeline against both retrieval configurations.

```bash
# Baseline
HYBRID_SEARCH_ENABLED=false KNOWLEDGE_EMBED_PROVIDER=ollama KNOWLEDGE_EMBED_MODEL=nomic-embed-text KNOWLEDGE_LLM_MODEL=llama3.1 \
  python harness/knowledge_qa/eval_runner.py --campaign-id <YOUR_CAMPAIGN_UUID> --role gm --run-id baseline-014

JUDGE_PROVIDER=ollama JUDGE_MODEL=llama3.1 \
  python harness/knowledge_qa/judge_runner.py --run-id baseline-014 --summary

# Hybrid
HYBRID_SEARCH_ENABLED=true KNOWLEDGE_EMBED_PROVIDER=ollama KNOWLEDGE_EMBED_MODEL=nomic-embed-text KNOWLEDGE_LLM_MODEL=llama3.1 \
  python harness/knowledge_qa/eval_runner.py --campaign-id <YOUR_CAMPAIGN_UUID> --role gm --run-id hybrid-014

JUDGE_PROVIDER=ollama JUDGE_MODEL=llama3.1 \
  python harness/knowledge_qa/judge_runner.py --run-id hybrid-014 --summary
```

**Pass criteria (SC-001, SC-003)**: `judge_aggregate` mean for `hybrid-014` does not regress by more than 2 percentage points versus `baseline-014`, and Recall@10/MRR from Scenario 3 do not regress by more than 2 percentage points on any standard category.

---

## Scenario 5: Access-level filtering still applies to lexical results (spec.md edge case)

```bash
python - <<'EOF'
import asyncio
from rag.knowledge.retriever import ChromaKnowledgeRetriever

async def main():
    r = ChromaKnowledgeRetriever()
    chunks = await r.search(query="<a query matching GM-only content>", campaign_id="<CAMPAIGN_UUID>", role="player", top_k=10)
    assert all(c.access_level == "player_visible" for c in chunks)
    print("OK — no gm_only chunks leaked via lexical signal")

asyncio.run(main())
EOF
```

**Pass criteria (FR-003)**: No `gm_only` chunk appears for `role="player"`, with `HYBRID_SEARCH_ENABLED=true`.

---

## Debugging

Set `LOG_LEVEL=DEBUG` to see lexical query text, matched chunk IDs, and per-signal RRF contributions:
```bash
LOG_LEVEL=DEBUG HYBRID_SEARCH_ENABLED=true python -m pytest harness/knowledge_qa/test_retrieval.py -v -s
```

Inspect the lexical index directly:
```bash
sqlite3 data/storyweaver.db "SELECT chunk_id, scope, access_level, substr(text, 1, 80) FROM knowledge_lexical LIMIT 5;"
sqlite3 data/storyweaver.db "SELECT COUNT(*) FROM knowledge_lexical;"
```
