# Quickstart Validation Guide: PDF Extraction Quality & Corpus Cleaning v2

---

## Prerequisites

1. A local ChromaDB collection with at least one ingested PDF (or a fresh one for re-ingestion).
2. Ollama running locally (`ollama serve`) with at minimum:
   - A text generation model (e.g., `qwen2.5:7b` or your current `OLLAMA_MODEL`)
   - A vision model pulled for Scenario 3 (e.g., `ollama pull minicpm-v`)
3. Python environment set up: `uv sync` from repo root.
4. The ED4_Players_Guide PDF available at the path used during initial ingestion.

---

## Scenario 1: Enhanced Text Cleaning

**What this validates**: SC-001, SC-002, SC-003, SC-004, SC-005, FR-001–FR-009

### Setup

```bash
# Ensure no existing collection conflicts (or use a separate test collection name)
# Re-ingest with text extraction (default)
python -m apps.web.cli ingest path/to/ED4_Players_Guide.pdf
```

### Assertions to verify

After ingestion completes, connect to ChromaDB and run the diagnostic notebook or these manual checks:

```python
import chromadb
client = chromadb.PersistentClient(path="./data/chroma")
col = client.get_collection("knowledge_global")
all_docs = col.get(include=["documents", "metadatas"])

docs = all_docs["documents"]

# SC-001: Zero chunks with replacement character
assert not any("?" in d or "�" in d for d in docs), "Found encoding artifacts"

# SC-002: Fewer than 1% stubs
short = [d for d in docs if len(d) < 150]
assert len(short) / len(docs) < 0.01, f"{len(short)} stubs out of {len(docs)} chunks"

# SC-003: Zero oversized chunks
giant = [d for d in docs if len(d) > 15000]
assert len(giant) == 0, f"{len(giant)} oversized chunks remain"

# SC-004: Zero image placeholders or bare page numbers
import re
assert not any(re.search(r"==> picture", d) for d in docs)
assert not any(re.search(r"(?m)^\s*\d{1,4}\s*$", d) for d in docs)

# SC-005: Back-of-book pages produced zero chunks
# (Verify manually: search for "Kickstarter" or an A-Z index entry)
kickstarter_chunks = [d for d in docs if "kickstarter" in d.lower()]
assert len(kickstarter_chunks) == 0, "Backer list chunks still present"
```

**Expected outcome**: All assertions pass. Log output from the ingestion run should show `INFO` lines reporting stub merges and giant splits, and `WARNING` lines for any discarded structural noise pages.

---

## Scenario 2: Benchmark Baseline Delta

**What this validates**: SC-006, FR-016–FR-018

### Setup

```bash
# Run benchmark before and after re-ingestion to capture the delta
# Step 1: Run benchmark on the OLD corpus (before re-ingestion)
python harness/knowledge_qa/test_gold_standard.py

# Step 2: Re-ingest with new cleaning rules (Scenario 1 above)

# Step 3: Run benchmark on the NEW corpus
python harness/knowledge_qa/test_gold_standard.py
```

### Compare

```python
# In a Python shell or notebook:
from harness.knowledge_qa.test_gold_standard import compare_benchmark_runs

# Compare second-to-last (before) vs last (after)
compare_benchmark_runs(-2, -1)
```

**Expected output**: A diff table with one row per category plus a global row. The global Recall@10 delta (ΔRecall) should be ≥ +0.05 (SC-006 — 5 pp improvement).

**Example output format**:
```
Category       MRR-A  MRR-B  ΔMRR    nDCG-A  nDCG-B  ΔnDCG   Recall-A  Recall-B  ΔRecall
-----------    -----  -----  -----   ------  ------  ------  --------  --------  -------
direct_fact    0.62   0.71   +0.09   0.58    0.67    +0.09   0.70      0.78      +0.08
comparison     0.55   0.58   +0.03   0.51    0.54    +0.03   0.65      0.68      +0.03
holistic       0.48   0.52   +0.04   0.45    0.49    +0.04   0.60      0.64      +0.04
numeric        0.70   0.79   +0.09   0.67    0.76    +0.09   0.80      0.88      +0.08
relationship   0.58   0.63   +0.05   0.55    0.60    +0.05   0.68      0.73      +0.05
global         0.59   0.65   +0.06   0.55    0.61    +0.06   0.69      0.74      +0.05
```

---

## Scenario 3: Vision Extraction Path

**What this validates**: SC-007, FR-010–FR-015

### Prerequisites

```bash
# Pull a vision model (first time only)
ollama pull minicpm-v
```

### Setup

```bash
export KNOWLEDGE_VISION_MODEL=minicpm-v

# Re-ingest using vision extraction
python -m apps.web.cli ingest path/to/ED4_Players_Guide.pdf --extraction-mode vision
```

### Assertions

**SC-007 — drop-cap quality (manual spot-check)**:

After ingestion, find 10 chapter-opening chunks (chunks where the breadcrumb is `doc_title > Chapter N`):

```python
results = col.get(where={"extraction_mode": "vision"}, include=["documents", "metadatas"])
# Pick the first chunk of each chapter breadcrumb
# Verify: each starts with a complete word (not "nce, long ago" or "avon woke")
```

At least 8 of the 10 spot-checked sentences must begin with a capital letter that is the first letter of a complete word.

**FR-015 — extraction_mode metadata**:

```python
metas = results["metadatas"]
assert all(m.get("extraction_mode") in ("text", "vision") for m in metas), \
    "Some chunks missing extraction_mode metadata"
```

**FR-013 — per-page fallback (triggerable by pausing Ollama mid-ingestion)**:

Watch the ingestion log for `WARNING` lines like:
```
WARNING packages.rag.rag.knowledge.ingestor: Vision extraction failed for page 42: ... — falling back to text
```

The ingestion must continue to completion despite the fallback.

### Compare vision vs text

```python
compare_benchmark_runs(-2, -1)
# -2 = text run, -1 = vision run
# Examine which categories improve under vision extraction
```

---

## Scenario 4: Comparison Tool Error Handling

**What this validates**: FR-018

```python
from harness.knowledge_qa.test_gold_standard import compare_benchmark_runs

# Should exit with a clear error naming the bad selector
try:
    compare_benchmark_runs(999, -1)
except ValueError as e:
    print(e)
    # Expected: "Selector 999 out of range. Available records: [timestamps...]"
```

---

## Scenario 5: Breadcrumb Markdown Stripping

**What this validates**: FR-009

After re-ingestion, verify that no breadcrumb path contains `*`, `_`, or `**`:

```python
metas = col.get(include=["metadatas"])["metadatas"]
bc_field = "breadcrumb"
bad = [m[bc_field] for m in metas if bc_field in m and re.search(r'[*_`]', m[bc_field])]
assert len(bad) == 0, f"Markdown in breadcrumbs: {bad[:3]}"
```

**Expected**: Empty list. Before the fix, breadcrumbs like `ED4_Players_Guide > _**Versatility**_` would have appeared here.

---

## Environment Variables Reference

| Variable | Required for | How to set |
|----------|-------------|------------|
| `KNOWLEDGE_VISION_MODEL` | Vision path | `export KNOWLEDGE_VISION_MODEL=minicpm-v` |
| `KNOWLEDGE_VISION_TIMEOUT_SECS` | Vision path | `export KNOWLEDGE_VISION_TIMEOUT_SECS=180` |
| `KNOWLEDGE_MIN_CHUNK_CHARS` | Quality gate | `export KNOWLEDGE_MIN_CHUNK_CHARS=150` |
| `KNOWLEDGE_MAX_CHUNK_CHARS` | Quality gate | `export KNOWLEDGE_MAX_CHUNK_CHARS=15000` |

---

## Contracts & Data Model

- [VisionLLMProvider contract](contracts/vision-llm-provider.md)
- [IngestionConfig contract](contracts/ingestion-config.md)
- [Data model](data-model.md)
