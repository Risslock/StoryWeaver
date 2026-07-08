---
description: "Task list for Vision Extraction Benchmark (feature 015)"
---

# Tasks: Vision Extraction Benchmark

**Input**: Design documents from `specs/015-vision-extraction-benchmark/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: The plan requests unit coverage for the two code changes (temperature passthrough, record attribution). Those test tasks are included; no broader TDD suite is requested for the operational run steps.

## ⚠️ Execution sequencing (read first — this feature is not story-parallel)

Both extraction paths write to the **same** `knowledge_global` collection, and each ingestion clean-slates the corpus doc. Therefore the two legs are **strictly sequential** and per-collection measurements must happen *inside* the leg that owns the collection:

```
Foundational code changes (Phase 2)  →  built once, block everything
   ↓
DOCLING LEG:  clean → ingest(docling) → retrieval bench → eval+judge → spot-check(docling)
   ↓
VISION LEG:   clean → ingest(vision)  → retrieval bench → eval+judge → spot-check(vision)
   ↓
COMPARE + DECIDE (needs both legs' records)
```

Story labels ([US1]–[US4]) are kept for traceability, but at runtime the legs interleave the stories. The Dependencies section spells out the true order.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- File paths are exact and repo-relative.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Confirm the environment and lock the held-fixed baseline before any run.

- [ ] T001 [P] Verify Ollama is reachable and all required models are pulled: vision `blaifa/Nanonets-OCR-s`, embed `nomic-embed-text`, enrich `llama3.2`, answer `llama3.1`, and `JUDGE_MODEL`; record versions in a new `specs/015-vision-extraction-benchmark/results.md` scratch doc.
- [ ] T002 Record the current held-fixed config snapshot (values of `knowledge_enrich_model`, `knowledge_embed_model`, retrieval `top_k`, `hybrid_search_enabled/_keyword_weight/_vector_weight`, `gold_standard_path`) into `results.md` so comparability (FR-011) can be verified later.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The code changes every attributable, deterministic run depends on. ⚠️ No benchmark leg may start until this phase is complete.

**Determinism — greedy decoding (FR-018, contracts/eval-determinism.md)**

- [ ] T003 Add `knowledge_eval_temperature: float = 0.0` to `Settings` in packages/core/core/config.py with startup range validation (0.0–2.0, fail-fast on out-of-range, mirroring the 014 hybrid-weight validator).
- [ ] T004 [P] Mirror `KNOWLEDGE_EVAL_TEMPERATURE=0.0` in `.env.example` (documented, per-feature section) and in local `.env`.
- [ ] T005 Thread `temperature` into `OllamaProvider.generate()` payload in packages/llm/llm/providers/ollama.py, resolved from `knowledge_eval_temperature` with an optional per-call override.
- [ ] T006 Thread `temperature` into `OllamaProvider.generate_structured()` payload in packages/llm/llm/providers/ollama.py (keep `response_format`), same resolution as T005.
- [ ] T007 Ensure the `claude` judge path passes `temperature=0` through the Anthropic provider call in packages/llm/llm/providers/anthropic.py (so the opt-in cloud judge is equally deterministic).
- [ ] T008 [P] Unit test: `temperature` is present in the Ollama `generate`/`generate_structured` payloads and defaults to 0.0 for eval, in packages/llm/tests/test_ollama_temperature.py.

**Run attribution (FR-011, contracts/benchmark-record-schema.md)**

- [ ] T009 Add `extraction_mode` (from `BENCHMARK_EXTRACTION_MODE`, default `"unknown"` + WARNING) and `decoding` (`"greedy"` when temp 0 else `"sampled"`) to the record written by `run_gold_standard_benchmark()` in harness/knowledge_qa/test_gold_standard.py.
- [ ] T010 Print `extraction_mode` + `decoding` per run in `compare_benchmark_runs()` header in harness/knowledge_qa/test_gold_standard.py.
- [ ] T011 Add a comparability check in harness/knowledge_qa/test_gold_standard.py that confirms two records differ ONLY in `extraction_mode` (all held-fixed fields equal) and surfaces a mismatch instead of silently comparing.
- [ ] T012 Stamp `extraction_mode` + `decoding` onto the eval run (record column or run-metadata sidecar) in harness/knowledge_qa/eval_runner.py so the judge aggregate is attributable per `run_id`.
- [ ] T013 [P] Unit test: the benchmark record carries `extraction_mode`/`decoding` and `compare_benchmark_runs` prints them; missing-field records degrade gracefully — in harness/knowledge_qa/test_gold_standard.py.

**Spot-check tool (built here so it's ready for each leg; US4)**

- [ ] T014 [P] [US4] Create harness/knowledge_qa/spot_check.py: a read-only CLI (`--extraction-mode`) that samples ≥10 chapter-opening chunks and ≥5 table-bearing chunks (`|…|` rows) from the current collection and prints each for human classification (complete-opening/drop-cap-gap; coherent-table/mangled-table).

**Checkpoint**: Foundation ready — the benchmark legs can now run.

---

## Phase 3: Docling Baseline Leg (Priority: P1) — serves [US2] baseline + [US3]

**Goal**: A fresh Docling baseline under current settings (FR-012 / US3 AC2), fully measured, before the collection is handed to the vision leg.

**Independent Test**: `benchmark_results.jsonl` has a Docling record with current held-fixed config; `eval.db` has a scored Docling `run_id`; spot-check counts recorded for Docling.

- [ ] T015 [US2] Clean-slate the corpus doc from both stores (`ChromaVectorStore.delete_by_doc` + lexical `delete_by_doc`), then ingest ED4_Players_Guide with `IngestionConfig(extraction_mode="docling")`; confirm completion and `extraction_mode="docling"` tagging.
- [ ] T016 [US2] Run the retrieval benchmark with `BENCHMARK_EXTRACTION_MODE=docling` (`pytest harness/knowledge_qa/test_gold_standard.py -k recall_sanity -s`) → appends the Docling retrieval record.
- [ ] T017 [US2] Run `eval_runner.py … --run-id docling-015` then `judge_runner.py --run-id docling-015 --summary` (greedy) → record the Docling judge aggregate mean in `results.md`.
- [ ] T018 [US4] Run `python harness/knowledge_qa/spot_check.py --extraction-mode docling` and record complete-opening / coherent-table counts in `results.md` (must be done now — the Docling collection is replaced in Phase 4).

**Checkpoint**: Docling baseline fully captured; safe to overwrite the collection.

---

## Phase 4: Vision Leg (Priority: P1) — serves [US1] + [US2] measurement

**Goal**: Prove the vision path still runs end-to-end (US1) and capture its metrics (US2), on the same held-fixed downstream config.

**Independent Test**: Vision ingestion completes with zero aborted pages, all chunks tagged `vision`, smoke query non-empty; a Vision retrieval record + scored Vision `run_id` exist; Vision spot-check recorded.

- [ ] T019 [US1] Clean-slate the corpus doc again, then ingest ED4_Players_Guide with `IngestionConfig(extraction_mode="vision")` (uses `blaifa/Nanonets-OCR-s`); **record wall-clock time** (FR-017) in `results.md`. Must finish with zero aborted pages — a partial collection is NOT benchmarkable (FR-003); on abort, fix the model and re-run.
- [ ] T020 [US1] Verify every chunk is tagged `extraction_mode="vision"` and a smoke retrieval query returns a non-empty ranked set (SC-001, US1 AC2/AC3).
- [ ] T021 [US2] Run the retrieval benchmark with `BENCHMARK_EXTRACTION_MODE=vision` → appends the Vision retrieval record.
- [ ] T022 [US2] Run `eval_runner.py … --run-id vision-015` then `judge_runner.py --run-id vision-015 --summary` (greedy) → record the Vision judge aggregate mean in `results.md`.
- [ ] T023 [US4] Run `python harness/knowledge_qa/spot_check.py --extraction-mode vision` and record complete-opening / coherent-table counts in `results.md`.

**Checkpoint**: Both legs measured; all inputs for the comparison exist.

---

## Phase 5: Comparison, Controlled-Conditions Proof & Decision (Priority: P1/P2) — [US2] + [US3]

**Goal**: Produce the per-category diff + judge delta, prove one-variable conditions, and record the recommendation.

**Independent Test**: A single diff table + judge delta exist; records confirmed to differ only in `extraction_mode`; a written verdict applying the FR-008 rule is recorded.

- [ ] T024 [US3] Run the comparability check (T011) on the two fresh records; confirm they differ ONLY in `extraction_mode` (SC-005). If any held-fixed field differs, redo the offending leg.
- [ ] T025 [US2] Produce the per-category diff: `compare_benchmark_runs(-2, -1)` (A=docling, B=vision) → capture ΔMRR/ΔnDCG/ΔRecall per category + global into `results.md` (SC-004).
- [ ] T026 [US2] Compute the judge aggregate delta (vision − docling) and per-dimension deltas from the two `--summary` outputs; note against the fixed 1.0 pp non-inferiority tolerance (SC-003/SC-004).
- [ ] T027 [US4] Note in `results.md` any divergence between the spot-check verdict and the aggregate-metric verdict (FR-014).
- [ ] T028 [US2] Write the evidence-backed recommendation (`vision_default` / `docling_default` / `inconclusive`) applying the FR-008 decision rule — judge aggregate primary gate (≥ −1.0 pp), global Recall@10 supporting (≥ −2 pp), judge regression forces keep-Docling — citing all deltas, spot-check counts, vision wall-clock, and the single-pass-nondeterminism limitation (SC-007).

**Checkpoint**: The decision the whole feature exists to make is recorded.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [ ] T029 [P] Update README.md (Principle I) to note the extraction-path benchmark result and how to reproduce it (link quickstart.md).
- [ ] T030 [P] Finalize `specs/015-vision-extraction-benchmark/results.md` as the durable record of the run (metrics, deltas, verdict, limitations).
- [ ] T031 Run the quickstart.md success checklist end-to-end (SC-001…007 all ticked).
- [ ] T032 Commit, push, and open the PR for `015-vision-extraction-benchmark`.

---

## Dependencies & Execution Order

### Hard ordering (imposed by the single shared collection)

1. **Phase 1 Setup** → **Phase 2 Foundational** (all code changes) block everything.
2. **Phase 3 Docling leg** must fully complete — including its spot-check (T018) — before Phase 4, because Phase 4's ingest overwrites the collection.
3. **Phase 4 Vision leg** runs next; its spot-check (T023) must run before any later re-ingest.
4. **Phase 5 Compare/Decide** needs both legs' records.
5. **Phase 6 Polish** last.

### Within Foundational (Phase 2)

- T003 → (T005, T006, T007) [temperature field before providers use it]; T004 [P] after T003.
- T009 → T010, T011; T012 independent of T009 but same env-var source.
- [P] parallel-safe: T008, T013, T014 (different files), and T004.

### Story mapping (traceability)

- **US1** (vision runs): T019, T020.
- **US2** (comparison & decision): T015–T017, T021–T022, T024*, T025, T026, T028.
- **US3** (controlled one-variable): T011 (foundational), T024, plus the T002 config snapshot.
- **US4** (fidelity spot check): T014, T018, T023, T027.

### Parallel Opportunities

- Foundational: T008, T013, T014 can be built in parallel with the T004 env edit while T003/T005/T006 proceed.
- The two legs themselves are **not** parallelizable (shared collection). This is the dominant constraint — do not attempt to run docling and vision ingestion concurrently.

---

## Implementation Strategy

### MVP (answers the core question fastest)

Foundational (Phase 2) → Docling leg (Phase 3) → Vision leg (Phase 4) → Compare/Decide (Phase 5). That sequence alone produces the recommendation. US4 spot-check (T018/T023) is cheap and runs inside each leg — keep it, since a collection can't be re-sampled once overwritten.

### Notes

- The vision leg (T019) is the long pole (~30–90 min). Everything else is minutes.
- Do all per-collection reads (retrieval bench, eval, spot-check) for a leg before starting the next leg's ingest.
- Commit code changes (Phase 2) before the long ingestion runs so a failed run never loses the tooling.
- `results.md` is the running lab notebook; it becomes the durable artifact (T030).
