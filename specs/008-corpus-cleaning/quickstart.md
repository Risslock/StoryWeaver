# Quickstart & Validation Guide: Corpus Pre-Processing & Cleaning

**Feature**: `008-corpus-cleaning`
**Date**: 2026-06-25

This guide describes how to validate the feature end-to-end after implementation. It does
not reproduce implementation code; see [data-model.md](data-model.md) for type definitions
and [contracts/cleaner-api.md](contracts/cleaner-api.md) for the `CorpusCleaner` interface.

---

## Prerequisites

- Ollama running locally (`ollama serve`) with `llama3.1` and `nomic-embed-text` pulled.
- ChromaDB accessible (default: local persistent store in `./chroma_data`).
- SQLite DB initialized (`uv run alembic upgrade head`).
- At least one ingested Earthdawn PDF (e.g., `ED4-Players-Guide.pdf`) available locally.
- Gold standard questions in `harness/knowledge_qa/rag_gold_standard.jsonl` (118 questions).

---

## Step 1 — Unit Test the Cleaner (No Ollama Required)

Run the cleaner unit tests in isolation to verify each rule before touching the full pipeline:

```bash
uv run pytest packages/rag/tests/knowledge/test_cleaner.py -v
```

**What to expect**:
- De-hyphenation: `"kar-\nma"` → `"karma"`, `"one-shot"` unchanged.
- TOC stripping: a fixture with 20 TOC-like lines → stripped; 3-line list → preserved.
- Front matter: copyright page on page 0 → stripped; same text on page 12 → preserved.
- Stat block: a fixture with `DEX: 6  STR: 8  TOU: 9` lines → normalised as Markdown table rows.
- Source type gating: `source_type="novel"` skips stat block and TOC rules; `"handwritten"`
  skips all except de-hyphenation.
- Bypass: `KNOWLEDGE_CLEANING_ENABLED=false` produces identical output to uncleaned input.

All tests must pass without Ollama, ChromaDB, or any network access.

---

## Step 2 — Verify the UI Dropdown

Start the Gradio app:

```bash
uv run python -m apps.web.main
```

Open the Knowledge Q&A tab → Upload Document accordion. Confirm:
- A "Source type" dropdown is visible with options: `rulebook`, `supplement`, `novel`, `handwritten`.
- The dropdown defaults to `rulebook`.
- Upload a PDF with the dropdown set to `rulebook`. Confirm ingestion starts and the document
  appears in the Ingested Documents table with the correct source type shown.

---

## Step 3 — Ingest a Structured PDF and Inspect Chunks

**Setup**: Clear the existing vector store (rename `./chroma_data` or delete the collections)
and re-ingest a rulebook PDF that contains multi-column tables, stat blocks, and a TOC.

```bash
# Optional: check the log for cleaning messages
LOG_LEVEL=WARNING uv run python -c "
import asyncio
from rag.knowledge.pipeline import IngestionPipeline
asyncio.run(IngestionPipeline().run(
    doc_id='test-doc-id',
    file_path='/path/to/ED4-Players-Guide.pdf',
    format='pdf',
    access_level_default=None,
    scope='global',
    campaign_id=None,
    source_type='rulebook',
))
"
```

**What to check in the logs** (`LOG_LEVEL=WARNING`):
- At least one `[corpus-cleaner] Stripped TOC section` line.
- At least one `[corpus-cleaner] Removed front matter page` line.
- At least one `[corpus-cleaner] Rejoined N hyphenated line-breaks` line (N > 0).
- Optionally: `[corpus-cleaner] Reconstructed stat block` or `multi-column layout` lines.

No `[corpus-cleaner]` lines should appear for transformations that didn't fire — zero-count
fields are silent.

---

## Step 4 — Targeted Retrieval Checks (Acceptance Scenarios)

After re-ingestion, run these spot checks via the Gradio UI or directly via the retriever.
Each maps to an acceptance scenario in the spec.

### Scenario A — Multi-Column Table (User Story 1, AC 1)

Ask: `"What are the attribute modifiers for a Windling?"`

**Pass criterion**: The cited chunk contains racial attribute values in correct column order
(not interleaved content from adjacent columns). The answer references correct numeric values.

### Scenario B — Stat Block (User Story 1, AC 2)

Ask: `"What are the DEX, STR, and TOU steps for a Windling?"`

**Pass criterion**: The returned chunk contains a coherent key-value list or Markdown table
with the correct attribute values — not scrambled lines from a top-to-bottom column read.

### Scenario C — De-Hyphenation (User Story 2)

1. In the raw PDF Markdown (before cleaning), find a term that appears hyphenated, e.g., search
   the raw pymupdf4llm output for `karma` appearing as `kar-\nma` or similar.
2. After ingestion with cleaning, ask: `"What is karma?"` or `"How does the karma system work?"`

**Pass criterion**: The chunk containing the formerly-broken term is retrieved. The text in the
chunk shows the natural form (`karma`, not `kar-\nma`).

**Regression check**: Temporarily ingest the same PDF with `KNOWLEDGE_CLEANING_ENABLED=false`.
Run the same query. Confirm the relevant chunk is NOT retrieved (or ranks much lower), proving
the fix was responsible for the improvement.

### Scenario D — No TOC/Front Matter Chunks (User Story 3)

Inspect the ChromaDB global collection for any stored chunk that consists primarily of TOC
entries (lines ending in page numbers with dot leaders) or front matter (copyright text,
dedications).

```bash
uv run python -c "
import chromadb
client = chromadb.PersistentClient('./chroma_data')
coll = client.get_collection('knowledge_global')
results = coll.get(limit=500, include=['documents'])
for doc in results['documents']:
    if '......' in doc or 'Copyright' in doc[:100]:
        print('POTENTIAL FALSE POSITIVE:', doc[:200])
"
```

**Pass criterion**: No chunk is flagged.

### Scenario E — Clean PDF Unchanged (SC-007)

Ingest a short, single-column Markdown file (e.g., `harness/knowledge_qa/fixtures/sample_rules.md`)
with `source_type="rulebook"` and `KNOWLEDGE_CLEANING_ENABLED=true`.

Verify the ingested chunks match what would be produced without cleaning by comparing chunk texts
directly (same content, same structure, no additions or removals attributable to the cleaner).

---

## Step 5 — Gold Standard Evaluation

After re-ingesting the full corpus with cleaning enabled:

```bash
uv run pytest harness/knowledge_qa/test_gold_standard.py -v -s
```

**Pass criteria** (SC-003 and SC-004):
- Mean MRR ≥ 0.5767 (agentic-chunker baseline from spec 007)
- Mean Recall@10 ≥ 0.8966
- At least one of {MRR, nDCG, Recall@10} strictly above the baseline

New scores are appended to `harness/knowledge_qa/benchmark_results.jsonl` with
`strategy="agentic+cleaning"` and `notes` describing the configuration.

---

## Step 6 — Bypass Regression Check

Verify that disabling cleaning produces no regressions in chunking behaviour:

```bash
KNOWLEDGE_CLEANING_ENABLED=false uv run pytest packages/rag/tests/ -v
```

All existing tests must pass. The bypass path should produce the same results as before
this feature was introduced (raw pymupdf4llm output → chunker, no new filtering).

---

## Step 7 — Logging Smoke Check

Confirm structured log output at multiple levels:

```bash
LOG_LEVEL=DEBUG uv run python -c "
import asyncio, logging
logging.basicConfig(level=logging.DEBUG)
from rag.knowledge.pipeline import IngestionPipeline
asyncio.run(IngestionPipeline().run(
    doc_id='smoke-test',
    file_path='/path/to/any.pdf',
    format='pdf',
    access_level_default=None,
    scope='global',
    campaign_id=None,
    source_type='rulebook',
))
"
```

**Confirm**:
- WARNING lines appear for each transformation that fired.
- DEBUG lines appear for unrecognised blocks passed through unchanged.
- No bare `print()` output from the cleaning module (Principle VIII).
- No crash when cleaning finds nothing to transform (all-zero report is valid).
