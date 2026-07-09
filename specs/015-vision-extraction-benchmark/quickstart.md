# Quickstart: Running the Vision Extraction Benchmark

The primary deliverable of feature 015 is a **recorded decision**, produced by running this procedure. It compares the vision extraction path against a fresh Docling baseline on ED4_Players_Guide, one variable at a time.

> Expect the vision ingestion to take ~30–90 min (one-time, accepted). Everything else is minutes.

## Prerequisites

- Ollama running locally and reachable at `OLLAMA_BASE_URL`.
- Models pulled: vision `blaifa/Nanonets-OCR-s`, embed `nomic-embed-text`, enrich `llama3.2`, answer `llama3.1`, and the judge model (`JUDGE_MODEL`).
- `.env` has `knowledge_eval_temperature=0.0` (greedy — the FR-018 default) and the judge env vars (`JUDGE_PROVIDER`, `JUDGE_MODEL`).
- A campaign UUID whose collection is the global knowledge base, and the ED4_Players_Guide PDF path.
- **Held fixed for both runs** (verify unchanged): cleaner, chunker, `knowledge_enrich_model=llama3.2`, `knowledge_embed_model=nomic-embed-text`, retrieval `top_k`, `hybrid_search_*`. Only `IngestionConfig.extraction_mode` changes.

## The one-variable rule

Between the two runs the ONLY difference is `extraction_mode` (`"docling"` vs `"vision"`) and the matching `BENCHMARK_EXTRACTION_MODE` label. If you change anything else, the comparison is void — start over.

---

## Run A — Docling baseline (fresh, current settings)

1. **Clean-slate** the corpus doc from both stores (vector + lexical `delete_by_doc`) so no stale chunks remain.
2. **Ingest** ED4_Players_Guide with `IngestionConfig(extraction_mode="docling_text")` — **not** plain `"docling"`. Confirm it completes and chunks are tagged `extraction_mode="docling_text"`.

   > **Chunker-parity correction**: plain `extraction_mode="docling"` routes through Docling's own `HybridChunker`, a *different* chunker than the one the vision path uses. `VisionPdfIngestor` always calls the shared `create_chunker()` (the app's configurable `KNOWLEDGE_CHUNKING_STRATEGY`, currently `agentic`) — and so does `extraction_mode="docling_text"`. Using plain `"docling"` as the baseline would silently change **two** variables (extraction *and* chunker) instead of one. `docling_text` is also what the currently-ingested production collection already uses, so it is the correct, already-representative baseline.
3. **Retrieval benchmark**:
   ```bash
   BENCHMARK_EXTRACTION_MODE=docling_text pytest harness/knowledge_qa/test_gold_standard.py -k recall_sanity -s
   ```
   → appends a `benchmark_results.jsonl` record with `extraction_mode=docling_text`, `decoding=greedy`.
4. **Answer generation + judge**:
   ```bash
   python harness/knowledge_qa/eval_runner.py --questions harness/knowledge_qa/rag_gold_standard.jsonl \
       --campaign-id <UUID> --role gm --run-id docling-015
   python harness/knowledge_qa/judge_runner.py --run-id docling-015 --summary
   ```
   → note the printed **aggregate** mean (primary metric).

## Run B — Vision path

1. **Clean-slate** the corpus doc again (delete Docling chunks from vector + lexical stores).
2. **Ingest** with `IngestionConfig(extraction_mode="vision")` (uses `blaifa/Nanonets-OCR-s`). **Record the wall-clock time** (FR-017). Must complete with zero aborted pages — a partial collection is NOT benchmarkable (FR-003); if it aborts, fix the model and re-run.
3. **Retrieval benchmark**:
   ```bash
   BENCHMARK_EXTRACTION_MODE=vision pytest harness/knowledge_qa/test_gold_standard.py -k recall_sanity -s
   ```
4. **Answer generation + judge**:
   ```bash
   python harness/knowledge_qa/eval_runner.py --questions harness/knowledge_qa/rag_gold_standard.jsonl \
       --campaign-id <UUID> --role gm --run-id vision-015
   python harness/knowledge_qa/judge_runner.py --run-id vision-015 --summary
   ```

---

## Produce the comparison

**Retrieval per-category diff** (Run A = docling, Run B = vision; `-1`/`-2` select the last two records):
```python
from harness.knowledge_qa.test_gold_standard import compare_benchmark_runs
compare_benchmark_runs(-2, -1)   # prints extraction_mode per run + ΔMRR/ΔnDCG/ΔRecall per category + global
```
Confirm the header shows `extraction_mode=docling_text` (A) vs `extraction_mode=vision` (B) and that all held-fixed config matches.

**Answer-quality delta**: `judge_delta = vision aggregate mean − docling aggregate mean` (from the two `--summary` outputs).

## Fidelity spot check (US4)

Run the spot-check helper against each collection (sample ≥10 chapter-openings, ≥5 tables) and classify by hand:
```bash
python harness/knowledge_qa/spot_check.py --extraction-mode docling_text
python harness/knowledge_qa/spot_check.py --extraction-mode vision
```
Record complete-opening and coherent-table counts per path.

---

## Apply the decision rule (FR-008) & record it

Recommend **vision as default** iff:
- `judge_delta ≥ −1.0 pp` (primary gate — non-inferior or better), **and**
- global `Recall@10` delta `≥ −2 pp` (no material retrieval regression).

If the judge score materially regresses → **keep Docling** regardless of retrieval gains (the feature-014 lesson). Otherwise → **inconclusive**.

Write the recommendation into the results doc / PR with: judge delta (vs 1.0 pp tolerance), per-category retrieval deltas, global Recall@10 delta (vs 2 pp), spot-check counts, vision ingestion wall-clock, and the single-pass-nondeterminism limitation note.

## Success check (maps to SC-001…007)

Validated end-to-end on 2026-07-08/09 — see [results.md](results.md) for full detail.

- [X] Vision ingestion completed, zero aborted pages, all chunks tagged `vision` (SC-001) — 282 chunks, `ingestion_status=ready`, `extraction_mode=vision` confirmed on all
- [X] Retrieval metrics produced for both paths on the same gold set (SC-002) — 118 questions, `gold_standard_path` identical
- [X] Judge aggregate produced for both paths (SC-003) — docling_text 0.838, vision 0.647
- [X] One per-category diff table + judge delta exists (SC-004) — `compare_benchmark_runs(-2, -1)` output in results.md
- [X] Records confirm only `extraction_mode` differs (SC-005) — `assert_comparable_extraction_runs()` passed
- [X] Spot check: ≥10 openings + ≥5 tables per path recorded (SC-006) — 10 openings + 5 tables sampled per path
- [X] Written recommendation applying the decision rule (SC-007) — **keep `docling_text`, do not adopt `vision`** (judge aggregate −19.1pp vs 1.0pp tolerance)
