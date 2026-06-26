# Quickstart Validation Guide: Feature 010

**Prerequisites**: Ollama running locally, Earthdawn rulebook PDF ingested into ChromaDB, `uv` installed.

---

## US1 — Per-Category Benchmark Visibility

**Goal**: Confirm per-category MRR, nDCG, and Recall@10 appear in terminal output and `benchmark_results.jsonl` without re-ingestion.

**Setup**: None — runs against the current index.

```bash
# From repo root
uv run pytest harness/knowledge_qa/test_gold_standard.py -v -s
```

**Expected terminal output** (after the run):

```
=== Per-Category Results ===
Category        Questions  MRR     nDCG    Recall@10
direct_fact     40         0.XXX   0.XXX   0.XXX
comparison      25         0.XXX   0.XXX   0.XXX
holistic        30         0.XXX   0.XXX   0.XXX
numeric         15         0.XXX   0.XXX   0.XXX
relationship    8          0.XXX   0.XXX   0.XXX
uncategorized   0          0.000   0.000   0.000
=== Global ===
Total: 118   MRR: 0.XXX   nDCG: 0.XXX   Recall@10: 0.XXX
```

**Expected JSONL**: Verify the new record includes `category_scores`:

```bash
uv run python -c "
import json
from pathlib import Path
last = json.loads(Path('harness/knowledge_qa/benchmark_results.jsonl').read_text().strip().splitlines()[-1])
assert 'category_scores' in last, 'category_scores missing'
cats = set(last['category_scores'])
assert 'direct_fact' in cats and 'uncategorized' in cats, f'unexpected categories: {cats}'
print('OK — categories:', sorted(cats))
"
```

**Acceptance**: All five categories shown; `uncategorized` row present; `category_scores` in JSONL (SC-001, SC-002, FR-001–003).

---

## US2 — Breadcrumb-Enriched Chunks

**Goal**: After re-ingestion with breadcrumbs enabled, every retrieved chunk starts with a structural breadcrumb.

```bash
uv run python - <<'EOF'
import asyncio
from rag.knowledge.pipeline import IngestionPipeline
from rag.knowledge.interface import IngestionConfig

async def main():
    await IngestionPipeline().run(
        doc_id="<YOUR_DOC_UUID>",
        file_path="path/to/earthdawn-chapter2.pdf",
        format="pdf",
        scope="global",
        campaign_id=None,
        config=IngestionConfig(enable_breadcrumbs=True),
    )

asyncio.run(main())
EOF
```

**Spot-check**: Retrieve 10 chunks and inspect the breadcrumb field and text prefix.

```bash
uv run python - <<'EOF'
import asyncio
from rag.knowledge.retriever import ChromaKnowledgeRetriever

async def main():
    chunks = await ChromaKnowledgeRetriever().search(
        "What is the Movement Rate of a dwarf?", campaign_id="", role="gm", top_k=10
    )
    for i, c in enumerate(chunks, 1):
        print(f"--- chunk {i} ---")
        print("breadcrumb:", c.breadcrumb)
        print("text[:120]:", c.text[:120])
        print()

asyncio.run(main())
EOF
```

**Expected**: Every chunk has a non-empty `breadcrumb` field containing the document name and at least one heading level. `text` starts with the same breadcrumb (SC-003, FR-004–006).

---

## US3 — Contextual Summaries for Semantic Retrieval

**Goal**: After re-ingestion with contextual summaries enabled, vocabulary-mismatched queries retrieve the correct chunk.

```bash
uv run python - <<'EOF'
import asyncio
from rag.knowledge.pipeline import IngestionPipeline
from rag.knowledge.interface import IngestionConfig

async def main():
    await IngestionPipeline().run(
        doc_id="<YOUR_DOC_UUID>",
        file_path="path/to/earthdawn-players-guide.pdf",
        format="pdf",
        scope="global",
        campaign_id=None,
        config=IngestionConfig(
            enable_breadcrumbs=True,
            enable_contextual_summaries=True,
        ),
    )

asyncio.run(main())
EOF
```

**Log verification** — confirm INFO lines appear per chunk:

```bash
LOG_LEVEL=INFO uv run python <script_above> 2>&1 | grep "contextual_summary"
```

**Benchmark re-run** and compare `holistic` + `comparison` scores against the pre-feature baseline in `benchmark_results.jsonl`:

```bash
uv run pytest harness/knowledge_qa/test_gold_standard.py -v -s
```

**Acceptance**: At least 3 of 5 previously-failing holistic/comparison questions now retrieve the correct chunk in top-10 (SC-004, FR-007–009).

---

## US4 — Source-Type Metadata Tagging

**Goal**: Confirm `source_type` is stored in chunk metadata and surfaced on `KnowledgeChunk`.

```bash
uv run python - <<'EOF'
import asyncio
from rag.knowledge.pipeline import IngestionPipeline
from rag.knowledge.interface import IngestionConfig

async def main():
    await IngestionPipeline().run(
        doc_id="<YOUR_SUPPLEMENT_DOC_UUID>",
        file_path="path/to/supplement.pdf",
        format="pdf",
        scope="global",
        campaign_id=None,
        config=IngestionConfig(source_type="supplement"),
    )

asyncio.run(main())
EOF
```

**Spot-check**:

```bash
uv run python - <<'EOF'
import asyncio
from rag.knowledge.retriever import ChromaKnowledgeRetriever

async def main():
    chunks = await ChromaKnowledgeRetriever().search(
        "some query from the supplement", campaign_id="", role="gm", top_k=5
    )
    for c in chunks:
        print(f"source_type={c.source_type!r}  chunk_id={c.chunk_id}")

asyncio.run(main())
EOF
```

**Expected**: Supplement chunks show `source_type='supplement'`; rulebook chunks show `source_type='rulebook'` (FR-010–011). No retrieval filter is applied — all source types are always considered at query time.

---

## Regression Check

```bash
uv run pytest packages/rag/tests/ harness/knowledge_qa/ -v
uv run ruff check packages/rag/ harness/
uv run pyright packages/rag/
```

All checks must pass before the feature is considered complete.
