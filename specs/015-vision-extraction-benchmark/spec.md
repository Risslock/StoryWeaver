# Feature Specification: Vision Extraction Benchmark

**Feature Branch**: `015-vision-extraction-benchmark`

**Created**: 2026-07-07

**Status**: Draft

**Input**: User description: "Vision extraction benchmark. The VisionPdfIngestor and OllamaVisionProvider were built in spec 011 but never benchmarked. Run the vision extraction path end-to-end against the current Docling baseline on the ED4_Players_Guide corpus, using the existing gold-standard retrieval harness (MRR/nDCG/Recall@10) and the LLM-judge answer-quality harness, and produce a per-category comparison so we can decide whether to make vision the default extraction path. One-variable-at-a-time: only the extraction path changes; everything downstream stays fixed. Prompt/hyperparameter tuning and any LLM corpus-rewrite pass are out of scope (deferred to backlog)."

## Clarifications

### Session 2026-07-07

- Q: What decides "make vision the default extraction path"? → A: Answer-quality (LLM-judge) global score is the primary gate — vision becomes default only if its global judge score improves or is non-inferior within a small stated tolerance AND retrieval does not materially regress; retrieval deltas are supporting evidence, not the verdict.
- Q: How do we control run-to-run variance and set the tolerance? → A: Greedy decoding (temperature 0) for the LLM steps in evaluation to minimize variance, with a single ingestion per path and a single evaluation pass. The FR-008 tolerance is a fixed pre-stated value (not empirically measured across repeated passes). Residual local-model nondeterminism is accepted and noted as a limitation.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Verify the Vision Path Still Runs (Priority: P1)

A developer runs a full vision-mode ingestion of the ED4_Players_Guide corpus end-to-end and confirms the vision extraction path — untouched since spec 011 — still works after Docling became the active PDF path (spec 012) and hybrid search landed (spec 014). The run completes without error, produces a populated collection, and every stored chunk is tagged `extraction_mode="vision"`.

**Why this priority**: The vision path has never been exercised since two major pipeline changes landed downstream of it. Nothing else in this feature is meaningful until we know the path produces a valid, queryable collection. This is the smallest slice that delivers value: a yes/no answer to "does vision ingestion still work end-to-end?" plus a corpus to benchmark.

**Independent Test**: Ingest ED4_Players_Guide with the vision extraction mode enabled and the default vision model. Confirm: (a) the run exits successfully with no aborted pages; (b) the resulting collection contains a non-trivial chunk count (same order of magnitude as the Docling baseline); (c) every chunk's metadata carries `extraction_mode="vision"`; (d) a smoke query returns results.

**Acceptance Scenarios**:

1. **Given** the vision extraction mode and default vision model are configured, **When** ED4_Players_Guide is ingested, **Then** the run completes without an ingestion-abort error and writes a populated collection.
2. **Given** vision ingestion has completed, **When** the collection is inspected, **Then** every chunk carries `extraction_mode="vision"` in its metadata, distinguishing it from the Docling baseline collection.
3. **Given** vision ingestion has completed, **When** a smoke retrieval query is issued against the collection, **Then** it returns a non-empty ranked result set.

---

### User Story 2 — Vision-vs-Docling Per-Category Comparison (Priority: P1)

A developer runs the existing gold-standard retrieval benchmark (MRR / nDCG / Recall@10) and the LLM-judge answer-quality harness against both the vision-mode collection and the current Docling baseline, then produces a single side-by-side per-category diff. They can see at a glance, per question category, whether vision extraction wins, loses, or ties on retrieval and on answer quality — enough evidence to decide whether vision should become the default extraction path.

**Why this priority**: The whole point of the feature is a defensible default-path decision backed by the same eval harness used for every prior retrieval change. Without the comparison, US1 only proves the path runs — not whether it's better. Co-P1 with US1 because the decision is the deliverable.

**Independent Test**: With both a vision-mode benchmark record and a Docling-baseline benchmark record available, run the comparison to produce a per-category diff table (ΔMRR, ΔnDCG, ΔRecall@10 per category plus a global row) and the LLM-judge score delta. Verify the table renders one row per category plus a global row, with signed deltas.

**Acceptance Scenarios**:

1. **Given** a Docling-baseline benchmark record and a vision-mode benchmark record both exist, **When** the comparison is produced, **Then** it shows per-category ΔMRR, ΔnDCG, and ΔRecall@10 plus a global row, with signed deltas.
2. **Given** both runs have been judged by the LLM-judge answer-quality harness, **When** the comparison is produced, **Then** it reports the vision-vs-Docling judge-score delta (overall and, where available, per category).
3. **Given** the comparison is complete, **When** the developer reviews it, **Then** a written recommendation (make vision default / keep Docling default / inconclusive) is recorded with the supporting deltas.
4. **Given** the two benchmark runs differ **only** in extraction path, **When** the comparison is interpreted, **Then** any metric change is attributable to the extraction path alone (see US3 controlled-conditions guarantee).

---

### User Story 3 — Controlled, One-Variable Comparison (Priority: P2)

A developer guarantees the comparison is fair: between the Docling baseline run and the vision run, the **only** thing that changes is the PDF extraction path. The cleaner, chunker, enricher, breadcrumb extraction, embedding model, retrieval settings, and hybrid-search weights are all held at their current committed defaults for both runs, and the gold-standard question set is identical. The benchmark records capture enough configuration metadata to prove the runs were comparable.

**Why this priority**: A benchmark that changes two variables at once is worthless for a default-path decision. This story is what makes US2's numbers trustworthy. It is P2 because it constrains *how* US1/US2 are executed rather than adding a separate deliverable, but it is a hard gate on the decision's validity.

**Independent Test**: Inspect both benchmark records' captured configuration. Confirm every downstream setting (cleaner, chunker, enricher model, embedding model, retrieval top_k, hybrid weights, gold-standard set version) is identical across the two records and only the extraction-path field differs.

**Acceptance Scenarios**:

1. **Given** a Docling baseline run and a vision run, **When** their captured configurations are compared, **Then** all downstream settings are identical and only the extraction-path field differs.
2. **Given** a stale Docling baseline record whose downstream configuration no longer matches current defaults, **When** the comparison is prepared, **Then** the developer re-runs a fresh Docling baseline under current settings rather than comparing against the stale record.
3. **Given** the gold-standard question set, **When** both runs are evaluated, **Then** they use the identical question set and version.

---

### User Story 4 — Extraction-Fidelity Spot Check (Priority: P3)

A developer spot-checks a sample of vision-extracted content for the qualitative failure modes that motivated vision extraction in the first place: chapter-opening sentences are complete (no dropped drop-cap first letter) and table structure is coherent (rows/columns preserved, not collapsed into prose). This gives a human-eyeball signal that complements the aggregate metrics — vision can win on fidelity even where a coarse metric is flat.

**Why this priority**: Aggregate retrieval metrics can miss localized fidelity wins/losses (a single mangled stat table, a lost chapter-opening word). The spot check is cheap human verification of the specific defects vision is supposed to fix. P3 because it informs the recommendation but is not the primary decision input.

**Independent Test**: Sample at least 10 chapter-opening chunks and at least 5 table-bearing chunks from the vision collection. Record, per sample, whether the opening sentence is complete and whether the table structure is coherent, and compare the same passages against the Docling extraction.

**Acceptance Scenarios**:

1. **Given** the vision collection, **When** at least 10 chapter-opening chunks are inspected, **Then** each is recorded as complete-opening or drop-cap-gap, and the count of complete openings is reported.
2. **Given** the vision collection, **When** at least 5 table-bearing passages are inspected, **Then** each is recorded as coherent-table or mangled-table, and compared against the same passage in the Docling extraction.
3. **Given** the spot-check results, **When** they diverge from the aggregate metric verdict (e.g., fidelity clearly better but metrics flat), **Then** the divergence is noted in the recommendation.

---

### Edge Cases

- **Vision ingestion aborts mid-document** (a page exhausts retries): per the spec-011 contract there is no fallback to text and no rollback. The benchmark cannot proceed on a partial collection — the developer resolves the vision-model failure and re-ingests before benchmarking. A partial collection MUST NOT be silently benchmarked as if complete.
- **Vision ingestion is prohibitively slow** on the available hardware (well beyond the ~30–90 min/book expectation): the run is still allowed to complete (one-time cost is accepted), but the observed wall-clock time is recorded as an operational data point feeding the default-path decision.
- **The existing Docling baseline record predates current downstream defaults**: it is not a valid comparison anchor; a fresh Docling baseline is run under current settings (US3 AC2).
- **Vision and Docling produce very different chunk counts**: this is itself a finding (extraction granularity differs) and is reported, not hidden — it does not invalidate the per-category metric comparison, which is normalized per question.
- **A gold-standard question has no supporting passage in one collection but does in the other**: handled by the existing per-category metric aggregation; such asymmetries surface as category-level deltas.
- **The vision model is not pulled locally / not configured**: ingestion aborts with a clear error before any pages render (existing spec-011 behavior) — this feature does not add a fallback.

## Requirements *(mandatory)*

### Functional Requirements

**Vision Ingestion Run (US1)**

- **FR-001**: The system MUST support a full end-to-end ingestion of the ED4_Players_Guide corpus through the vision extraction path using the currently configured default vision model, producing a queryable collection distinct from the Docling baseline collection.
- **FR-002**: Every chunk produced by the vision run MUST be tagged with an extraction-path identifier (`extraction_mode="vision"`) in its stored metadata, so downstream benchmark records can attribute results to the vision path.
- **FR-003**: A vision ingestion run that aborts before completion MUST NOT be treated as a benchmarkable corpus; the feature MUST require a complete run before any comparison is produced.

**Benchmark Execution & Comparison (US2)**

- **FR-004**: The system MUST evaluate the vision-mode collection with the existing gold-standard retrieval harness, producing per-category MRR, nDCG, and Recall@10.
- **FR-005**: The system MUST evaluate the vision-mode collection with the existing LLM-judge answer-quality harness, producing an answer-quality score comparable to the Docling baseline.
- **FR-006**: The system MUST produce a single side-by-side comparison of the vision run against a Docling baseline run, reporting per-category ΔMRR, ΔnDCG, ΔRecall@10 plus a global row, using the existing benchmark comparison capability.
- **FR-007**: The comparison MUST report the LLM-judge answer-quality delta (overall, and per category where the harness provides it).
- **FR-008**: The feature MUST conclude with a written, evidence-backed recommendation — make vision the default extraction path, keep Docling, or inconclusive — driven by an explicit decision rule: the global LLM-judge answer-quality score is the **primary gate**. Vision is recommended as the default only if its global judge score improves over the Docling baseline, or is non-inferior within a small stated tolerance, **and** global retrieval (Recall@10 / MRR / nDCG) does not materially regress. Per-category retrieval deltas are supporting evidence, not the verdict. If the judge score materially regresses (as happened in feature 014), the recommendation MUST be keep-Docling regardless of retrieval gains. The tolerance and "material regression" thresholds MUST be stated numerically in the recommendation. Because variance is controlled by greedy decoding + single-pass evaluation (FR-018) rather than measured across repeated runs, these thresholds are fixed pre-stated values: default non-inferiority tolerance of 1.0 pp on the global judge score and a material-regression threshold of 2 pp on global Recall@10 (either may be adjusted at review time, but MUST be fixed before the runs are interpreted).

**Controlled Conditions (US3)**

- **FR-009**: The vision run and the Docling baseline run MUST differ only in the PDF extraction path; all downstream stages (cleaner, chunker, enricher and its model, breadcrumb extraction, embedding model, retrieval settings, hybrid-search enablement and weights) MUST be held at their current committed defaults for both runs.
- **FR-010**: Both runs MUST be evaluated against the identical gold-standard question set and version.
- **FR-011**: Each benchmark record MUST capture enough configuration metadata (extraction path plus the held-fixed downstream settings and gold-standard version) to verify after the fact that the two runs were comparable.
- **FR-012**: If the available Docling baseline record was produced under downstream settings that no longer match current defaults, a fresh Docling baseline MUST be run under current settings before comparison.
- **FR-018**: To control run-to-run variance, the evaluation MUST use greedy decoding (temperature 0) for the LLM steps it exercises (at minimum the LLM judge, and any enrichment/generation invoked during evaluation), with a single ingestion per extraction path and a single evaluation pass. Repeated ingestions or repeated evaluation passes are NOT required. The benchmark records MUST note the decoding setting used, and the recommendation MUST acknowledge residual local-model nondeterminism as a limitation on the confidence of small deltas.

**Fidelity Spot Check (US4)**

- **FR-013**: The feature MUST record a fidelity spot check over at least 10 chapter-opening passages (complete-opening vs drop-cap-gap) and at least 5 table-bearing passages (coherent vs mangled), comparing vision extraction against Docling extraction for the same passages.
- **FR-014**: Spot-check findings that diverge from the aggregate-metric verdict MUST be surfaced in the final recommendation.

**Scope Guardrails**

- **FR-015**: This feature MUST NOT modify any prompt (enricher, query-expansion, rerank, contextual-summary) or tune any hyperparameter (chunk sizes, retrieval top_k, hybrid weights); such changes are deferred to a separate tuning spec. The only permitted configuration change is selecting the extraction path.
- **FR-016**: This feature MUST NOT introduce any LLM corpus-rewrite/reformatting pass; that idea is a deferred contingency in the backlog.
- **FR-017**: The feature MUST record the observed vision-ingestion wall-clock time as an operational input to the default-path decision (the one-time slow-ingestion cost is accepted, not a blocker).

### Key Entities *(include if feature involves data)*

- **Extraction Path**: The strategy used to convert a PDF into Markdown for a run — `vision` or `docling`. The single independent variable in this benchmark; recorded on every chunk and every benchmark record.
- **Benchmark Record**: A stored result of one evaluation run over one collection, holding per-category retrieval metrics, answer-quality score, and the configuration metadata needed to confirm comparability. Two records (vision, docling) are the inputs to the comparison.
- **Per-Category Comparison**: The side-by-side diff of two benchmark records, one row per question category plus a global row, showing signed deltas for each metric — the primary decision artifact.
- **Fidelity Spot Check**: A recorded human inspection of sampled chapter-opening and table-bearing passages under each extraction path, classifying opening completeness and table coherence — the qualitative decision input.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A complete vision-mode ingestion of ED4_Players_Guide finishes with zero aborted pages and produces a collection whose every chunk is tagged with the vision extraction path.
- **SC-002**: Retrieval metrics (per-category MRR, nDCG, Recall@10) are produced for the vision collection using the same gold-standard set used for the Docling baseline.
- **SC-003**: LLM-judge answer-quality scores are produced for the vision collection, comparable to the Docling baseline.
- **SC-004**: A single per-category comparison table exists showing signed ΔMRR, ΔnDCG, ΔRecall@10 (one row per category plus a global row) and the answer-quality delta, between the vision run and a current-settings Docling baseline.
- **SC-005**: Configuration metadata on both benchmark records confirms the two runs differ only in extraction path (all downstream settings and the gold-standard version identical).
- **SC-006**: A fidelity spot check covering at least 10 chapter-opening passages and at least 5 table-bearing passages is recorded, with completeness/coherence counts for both extraction paths.
- **SC-007**: A written recommendation (vision default / Docling default / inconclusive) is recorded, applying the FR-008 decision rule — LLM-judge answer-quality score as the primary gate with retrieval as supporting evidence — and citing the observed retrieval deltas, answer-quality delta (against the stated tolerance), spot-check findings, and ingestion wall-clock time.

## Assumptions

- The vision extraction path (`VisionPdfIngestor`) and its Ollama vision provider from spec 011 are present in the codebase and are intended to be exercised as-is; this feature does not rebuild them, only runs and evaluates them.
- The default vision model (`blaifa/Nanonets-OCR-s`) is pulled and available in the local Ollama instance before the run; if it is not configured, ingestion aborts with a clear error (existing spec-011 behavior) and this feature adds no fallback.
- The gold-standard retrieval harness, the LLM-judge answer-quality harness, and the benchmark per-category comparison tool (spec 011 FR-016) all exist and are usable without modification beyond pointing them at the vision collection.
- The current Docling extraction path is the baseline "default" to beat; a fresh Docling baseline under current downstream settings is run if the most recent stored baseline predates those settings.
- Vision ingestion is significantly slower than Docling (~30–90 min per book) and this one-time cost is acceptable; long wall-clock time is recorded, not treated as a failure.
- ED4_Players_Guide is the single corpus for this benchmark; generalization to other books is out of scope for this feature.
- All downstream pipeline defaults (cleaner rules, chunker, enricher model `llama3.2`, embedding model `nomic-embed-text`, retrieval settings, hybrid-search weights) are held at their current committed values for both runs.
- Evaluation is run once per extraction path with greedy decoding (temperature 0) on the LLM steps to minimize variance; the FR-008 decision tolerances (1.0 pp judge non-inferiority, 2 pp Recall@10 regression) are fixed pre-stated values, not derived from repeated runs. Residual local-model nondeterminism is accepted as a known limitation on small deltas.
- Prompt engineering (few-shot) and hyperparameter tuning are explicitly deferred to backlog spec 016; the LLM corpus-rewrite pass is a deferred contingency — neither is in scope here.
