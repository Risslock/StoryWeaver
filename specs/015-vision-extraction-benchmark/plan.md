# Implementation Plan: Vision Extraction Benchmark

**Branch**: `015-vision-extraction-benchmark` | **Date**: 2026-07-07 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/015-vision-extraction-benchmark/spec.md`

## Summary

Benchmark the already-built vision extraction path (`VisionPdfIngestor` + `OllamaVisionProvider`, spec 011) against the current Docling baseline on the ED4_Players_Guide corpus, using the existing retrieval harness (`run_gold_standard_benchmark` → MRR/nDCG/Recall@10) and the existing answer-quality harness (`eval_runner.py` → `judge_runner.py`). The extraction path is the **single independent variable**; every downstream stage stays at its current committed default. The decision is gated on the LLM-judge answer-quality score (primary) with retrieval as supporting evidence.

This is mostly an **orchestration + measurement** feature — the ingestion and evaluation machinery already exists. Three small code changes are required to make the comparison honest and attributable:

1. **Record `extraction_mode` on each benchmark run** (`test_gold_standard.py` + the eval/judge run metadata) so a run is attributable to vision vs docling (FR-011) — today the record captures chunking/enrich/embed/hybrid config but not the extraction path.
2. **Greedy decoding (temperature 0) for evaluation** (`OllamaProvider.generate`/`generate_structured`) threaded through generation (`ask_question`) and the judge — today no `temperature` is sent at all, so runs are non-deterministic (FR-018).
3. **Surface `extraction_mode` in the comparison output** (`compare_benchmark_runs`) so the diff table names which path is A and which is B.

Everything else is a **run procedure** (quickstart): clean-slate re-ingest per path, run both harnesses, produce the per-category diff + judge delta, and record the fidelity spot check.

## Technical Context

**Language/Version**: Python 3.11+

**Primary Dependencies**:
- *Existing, unchanged*: `packages/rag/` (`IngestionPipeline`, `ChromaKnowledgeRetriever`, `VisionPdfIngestor`, `DoclingIngestor`, `ChromaVectorStore`, `SQLiteLexicalStore`, `ChunkEnricher`, `evaluator.py`), `packages/rag/rag/evaluation/` (judge + store + factory, spec 013), `packages/core/` (`Settings`), `harness/knowledge_qa/` (`test_gold_standard.py`, `eval_runner.py`, `judge_runner.py`)
- *Existing, lightly modified*: `packages/llm/llm/providers/ollama.py` (add temperature to the OpenAI-compatible payload)
- *External services*: Ollama — vision model `blaifa/Nanonets-OCR-s` (must be pulled), embed `nomic-embed-text`, enrich `llama3.2`, answer LLM `llama3.1`, judge via `JUDGE_PROVIDER`/`JUDGE_MODEL`; PyMuPDF (`fitz`) for page render (already a dep); Docling (baseline path)

**Storage**: ChromaDB collection `knowledge_global` (both paths write here — sequential, clean-slate between runs), SQLite lexical FTS5 table, `data/eval.db` (SQLite, per-`run_id` answer + judge records), `harness/knowledge_qa/benchmark_results.jsonl` (append-only retrieval records). No new store; no ChromaDB schema migration.

**Testing**: `pytest` + `pytest-asyncio`. New unit coverage for the temperature-passthrough and the `extraction_mode` record field; existing harness auto-skips when Ollama is unreachable.

**Target Platform**: Local (Windows/Linux), Ollama for all model calls; no cloud dependency (judge MAY be `claude` if the developer opts in, but the default local judge keeps it local-first).

**Project Type**: Single-project monorepo (`packages/*` + `apps/web/` + `harness/`). No new top-level package.

**Performance Goals**: None as a gate. Vision ingestion is ~30–90 min/book (one-time, accepted); observed wall-clock is recorded as a decision input (FR-017).

**Constraints**:
- **One variable only** (FR-009): between the two runs, only `IngestionConfig.extraction_mode` differs (`"docling_text"` vs `"vision"` — NOT plain `"docling"`, which uses Docling's own `HybridChunker` instead of the shared `create_chunker()` that both `docling_text` and `vision` use; using plain `"docling"` would confound extraction *and* chunker); cleaner, chunker, enricher (`llama3.1`, the actual configured `KNOWLEDGE_ENRICH_MODEL`), breadcrumbs, embedding model, retrieval `top_k`, hybrid enablement + weights all held at current defaults.
- **Greedy decoding, single pass** (FR-018): temperature 0 on evaluation LLM steps; one ingestion + one eval pass per path; no repeated runs.
- **Fixed pre-stated tolerances**: judge non-inferiority 1.0 pp; retrieval material-regression 2 pp on global Recall@10 (fixed before interpreting the runs).
- **Decision rule** (FR-008): global LLM-judge aggregate is the primary gate; retrieval deltas are supporting evidence; a material judge regression forces keep-Docling regardless of retrieval gains.
- **No fallback** on vision failure (existing spec-011 contract): abort, no text fallback, no rollback; a partial collection MUST NOT be benchmarked (FR-003).

**Scale/Scope**: Single corpus (ED4_Players_Guide), the existing 118-question `rag_gold_standard.jsonl`. Two ingestions, two retrieval-benchmark records, two eval/judge `run_id`s, one comparison, one spot check, one written recommendation.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Spec-Driven Development | ✅ PASS | Spec at `specs/015-vision-extraction-benchmark/spec.md`; both clarifications resolved and integrated |
| II. Provider Abstraction | ✅ PASS | Vision stays behind `VisionLLMProvider`; judge behind the `JUDGE_PROVIDER` factory (spec 013); temperature is a payload parameter inside the existing `OllamaProvider`, no new branching or provider coupling |
| III. Package Isolation | ✅ PASS | Changes confined to `packages/llm/` (temperature), `packages/rag/` (record field), and `harness/knowledge_qa/` (record + comparison + spot-check); no new package |
| IV. Local-First, Cloud-Optional | ✅ PASS | All model calls run on local Ollama; the only optional cloud path is an opt-in `claude` judge that already exists |
| V. Harness-Driven Agent Quality | ✅ PASS | The feature *is* a harness comparison; acceptance criteria are expressed as harness/eval outputs; existing harnesses are extended, not replaced |
| VI. Product-First Development | ✅ PASS | Directly informs the default extraction path for the product's core Knowledge Q&A; no speculative infra |
| VII. Placeholder-First & Explicit Failures | ✅ PASS | Vision abort is explicit and non-silent (existing); benchmark refuses to run on a partial collection (FR-003); missing vision model aborts with a clear error (existing) |
| VIII. Structured Logging & Observability | ✅ PASS | New/changed code uses `logging.getLogger(__name__)`; wall-clock and decoding settings are logged and recorded on the run records |

**Gate Result**: ✅ ALL PASS — No violations require justification. (Re-checked after Phase 1: still PASS — the design adds only a config field, a payload parameter, and record metadata.)

## Project Structure

### Documentation (this feature)

```text
specs/015-vision-extraction-benchmark/
├── plan.md              # This file
├── research.md          # Phase 0 output — decisions (extraction_mode source, temperature threading, clean-slate, judge delta, spot check)
├── data-model.md        # Phase 1 output — benchmark record, eval/judge run, fidelity spot-check record
├── quickstart.md        # Phase 1 output — the end-to-end run procedure (the primary deliverable's recipe)
├── contracts/
│   ├── benchmark-record-schema.md   # extraction_mode + decoding fields added to benchmark_results.jsonl and eval run metadata
│   └── eval-determinism.md          # temperature-0 passthrough contract for generation + judge
└── tasks.md             # Phase 2 output (via /speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
packages/llm/llm/providers/ollama.py
    # MODIFIED: OllamaProvider.generate/generate_structured send "temperature" in the payload;
    #   default sourced from a new Settings field (greedy default for eval). VisionLLMProvider
    #   image path unchanged.

packages/core/core/config.py
    # MODIFIED: add knowledge_eval_temperature Settings field, default 0.0; mirrored in
    #   .env.example and .env per repo practice.

harness/knowledge_qa/test_gold_standard.py
    # MODIFIED: run_gold_standard_benchmark() records "extraction_mode" (+ "decoding") on the
    #   benchmark_results.jsonl record; compare_benchmark_runs() prints extraction_mode per run.

harness/knowledge_qa/eval_runner.py
    # MODIFIED: stamp extraction_mode + decoding onto the eval run so the judge delta is attributable.

harness/knowledge_qa/spot_check.py
    # NEW: pull N chapter-opening + M table-bearing sample chunks from the current collection for
    #   human fidelity inspection (US4); prints/records completeness + coherence classifications.

packages/llm/tests/ (or packages/rag/tests/)
    # NEW/EXTENDED: unit test that temperature is threaded into the Ollama payload (default 0 for eval).

harness/knowledge_qa/test_gold_standard.py (tests)
    # EXTENDED: assert the benchmark record carries extraction_mode; comparison prints it.

.env.example / .env
    # MODIFIED: document + default the new temperature setting.

README.md
    # MODIFIED (Principle I): note the extraction-path benchmark and how to reproduce it.
```

**Structure Decision**: Single-project monorepo, no new package. The feature is deliberately thin on new code: the ingestion (`extraction_mode="vision"`) and evaluation harnesses already exist, so the change surface is (a) one determinism knob in the shared `OllamaProvider`, (b) run-attribution metadata on the two existing record sinks, and (c) one small read-only spot-check helper. The bulk of the deliverable is the **run procedure and the recorded decision**, captured in `quickstart.md` and a results write-up, not new modules.

## Complexity Tracking

No constitution violations. No entries required.
