# Results: Vision Extraction Benchmark (feature 015)

Running lab notebook for the benchmark. Filled in as each phase completes (tasks.md).

## T001 — Environment verification (2026-07-07)

Ollama reachable at `http://localhost:11434`. Models pulled (relevant subset):

| Role | Model | Pulled? |
|---|---|---|
| Vision extraction | `blaifa/Nanonets-OCR-s:latest` | ✅ |
| Embedding | `nomic-embed-text:latest` | ✅ |
| Enrich | `llama3.1:latest` | ✅ |
| Answer LLM | `llama3.1:latest` | ✅ |
| Judge (`JUDGE_MODEL`) | `llama3.1` (via `JUDGE_PROVIDER=ollama`) | ✅ |

Corpus source PDF located at `C:\Users\juane\Documents\Juanes\Hobbies\Rol\Earthdawn\ED4_Players_Guide.pdf` (not tracked in the repo — operator-local path).

Existing `knowledge_documents` row for the corpus: `id=bf5af91681744f16842fda4f583a18a0`, `scope=global`, `title=ED4_Players_Guide`, `format=pdf`, `ingestion_status=ready`, `chunk_count=780` (current production state — this is the collection that will be clean-slated and re-ingested twice by this benchmark).

## T002 — Held-fixed config snapshot (2026-07-07)

Captured from `.env` at benchmark start — these MUST be identical across the Docling and Vision legs (FR-009):

```
KNOWLEDGE_CHUNKING_STRATEGY=agentic
KNOWLEDGE_MAX_CHUNK_TOKENS=2500
KNOWLEDGE_CHUNK_OVERLAP_TOKENS=200
KNOWLEDGE_MIN_CHUNK_CHARS=300
KNOWLEDGE_MAX_CHUNK_CHARS=15000
KNOWLEDGE_AGENTIC_BATCH_SECTIONS=10
KNOWLEDGE_AGENTIC_SKIP_TOKENS=500
KNOWLEDGE_AGENTIC_PROSE_THRESHOLD=0.4
KNOWLEDGE_ENRICH_MODEL=llama3.1
KNOWLEDGE_EMBED_MODEL=nomic-embed-text
KNOWLEDGE_ENRICH_BATCH_SIZE=6
KNOWLEDGE_TOP_K=10
KNOWLEDGE_RRF_K=60
KNOWLEDGE_EXPANSION_COUNT=1
HYBRID_SEARCH_ENABLED=true
HYBRID_SEARCH_KEYWORD_WEIGHT=1.0
HYBRID_SEARCH_VECTOR_WEIGHT=1.0
JUDGE_PROVIDER=ollama
JUDGE_MODEL=llama3.1
gold_standard_path=harness/knowledge_qa/rag_gold_standard.jsonl (118 questions)
```

New for this feature (both legs, once Phase 2 lands):

```
KNOWLEDGE_EVAL_TEMPERATURE=0.0   # greedy decoding (FR-018)
```

Only `IngestionConfig.extraction_mode` (`"docling_text"` vs `"vision"`) differs between the two legs.

**Correction found while building `spot_check.py`** (verified against the live collection): the currently-ingested production ED4_Players_Guide collection (780 chunks) has `extraction_mode="docling_text"` in its chunk metadata, not plain `"docling"`. This is correct and intentional — plain `"docling"` uses Docling's own `HybridChunker`, while `"docling_text"` and `"vision"` both use the shared, configurable `create_chunker()` (`KNOWLEDGE_CHUNKING_STRATEGY=agentic`). The Docling leg of this benchmark uses `extraction_mode="docling_text"` so the chunker is held fixed against the vision leg — using plain `"docling"` would have confounded two variables. All design docs (plan.md, research.md, data-model.md, contracts/, quickstart.md, tasks.md) were updated to reflect this.

---

## Phase 3 — Docling leg

*(pending — filled in when the leg runs)*

## Phase 4 — Vision leg

*(pending — filled in when the leg runs)*

## Phase 5 — Comparison & decision

*(pending)*
