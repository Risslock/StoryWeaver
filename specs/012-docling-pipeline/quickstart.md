# Quickstart: Validating the Docling Ingestion Pipeline (012)

*End-to-end validation guide for the Docling pipeline. Run this after implementation to confirm all acceptance criteria are met.*

---

## Prerequisites

1. **Dependencies installed**: `uv sync` from repo root — `docling` and `transformers` must be present in `packages/rag/`.
2. **Docling model cache**: The first run downloads layout ML models (~1–2 GB) to `~/.cache/docling`. Subsequent runs use the cache.
3. **ED4_Players_Guide PDF**: Available locally (not redistributed).
4. **ChromaDB**: `./data/chroma` directory writable.
5. **Ollama running** (for local provider): `http://localhost:11434` reachable.

---

## Scenario A: Docling Ingestion (Ollama provider)

### 1. Set environment

```bash
# .env or shell
KNOWLEDGE_ENRICH_PROVIDER=ollama
KNOWLEDGE_EMBED_PROVIDER=ollama
KNOWLEDGE_ENRICH_MODEL=llama3.2
KNOWLEDGE_EMBED_MODEL=nomic-ai/nomic-embed-text-v1.5   # uses truncate_dim=256 in Ollama embed calls
OLLAMA_BASE_URL=http://localhost:11434
# KNOWLEDGE_DOCLING_PAGE_BATCH_SIZE=10                 # optional; increase for speed, decrease for low RAM
```

### 2. Run ingestion

```python
from rag.knowledge.pipeline import IngestionPipeline
from rag.knowledge.interface import IngestionConfig
import asyncio

pipeline = IngestionPipeline()
config = IngestionConfig(extraction_mode="docling", source_type="rulebook")
asyncio.run(pipeline.run(
    doc_id="<uuid>",
    file_path="path/to/ED4_Players_Guide.pdf",
    format="pdf",
    scope="global",
    campaign_id=None,
    config=config,
))
```

### 3. Expected outcomes

Run inspection queries against `knowledge_global` collection after ingestion completes.

| Criterion | Check |
|-----------|-------|
| SC-001: Zero image placeholder chunks | No chunk in `original_text` contains `"==> picture"` or `"--- Start of picture text ---"` |
| SC-002: Zero furniture chunks | No chunk body contains an isolated integer line (page number) |
| SC-003: ≥86 structured table chunks | At least 86 chunks contain Markdown table content (`\|...\|` in coherent rows, not pipe-row micro-chunks) |
| SC-004: ≥96.7% breadcrumb coverage | At least 1392 of 1439 chunks have `breadcrumb != ""` in metadata |
| SC-006: ≥99 stat-block hits | CorpusCleaner stat-block detection reports ≥99 hits |
| SC-008: Required metadata fields | Every chunk has: `breadcrumb`, `original_text`, `extraction_mode="docling"`, `source_type` |

### 4. Inspect metadata (quick check)

```python
from rag.knowledge.vector_store import ChromaVectorStore

store = ChromaVectorStore()
col = store.collection("knowledge_global")
result = col.get(include=["metadatas"])
metas = result["metadatas"]

# SC-001
placeholder_chunks = [m for m in metas if "==> picture" in m.get("original_text", "")]
assert len(placeholder_chunks) == 0, f"Found {len(placeholder_chunks)} image placeholder chunks"

# SC-004
with_breadcrumb = [m for m in metas if m.get("breadcrumb", "")]
print(f"Breadcrumb coverage: {len(with_breadcrumb)}/{len(metas)} ({100*len(with_breadcrumb)/len(metas):.1f}%)")
assert len(with_breadcrumb) / len(metas) >= 0.967

# SC-008: extraction_mode
docling_chunks = [m for m in metas if m.get("extraction_mode") == "docling"]
assert len(docling_chunks) == len(metas), "Not all chunks have extraction_mode=docling"
```

---

## Scenario B: HuggingFace Provider Switch

### 1. Set environment (no code changes)

```bash
KNOWLEDGE_ENRICH_PROVIDER=huggingface
KNOWLEDGE_EMBED_PROVIDER=huggingface
KNOWLEDGE_ENRICH_MODEL=mistralai/Mistral-7B-Instruct-v0.3
KNOWLEDGE_EMBED_MODEL=BAAI/bge-m3                        # or sentence-transformers/all-MiniLM-L6-v2 as fallback
HF_API_KEY=hf_...
```

### 2. Run ingestion on a small document (5-page test PDF)

Same pipeline call as Scenario A. Expected outcomes:
- Enrichment LLM calls go to `https://api-inference.huggingface.co/...` (verify via `LOG_LEVEL=DEBUG`)
- Embedding calls go to `https://api-inference.huggingface.co/models/nomic-ai/nomic-embed-text-v1`
- ChromaDB chunks have all required metadata fields populated (SC-010)

### 3. Verify no Ollama calls

With `LOG_LEVEL=DEBUG`, confirm that no log lines reference `localhost:11434` while `KNOWLEDGE_ENRICH_PROVIDER=huggingface`.

---

## Scenario C: Missing Env Var Abort (SC-011)

### Test: KNOWLEDGE_ENRICH_MODEL absent

```bash
unset KNOWLEDGE_ENRICH_MODEL
```

Run the pipeline. Expected:
- Pipeline logs `ERROR: KNOWLEDGE_ENRICH_MODEL is required but not set`
- Pipeline aborts within 1 second of startup
- No partial document processing occurs

Repeat for `KNOWLEDGE_EMBED_MODEL`, `KNOWLEDGE_ENRICH_PROVIDER`, `KNOWLEDGE_EMBED_PROVIDER`.

---

## Scenario D: Legacy Path Deprecation Warning (SC-009)

```python
import logging, io
from rag.knowledge.ingestor import PdfIngestor   # legacy

buf = io.StringIO()
handler = logging.StreamHandler(buf)
logging.getLogger("rag.knowledge.ingestor").addHandler(handler)

PdfIngestor()  # or extract_with_context — must emit WARNING

output = buf.getvalue()
assert "deprecated" in output.lower(), "Expected deprecation WARNING"
assert "012" in output, "Expected feature number in deprecation message"
```

---

## Scenario E: Retrieval Quality (SC-007)

After Docling ingestion:

1. Run the existing benchmark harness against `benchmark_results.jsonl` (feature 011 baseline).
2. Confirm Recall@10 is equal to or exceeds the 011 text-path baseline.

```bash
cd harness
pytest tests/test_retrieval_benchmark.py -v
```

Expected: All benchmark assertions pass; no Recall@10 regression.

---

## References

- [spec.md](spec.md) — acceptance scenarios and success criteria
- [data-model.md](data-model.md) — full ChromaDB metadata schema
- [contracts/ingestion-pipeline.md](contracts/ingestion-pipeline.md) — public interface contracts
- [research.md](research.md) — Docling API details and HF endpoint format
