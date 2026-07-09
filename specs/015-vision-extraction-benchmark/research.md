# Phase 0 Research: Vision Extraction Benchmark

Resolves the open decisions implied by the Technical Context. Each entry: **Decision / Rationale / Alternatives considered**.

---

## R1 — How is a benchmark run attributed to an extraction path?

**Decision**: The operator sets an environment variable `BENCHMARK_EXTRACTION_MODE` (`"vision"` | `"docling_text"`) at benchmark time; `run_gold_standard_benchmark()` reads it and writes it onto the `benchmark_results.jsonl` record as `"extraction_mode"`. `eval_runner.py` reads the same variable and stamps it onto the eval run. If the variable is unset, default to `"unknown"` and log a WARNING (the record is still written, but the comparison will flag it).

> **Correction found during implementation**: the baseline `IngestionConfig.extraction_mode` value is `"docling_text"`, not plain `"docling"`. Plain `"docling"` routes through Docling's own `HybridChunker`; `"docling_text"` and `"vision"` both route through the shared `create_chunker()` (the app's configurable `KNOWLEDGE_CHUNKING_STRATEGY`). Using plain `"docling"` as the baseline would have changed two variables (extraction *and* chunker) instead of one — see plan.md Constraints and quickstart.md Run A.

**Rationale**: The retrieval harness only queries the live collection; it has no intrinsic knowledge of how that collection was ingested. The extraction path is a property of the *ingestion run*, not the retriever. An explicit operator-supplied variable matches the existing "operator drives the run" model (same as `GOLD_STANDARD_PATH`), is trivially auditable, and keeps the two record sinks (retrieval JSONL + eval.db) consistent with a single source of truth.

**Alternatives considered**:
- *Read `extraction_mode` from a sampled retrieved chunk's metadata*: the value IS stored per chunk (`pipeline.py:338`), but `KnowledgeChunk` does not currently surface it, and a mixed collection (if clean-slate is skipped) would give an ambiguous answer. Rejected as implicit and fragile; the env var is explicit.
- *A new config/Settings field*: over-couples a transient benchmark parameter to global app config. Rejected.

---

## R2 — How is greedy decoding (temperature 0) applied to evaluation?

**Decision**: Add a `knowledge_eval_temperature` Settings field (default `0.0`) and thread a `temperature` into `OllamaProvider.generate()` / `generate_structured()` via the OpenAI-compatible payload (`"temperature": <value>`). The generation path (`ask_question` → answer LLM) and the judge path (when `JUDGE_PROVIDER=ollama`) both resolve their temperature from this field. When `JUDGE_PROVIDER=claude`, pass `temperature=0` through the existing Anthropic provider call.

**Rationale**: The Ollama OpenAI-compatible `/v1/chat/completions` endpoint honors `temperature`; today none is sent, so Ollama's server default (~0.8) makes every run non-deterministic — exactly the variance FR-018 controls. A single Settings-backed default keeps it declarative and mirrored into `.env`. Temperature 0 (greedy) is the standard determinism setting for LLM-as-judge and for reproducible generation benchmarks.

**Alternatives considered**:
- *Per-call temperature argument only, no Settings field*: works but scatters the value and can't be documented in `.env`. Rejected in favor of a config default that per-call may still override.
- *`seed` parameter instead of/in addition to temperature*: Ollama supports `seed`, but greedy decoding is the simpler, model-agnostic determinism lever and is sufficient for a single-pass benchmark. Seed is noted as a possible future refinement, not required here.
- *Measure the noise floor via repeated passes* (spec Q2 option A): explicitly rejected by the clarification — single pass + greedy was chosen. Residual local-model nondeterminism is accepted as a stated limitation.

---

## R3 — How is the collection kept clean between the two ingestions?

**Decision**: Before each ingestion, delete the corpus document's existing chunks from **both** stores — `ChromaVectorStore.delete_by_doc(collection, doc_id)` and the lexical FTS5 store's `delete_by_doc(doc_id)` — then ingest with the target `extraction_mode`. The run procedure is strictly sequential: (Docling: clean → ingest → benchmark → eval → judge), then (Vision: clean → ingest → benchmark → eval → judge).

**Rationale**: Both paths write to the same `knowledge_global` collection (`pipeline.py:172`), and vision vs docling produce different chunk counts and IDs, so a plain re-ingest (upsert) would leave stale chunks from the other path and pollute retrieval. `delete_by_doc` already exists on the vector store (`vector_store.py:109`); pairing it with the lexical delete guarantees a single-path collection. Sequential runs are required anyway because there is one shared collection.

**Alternatives considered**:
- *Separate per-mode collections* (`knowledge_global__vision`): cleaner isolation and would allow both to coexist, but requires threading a collection suffix through ingestion + retrieval — a larger change than the benchmark warrants, and the retrieval harness hardcodes the global collection. Rejected for this feature; noted as a possible future ergonomic improvement.
- *Drop/recreate the whole collection*: heavier and risks other documents if the collection is shared. `delete_by_doc` is the surgical, existing primitive.

---

## R4 — How is the answer-quality (judge) delta computed between the two runs?

**Decision**: Each path gets its own `eval_runner.py` `run_id` (answers) → `judge_runner.py` (scores) → `judge_runner.py --summary` prints per-dimension means (faithfulness, relevance, context_utilization, answer_correctness, aggregate) for that run. The vision-vs-docling **judge delta** is the difference of the two runs' `aggregate` means (and per-dimension means), compared against the 1.0 pp non-inferiority tolerance. A tiny read-only helper (or a documented manual step in quickstart) diffs the two `run_id` aggregates.

**Rationale**: `judge_runner.py` already computes and prints per-run mean scores (`judge_runner.py:183-188`); the aggregate mean is the primary gate per FR-008. Two run_ids + a subtraction is the minimal path to the delta; no new scoring machinery is needed.

**Alternatives considered**:
- *A full judge-comparison CLI mirroring `compare_benchmark_runs`*: nicer, but gold-plates a one-time decision. A documented subtraction (optionally a ~20-line helper reading eval.db by two run_ids) suffices. Kept optional.

---

## R5 — How is the US4 fidelity spot check performed?

**Decision**: A new read-only helper `harness/knowledge_qa/spot_check.py` samples from the *current* collection: ≥10 chunks whose text begins a chapter/section (chapter-opening candidates) and ≥5 chunks containing table markup (`|…|` rows), printing each for human classification (complete-opening vs drop-cap-gap; coherent-table vs mangled-table). Run it once against the vision collection and once against the Docling collection; record the counts and side-by-side notes in the results write-up. Classification is human judgment, not automated.

**Rationale**: The defects vision targets (dropped drop-cap first letters, collapsed tables) are localized and can be invisible to aggregate metrics — a human eyeball on a small sample is the cheapest reliable signal (spec US4). Sampling from the live collection reuses existing retrieval/store access; no new extraction needed.

**Alternatives considered**:
- *Automated table/opening detection*: brittle and out of proportion for a P3 sample; human classification over a small N is more trustworthy and faster to build.

---

## R6 — Baseline freshness (which Docling record to compare against)

**Decision**: Always produce a **fresh Docling baseline** under current downstream settings as part of this feature's run, rather than reusing the most recent historical `benchmark_results.jsonl` Docling record. The comparison uses the two freshly produced records (Docling, Vision) with identical held-fixed config.

**Rationale**: FR-012 / US3 AC2 require re-running the baseline if prior settings differ. Hybrid search (014) and other defaults landed after older records; a fresh baseline under today's exact config is the only way to guarantee "only extraction path changed." Producing both records in one sitting removes any doubt.

**Alternatives considered**:
- *Reuse last Docling record*: risks a two-variable comparison (e.g., pre-hybrid vs post-hybrid). Rejected unless the record's captured config provably matches — and producing a fresh one is cheap relative to the vision ingestion cost.
