# Quickstart: Validating Appendage Section Merging

**Feature**: 009-appendage-section-merge
**Date**: 2026-06-26

---

## Prerequisites

- Python environment activated (`uv sync` from repo root)
- Ollama running with `llama3.1` and `nomic-embed-text` pulled
- `.env` loaded (or env vars set in shell)
- An Earthdawn 4E PDF available (e.g. ED4_Players_Guide.pdf)

---

## Scenario 1 — Unit: prose ratio classification

Run the unit tests for the new `_is_appendage_section` logic:

```bash
cd packages/rag
pytest tests/knowledge/test_chunker_agentic.py -v -k "appendage"
```

**Expected**: All appendage classification tests pass. A section with only attribute lines (DEX, STR, table rows) is classified as an appendage. A section with a prose paragraph is not.

---

## Scenario 2 — Unit: merge step preserves subject context

```bash
cd packages/rag
pytest tests/knowledge/test_chunker_agentic.py -v -k "merge"
```

**Expected**: The merge test verifies that after `_merge_appendage_sections`, a race-description section followed by a stat-block section produces a single combined section containing both the race name and the attribute values.

---

## Scenario 3 — Integration: stat block chunks carry entity name

Ingest a real rulebook section and query for an attribute value:

```python
# Run from repo root in a Python shell or scratch script
import asyncio, os
os.environ["LOG_LEVEL"] = "INFO"

from rag.knowledge.ingestor import PdfIngestor
chunks = asyncio.run(PdfIngestor().ingest_async("path/to/ED4_Players_Guide.pdf"))

# Find chunks containing DEX and check for race name
dex_chunks = [c for c in chunks if "DEX" in c]
for c in dex_chunks[:3]:
    print("---")
    print(c[:400])
```

**Expected**: Each chunk containing "DEX" also contains a race or creature name (e.g. "T'skrang", "Troll", "Windling") in the same text block. No chunk should be only `DEX 11, STR 10…` with no subject.

**Log lines to look for**:
```
INFO:rag.knowledge.chunker_agentic:[agentic-chunker] Merged appendage section into preceding …
```

---

## Scenario 4 — Threshold tuning

```bash
KNOWLEDGE_AGENTIC_PROSE_THRESHOLD=0.5 python -c "
import asyncio, os
from rag.knowledge.ingestor import PdfIngestor
chunks = asyncio.run(PdfIngestor().ingest_async('path/to/ED4_Players_Guide.pdf'))
print(f'{len(chunks)} chunks produced')
"
```

Run again with `KNOWLEDGE_AGENTIC_PROSE_THRESHOLD=0.1` and compare chunk counts.

**Expected**: Higher threshold → more merges → fewer total chunks. Lower threshold → fewer merges → more total chunks. No code changes required.

---

## Scenario 5 — Size cap guard

Create a synthetic test where an appendage section that would exceed `max_tokens * 4` when merged is left standalone:

```bash
cd packages/rag
pytest tests/knowledge/test_chunker_agentic.py -v -k "size_cap"
```

**Expected**: The oversized appendage is emitted as a separate chunk rather than merged; no exception raised; INFO log indicates the merge was skipped.

---

## What to check in logs

With `LOG_LEVEL=INFO`:

| Log message | Meaning |
|---|---|
| `[agentic-chunker] Merged appendage section into preceding (prose ratio: X%, first: '...')` | Section was detected as data-heavy and merged |
| `[agentic-chunker] Skipping merge — size cap would be exceeded` | Appendage left standalone to avoid oversized section |
| `[agentic-chunker] Skipping LLM for sections N-M of T (all within token limit)` | Fast-path still active for already-small merged sections |