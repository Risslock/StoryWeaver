# Contract: Benchmark Record Attribution

**Files**: `harness/knowledge_qa/test_gold_standard.py`, `harness/knowledge_qa/eval_runner.py`
**Status**: Extension of existing records (feature 015)

---

## Purpose

Make every benchmark run attributable to the extraction path that produced its collection, and record the decoding setting, so a vision-vs-docling comparison is provably one-variable (FR-009, FR-011, FR-018).

---

## Input

| Source | Value |
|--------|-------|
| Env var `BENCHMARK_EXTRACTION_MODE` | `"vision"` \| `"docling_text"` (operator-set at run time; R1 — baseline uses `docling_text`, not plain `docling`, to keep the chunker held-fixed) |
| Settings `knowledge_eval_temperature` | `float`, default `0.0` → `decoding = "greedy"` when `0.0` else `"sampled"` |

If `BENCHMARK_EXTRACTION_MODE` is unset: value is `"unknown"` and a WARNING is logged. The record is still written.

---

## Retrieval record (`benchmark_results.jsonl`)

`run_gold_standard_benchmark()` MUST add to the appended JSON object:

```jsonc
{
  // ...all existing fields unchanged...
  "extraction_mode": "vision",   // NEW — from BENCHMARK_EXTRACTION_MODE
  "decoding": "greedy"           // NEW — derived from knowledge_eval_temperature
}
```

## Comparison output (`compare_benchmark_runs`)

The printed header MUST name the extraction path for each run, e.g.:

```
Run A: 2026-07-07T..Z  (extraction_mode=docling, decoding=greedy)
Run B: 2026-07-07T..Z  (extraction_mode=vision,  decoding=greedy)
```

Existing per-category / exact_term / global rows and hybrid-config line are unchanged.

## Answer-eval run (`eval_runner.py` → `data/eval.db`)

The run identified by `run_id` MUST be labelled with `extraction_mode` and `decoding` (column on the record or a run-metadata sidecar), so the judge aggregate for that run is attributable when computing the vision-vs-docling delta.

---

## Behavioural guarantees

- **Additive only**: existing record fields keep their names, types, and values. Historical records without `extraction_mode`/`decoding` remain readable (`compare_benchmark_runs` shows `unknown`/absent gracefully — same tolerance it already has for missing `category_scores`).
- **No new required env var for normal app use**: `BENCHMARK_EXTRACTION_MODE` is read only by the harness scripts, never by the product runtime.
- **Comparability assertion**: a helper/step MUST confirm the two records being compared differ only in `extraction_mode` (all held-fixed fields equal) before the deltas are interpreted; a mismatch is surfaced, not silently compared.
