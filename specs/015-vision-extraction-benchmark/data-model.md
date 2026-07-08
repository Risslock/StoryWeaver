# Phase 1 Data Model: Vision Extraction Benchmark

This feature introduces **no new persistent entities and no schema migrations**. It extends the metadata carried on two existing record sinks and defines one transient record for the spot check. "Fields added" below are the only structural changes.

---

## E1 — Retrieval Benchmark Record (existing: `benchmark_results.jsonl`)

One append-only JSON line per retrieval-benchmark run, written by `run_gold_standard_benchmark()`.

**Existing fields** (unchanged): `timestamp`, `chunking.{strategy,params}`, `enrich_model`, `embed_model`, `gold_standard_path`, `k`, `total_questions`, `mean_mrr`, `mean_ndcg`, `mean_recall_at_k`, `category_scores{...}`, `exact_term_scores`, `hybrid_search_enabled`, `hybrid_search_keyword_weight`, `hybrid_search_vector_weight`, `notes`.

**Fields ADDED**:

| Field | Type | Meaning |
|-------|------|---------|
| `extraction_mode` | `str` (`"vision"` \| `"docling"` \| `"unknown"`) | Which ingestion path produced the collection this run queried (from `BENCHMARK_EXTRACTION_MODE`; R1). The single independent variable. |
| `decoding` | `str` (`"greedy"` \| `"sampled"`) | `"greedy"` when `knowledge_eval_temperature == 0.0`, else `"sampled"`. Records the FR-018 determinism setting. |

**Validation / rules**:
- `extraction_mode` is set from the env var at write time; `"unknown"` triggers a WARNING log (record still written).
- The comparison (`compare_benchmark_runs`) prints `extraction_mode` for Run A and Run B (previously only hybrid config was printed).
- Comparability check: two records are a valid vision-vs-docling comparison only if every held-fixed field (`chunking`, `enrich_model`, `embed_model`, `k`, hybrid fields, `gold_standard_path`) is identical and only `extraction_mode` differs (FR-009/FR-011).

---

## E2 — Answer Eval Run (existing: `data/eval.db`, keyed by `run_id`)

Per-question answer records written by `eval_runner.py` and scored in place by `judge_runner.py`. One `run_id` per extraction path.

**Existing per-record fields** (unchanged): `run_id`, `campaign_id`, `role`, `question`, `reference_answer`, `question_source`, `question_category`, `generated_response`, `context_chunks_json`, and the judge columns (`judge_status`, `judge_faithfulness`, `judge_relevance`, `judge_context_utilization`, `judge_answer_correctness`, `judge_aggregate`, rationales, `judge_provider`, `judge_model`).

**Attribution ADDED** (run-level, not per question — recorded alongside the run so the judge delta is attributable):

| Field | Type | Meaning |
|-------|------|---------|
| `extraction_mode` | `str` | The path the answered collection was ingested with (from `BENCHMARK_EXTRACTION_MODE`). |
| `decoding` | `str` | `"greedy"` / `"sampled"` — the generation + judge temperature setting for this run. |

**Rules**:
- Implementation may store these as columns on the eval record, or as a small run-metadata row/sidecar — the contract is only that the two `run_id`s are labelled with their extraction path and decoding so the delta is not ambiguous.
- The **judge aggregate mean** per run is the primary decision metric (FR-008). The **judge delta** = vision aggregate mean − docling aggregate mean, compared to the 1.0 pp tolerance.

---

## E3 — Fidelity Spot-Check Record (transient, US4)

Produced by `spot_check.py` + human classification; recorded in the results write-up (not a persistent store).

| Field | Type | Meaning |
|-------|------|---------|
| `extraction_mode` | `str` | Which collection the sample came from. |
| `sample_kind` | `str` (`"chapter_opening"` \| `"table"`) | What was sampled. |
| `chunk_id` | `str` | The sampled chunk. |
| `classification` | `str` (`"complete_opening"`/`"drop_cap_gap"` or `"coherent_table"`/`"mangled_table"`) | Human verdict. |
| `note` | `str` | Optional free-text comparison against the other path's same passage. |

**Rules**: ≥10 `chapter_opening` samples and ≥5 `table` samples per extraction path (SC-006). Counts of `complete_opening` and `coherent_table` per path feed the recommendation (FR-013/FR-014).

---

## E4 — Benchmark Recommendation (transient artifact)

The feature's terminal output — a written record (in the results doc / PR description), not a database entity.

| Field | Meaning |
|-------|---------|
| `verdict` | `vision_default` \| `docling_default` \| `inconclusive` |
| `judge_aggregate_delta` | vision − docling judge aggregate mean (primary gate) |
| `judge_tolerance_pp` | fixed non-inferiority tolerance = 1.0 pp |
| `recall_at_10_delta` | global Recall@10 delta (supporting) |
| `recall_regression_threshold_pp` | fixed material-regression threshold = 2 pp |
| `per_category_deltas` | from `compare_benchmark_runs` |
| `spot_check_summary` | complete-opening / coherent-table counts per path |
| `ingestion_wall_clock` | observed vision ingestion time (FR-017) |
| `limitations` | residual single-pass nondeterminism note (FR-018) |

**Decision rule applied** (FR-008): recommend `vision_default` iff `judge_aggregate_delta ≥ −1.0 pp` **and** `recall_at_10_delta ≥ −2 pp`; recommend `docling_default` if the judge score materially regresses regardless of retrieval; else `inconclusive`.
