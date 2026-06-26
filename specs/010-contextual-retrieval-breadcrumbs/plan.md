# Implementation Plan: Contextual Retrieval, Breadcrumb Injection, Multi-Source Corpus & Per-Category Benchmarking

**Branch**: `010-contextual-retrieval-breadcrumbs` | **Date**: 2026-06-26 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/010-contextual-retrieval-breadcrumbs/spec.md`

## Summary

Four additions to the RAG ingestion and evaluation pipeline: (1) per-category metric breakdown in the benchmark harness — no re-ingestion required; (2) breadcrumb injection — every chunk prefixed with its document/chapter/section path before embedding; (3) contextual summaries — opt-in per-chunk LLM summary prepended to compound text at ingestion time; (4) `source_type` metadata tag stored on every chunk — no retrieval-time filter (the LLM and prompt layer handle source-type awareness).

This feature also introduces `IngestionConfig`, a single config dataclass that consolidates all preprocessing options onto `IngestionPipeline.run()`, replacing the scattered keyword arguments that were accumulating. This is the structural cleanup point for the pipeline.

## Technical Context

**Language/Version**: Python 3.11+

**Primary Dependencies**: `chromadb >= 0.4`, `pymupdf4llm`, `pydantic-ai`, `storyweaver-llm` (OllamaProvider), `fitz` (PyMuPDF)

**Storage**: ChromaDB (vector + compound text + per-chunk metadata), SQLite via `storyweaver-storage` (ingestion progress)

**Testing**: pytest, ruff, pyright

**Target Platform**: Local Linux/macOS (Docker Compose); Ollama required for ingestion and retrieval

**Project Type**: Python packages monorepo — changes confined to `packages/rag/` and `harness/knowledge_qa/`

**Performance Goals**: No throughput regression at retrieval time. Contextual summary adds one Ollama call per chunk at ingestion time — acceptable one-time cost.

**Constraints**: Local-first (Ollama). Breadcrumbs computed without LLM calls. Full re-ingestion required when enabling breadcrumbs or contextual summaries on an existing index.

**Scale/Scope**: ~118 gold standard questions; typical rulebook 50–300 chunks per document

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Spec-Driven | ✅ PASS | `spec.md` complete and accepted |
| II. Provider Abstraction | ✅ PASS | Contextual summary uses existing `OllamaProvider` via `ChunkEnricher` — no new provider binding |
| III. Package Isolation | ✅ PASS | All changes in `packages/rag/` and `harness/`; no new packages |
| IV. Local-First | ✅ PASS | All new LLM calls go to Ollama; no cloud required |
| V. Harness-Driven Quality | ✅ PASS | US1 (per-category benchmarking) is runnable against the current index with no re-ingestion |
| VI. Product-First | ✅ PASS | Direct retrieval quality improvement |
| VII. Placeholder-First | ✅ PASS | New pipeline flags default to unchanged existing behaviour; re-ingestion requirement is documented |
| VIII. Structured Logging | ✅ PASS | FR-009 requires INFO per summary attempt and WARNING on fallback — matches Principle VIII severity rules |

**No gate violations.**

## Project Structure

### Documentation (this feature)

```text
specs/010-contextual-retrieval-breadcrumbs/
├── plan.md              ← this file
├── research.md          ← Phase 0 output
├── data-model.md        ← Phase 1 output
├── quickstart.md        ← Phase 1 output
├── contracts/
│   ├── ingestion-pipeline.md   ← IngestionConfig + updated run() signature
│   ├── retriever.md            ← KnowledgeChunk extended fields
│   └── benchmark-results.md   ← JSONL schema with category_scores
└── tasks.md             ← Phase 2 output (/speckit-tasks — not created here)
```

### Source Code (repository root)

```text
packages/rag/rag/knowledge/
├── interface.py         # Add IngestionConfig dataclass; add breadcrumb + source_type to KnowledgeChunk
├── ingestor.py          # Add extract_with_context() → (full_md_text, chunks); existing ingest() unchanged
├── breadcrumb.py        # NEW: BreadcrumbExtractor — deterministic heading scan, no deps
├── enricher.py          # Add generate_contextual_summaries(texts, breadcrumbs, doc_title) → list[str]
├── pipeline.py          # run() takes IngestionConfig; orchestrates all five stages cleanly
└── retriever.py         # Read breadcrumb + source_type from metadata → KnowledgeChunk fields

apps/web/services/knowledge.py
# _run_pipeline() updated to construct IngestionConfig and pass it to pipeline.run()

packages/rag/rag/knowledge/evaluator.py
# Add CategoryMetrics; extend EvalSummary.category_scores; extend aggregate_results()

harness/knowledge_qa/
└── test_gold_standard.py    # Add per-category aggregation, terminal display, JSONL output
```

### Pipeline stage flow (pipeline.py)

```
1. _extract(file_path, format, config)
       → PdfIngestor/MarkdownIngestor.extract_with_context()
       → tuple[full_md_text, list[chunks]]

2. _compute_breadcrumbs(full_md_text, chunks, doc_title, config)
       → BreadcrumbExtractor().extract()  [only if config.enable_breadcrumbs]
       → list[breadcrumb_str]   (one per chunk; "" when no heading found)

3. Per batch: enricher.enrich_batch(batch)
       → list[ChunkEnrichment]  (headline / summary / topic / access_level)

4. Per batch: enricher.generate_contextual_summaries(batch, batch_breadcrumbs, doc_title)
       → list[str]              [only if config.enable_contextual_summaries]
       → falls back per-chunk to "" on LLM failure; logged at WARNING

5. _build_records(batch, enrichments, breadcrumbs, contextual_summaries, config, ...)
       → compound text order: breadcrumb → contextual_summary? → headline → summary → raw_text

6. embed_fn.embed(compound_texts) → embeddings

7. store.upsert(collection, ids, embeddings, compound_texts, metadatas)
```

**No new packages.** `breadcrumb.py` is a new module within the existing `packages/rag/rag/knowledge/` package. `IngestionConfig` lives in `interface.py` alongside the other shared types.
