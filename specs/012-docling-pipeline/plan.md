# Implementation Plan: Docling Ingestion Pipeline

**Branch**: `012-docling-pipeline` | **Date**: 2026-06-26 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/012-docling-pipeline/spec.md`

## Summary

Replace the pymupdf4llm extraction + legacy chunker paths with Docling's `DocumentConverter` + `HybridChunker`. Breadcrumbs derive from `chunk.meta.headings`, superseding `BreadcrumbExtractor`. Deprecate CorpusCleaner FR-003 (image placeholder stripping) and FR-004 (furniture stripping) — Docling eliminates these at extraction time. Add provider-selectable enrichment LLM and embedding function via two factory functions (`get_knowledge_enrich_provider()`, `get_knowledge_embed_fn()`) following the `get_image_provider()` pattern. Create `HuggingFaceEmbedFn` for HF Inference API feature-extraction.

---

## Technical Context

**Language/Version**: Python 3.11+

**Primary Dependencies**:
- *New*: `docling>=2.0.0` (DocumentConverter, HybridChunker, PdfPipelineOptions)
- *New*: `transformers` (AutoTokenizer for HybridChunker tokenizer parameter)
- *Retained*: `chromadb>=0.4`, `pymupdf4llm` (kept deprecated), `pydantic`, `httpx`

**Storage**: ChromaDB (vector store at `./data/chroma`), SQLite (document status via SQLAlchemy)

**Testing**: `pytest` for unit + integration tests; `/harness` for retrieval quality evals

**Target Platform**: Local (Windows/Linux), Ollama as default provider

**Project Type**: Library — `packages/rag/` ingestion pipeline within Python monorepo

**Performance Goals**: End-to-end ingestion ≤1/10 of pymupdf4llm wall-clock time for ED4_Players_Guide (SC-005; already validated in spike at ~30× faster)

**Constraints**:
- Docling downloads ~1–2 GB of layout ML models on first run (cached in `~/.cache/docling`); subsequent runs use cache
- HuggingFace free-tier rate limits apply; pipeline aborts on rate-limit error — no automatic retry in scope
- Post-chunk quality gate (150 chars min / 15,000 chars max) continues to apply to HybridChunker output
- `KNOWLEDGE_ENRICH_MODEL` and `KNOWLEDGE_EMBED_MODEL` MUST be required env vars with no code-level defaults

**Scale/Scope**: Single-document ingestion (~1,400 chunks for a 300-page rulebook PDF)

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Spec-Driven Development | ✅ PASS | Spec exists at `specs/012-docling-pipeline/spec.md`; spike PR #19 ratified Docling adoption before implementation |
| II. Provider Abstraction | ✅ PASS | This feature *implements* provider abstraction — `get_knowledge_enrich_provider()` and `get_knowledge_embed_fn()` factories; switching requires only env var change |
| III. Package Isolation | ✅ PASS | All changes within `packages/rag/`; `ChunkEnricher` and `ChromaVectorStore` are unchanged; no new top-level packages |
| IV. Local-First, Cloud-Optional | ✅ PASS | Default provider is Ollama (local); HuggingFace is opt-in via env vars; Docling runs locally with downloaded models |
| V. Harness-Driven Quality | ✅ PASS | SC-001–SC-012 are all expressible as automated assertions; SC-007 Recall@10 benchmarks against existing `benchmark_results.jsonl` |
| VI. Product-First Development | ✅ PASS | Extraction quality directly improves retrieval and answer quality; provider flexibility removes local-only constraint |
| VII. Placeholder-First & Explicit Failures | ✅ PASS | Pipeline aborts with ERROR-level logs on missing env vars (FR-020–FR-026); deprecated paths emit WARNING and continue functioning |
| VIII. Structured Logging | ✅ PASS | Deprecation markers use `logging.getLogger(__name__).warning()`; provider selection logged at INFO; errors at ERROR |

**Gate Result**: ✅ ALL PASS — No violations require justification.

---

## Project Structure

### Documentation (this feature)

```text
specs/012-docling-pipeline/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── ingestion-pipeline.md   # Phase 1 output
└── tasks.md             # Phase 2 output (via /speckit-tasks — NOT created here)
```

### Source Code

```text
packages/rag/
├── pyproject.toml                          # Add docling, transformers dependencies
└── rag/knowledge/
    ├── pipeline.py                         # Modified: Docling branch in _extract(); factory providers; no model defaults
    ├── ingestor.py                         # Modified: add DoclingIngestor; deprecate PdfIngestor
    ├── docling_chunker.py                  # NEW: DoclingChunker wrapping HybridChunker
    ├── cleaner.py                          # Modified: mark FR-003 + FR-004 rules DEPRECATED(012)
    ├── breadcrumb.py                       # Modified: deprecate BreadcrumbExtractor
    ├── chunker.py                          # Modified: deprecate HeadingChunker
    ├── chunker_semantic.py                 # Modified: deprecate SemanticChunker
    ├── chunker_agentic.py                  # Modified: deprecate AgenticChunker
    ├── embedder.py                         # Modified: add HuggingFaceEmbedFn; update get_embed_fn() → provider-aware
    ├── factory.py                          # NEW: get_knowledge_enrich_provider(), get_knowledge_embed_fn()
    └── retriever.py                        # Modified: replace OllamaProvider with get_knowledge_enrich_provider()

.env.example                                # Add KNOWLEDGE_ENRICH_PROVIDER, KNOWLEDGE_EMBED_PROVIDER,
                                            # and document KNOWLEDGE_ENRICH_MODEL, KNOWLEDGE_EMBED_MODEL as required
```

**Structure Decision**: Single-package changes within `packages/rag/`; factory module added in the existing `rag/knowledge/` namespace for locality.

---

## Complexity Tracking

> No Constitution Check violations found. No entries required.
