# Implementation Plan: Corpus Pre-Processing & Cleaning

**Branch**: `008-corpus-cleaning` | **Date**: 2026-06-25 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/008-corpus-cleaning/spec.md`

## Summary

Add a `CorpusCleaner` module to `packages/rag/rag/knowledge/` that sits between PDF extraction
and chunking. The cleaner applies rule profiles per source type (`rulebook`, `supplement`,
`novel`, `handwritten`): fitz coordinate-based multi-column reconstruction and stat block
normalisation (rulebook/supplement), de-hyphenation (all), TOC and front matter stripping
(rulebook/supplement/novel). PDF extraction is upgraded from single-string mode to
`pymupdf4llm page_chunks=True` for accurate per-page metadata. A source-type dropdown is added
to the Gradio upload form. The entire cleaning pipeline is bypassable via
`KNOWLEDGE_CLEANING_ENABLED=false`. Quality is confirmed by re-running the 118-question gold
standard harness and comparing against the spec 007 agentic-chunker baseline
(MRR=0.5767, nDCG=0.6413, Recall@10=0.8966).

## Technical Context

**Language/Version**: Python 3.11+

**Primary Dependencies**:
- `pymupdf4llm` (existing) — switching to `page_chunks=True` mode; no version bump required
- `PyMuPDF` / `fitz` (already a transitive dep of `pymupdf4llm`) — used directly for
  block bounding-box extraction in multi-column detection
- `re` (stdlib) — de-hyphenation and pattern matching; no new library deps
- `chromadb>=0.4`, `pydantic-ai`, `storyweaver-core`, `storyweaver-llm`,
  `storyweaver-storage` — all existing, unchanged

**Storage**:
- SQLite: new `source_type` column on `knowledge_documents` (migration `0007_…`)
- ChromaDB: re-ingestion required after deployment; schema unchanged

**Testing**:
- `pytest` for unit tests (`packages/rag/tests/knowledge/test_cleaner.py`) — plain
  Markdown in/out, no Ollama required (FR-012)
- `/harness/knowledge_qa/test_gold_standard.py` for integration eval (requires Ollama)
- `ruff` + `pyright` on all changed files

**Target Platform**: Local development server (same as all other packages)

**Project Type**: Monorepo Python package extension (`packages/rag/`, `apps/web/`,
`packages/core/`)

**Performance Goals**: Ingestion latency increase is acceptable — ingestion runs in the
background (existing behaviour). No speed gate. Cleaning MUST NOT raise exceptions on
unrecognised content.

**Constraints**:
- No new top-level packages beyond `packages/rag/` (existing)
- No new cloud dependencies; `fitz` is already a transitive dep
- `KNOWLEDGE_CLEANING_ENABLED=false` must bypass all cleaning with no code changes (FR-009)
- All existing unit tests must continue to pass after the interface change to `ingest_async`

**Scale/Scope**: Single-document ingestion; 118-question gold standard; four source types

## Constitution Check

| Principle | Check | Status |
|-----------|-------|--------|
| I. Spec-Driven | Full spec + plan written before any code | ✅ PASS |
| II. Provider Abstraction | Source type and rule profiles configurable via constructor param + env var; no new provider coupling; `KNOWLEDGE_CLEANING_ENABLED` env var bypasses all cleaning | ✅ PASS |
| III. Package Isolation | All new code in `packages/rag/rag/knowledge/cleaner.py`; no new package; no circular deps; cleaner independently testable with plain strings (FR-012) | ✅ PASS |
| IV. Local-First | No new cloud or OS-level deps; `fitz` is already a transitive dep of `pymupdf4llm`; cleaning runs entirely locally | ✅ PASS |
| V. Harness-Driven | Gold standard re-run after re-ingestion; new cleaner unit tests; acceptance criteria expressed as assertions | ✅ PASS |
| VI. Product-First | Feature directly improves retrieval quality for GMs and players | ✅ PASS |
| VII. Placeholder-First | Source-type dropdown visible in UI immediately (placeholder first, then wired); no silent failures — unrecognised content passes through with DEBUG log (FR-011) | ✅ PASS |
| VIII. Structured Logging | All transformations logged at WARNING (FR-010); passthrough content at DEBUG (FR-011); `logging.getLogger(__name__)` in `cleaner.py`; no bare `print()` | ✅ PASS |

## Project Structure

### Documentation (this feature)

```text
specs/008-corpus-cleaning/
├── plan.md              # This file
├── research.md          # Phase 0: extraction strategy, algorithm decisions, baseline scores
├── data-model.md        # Phase 1: CorpusCleaner types, DB change, pipeline interface changes
├── contracts/
│   └── cleaner-api.md   # Phase 1: CorpusCleaner public API, rule profiles, logging contract
├── quickstart.md        # Phase 1: validation scenarios (unit tests → UI → retrieval → harness)
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created by /speckit-plan)
```

### Source Code Changes

```text
packages/rag/rag/knowledge/
├── cleaner.py           # NEW — CorpusCleaner, PageText, CleanedDocument, CleaningReport,
│                        #        CleaningRuleProfile, _PROFILES mapping
├── ingestor.py          # UPDATED — page_chunks=True; call CorpusCleaner; source_type param;
│                        #            fitz multi-column block extraction
├── pipeline.py          # UPDATED — source_type param propagated to _extract_chunks
└── [all others]         # UNCHANGED

packages/rag/tests/knowledge/
├── test_cleaner.py      # NEW — unit tests per rule; source type gating; bypass; edge cases
└── [existing tests]     # UNCHANGED

packages/core/core/
└── models.py            # UPDATED — KnowledgeDocument.source_type field (String(20))

packages/core/core/migrations/versions/
└── 0007_add_source_type_to_knowledge_documents.py  # NEW Alembic migration

apps/web/
├── services/knowledge.py     # UPDATED — source_type param in submit_document,
│                             #            confirm_overwrite, _run_pipeline
├── pages/gm/knowledge_qa.py  # UPDATED — source_type dropdown; "Source" column in doc table
└── pages/player/knowledge_qa.py  # CHECK — upload form here too if present; same dropdown

harness/knowledge_qa/
├── benchmark_results.jsonl   # UPDATED — new row after re-ingestion with cleaning
└── test_gold_standard.py     # UNCHANGED — re-run as-is; scores compared to baseline
```

**Structure Decision**: Single package extension — all new logic in `packages/rag/rag/knowledge/`.
The cleaner is a new module within the existing package boundary. No new package is introduced
because the cleaning domain is specific to knowledge ingestion and has no cross-package consumers.

## Complexity Tracking

No constitution violations. No new packages. `fitz` is a transitive dep (not a new dependency).
The only notable complexity is the interface change from `str` to `list[PageText]` in
`PdfIngestor._convert_to_markdown()` — justified by the significant accuracy gain for front
matter detection and multi-column layout reconstruction (Decision 1 in research.md).