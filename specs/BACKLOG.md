# Spec Backlog

Ideas approved for future specs, captured before they have a full specification.

---

## Spec 009 — Breadcrumb Injection, Contextual Retrieval & Multi-Source Corpus

**Intent**: Improve retrieval quality by making every chunk context-aware.

- **Breadcrumb injection**: attach `Book > Chapter > Section` path to each chunk's metadata so structural context travels with the chunk into retrieval results
- **Contextual retrieval**: LLM prepends a 1-2 sentence situating summary to each chunk before embedding (Anthropic technique), so long-distance semantic connections become local to the chunk
- **Multi-source metadata**: tag each chunk with source type (`rulebook`, `supplement`, `handwritten`, `novel`) to enable source-weighted or source-filtered retrieval
- **Embedding model comparison**: benchmark `qwen3-embedding:4b` vs current `nomic-embed-text` as an additional eval axis (matrix run: chunking strategy × embedding model); re-ingestion required anyway when breadcrumbs are added
- **Scope**: retrieval chunking only; LLM synthesis context remains a separate concern

**Trigger**: After spec 008 corpus cleaning lands — breadcrumb injection depends on clean heading signals.

---

## Spec 010 — Answer Evaluation (End-to-End Quality Measurement)

**Intent**: Close the loop from retrieval quality (MRR, nDCG, Recall@k) to answer quality.

- LLM-as-judge or RAGAS framework to score faithfulness, answer relevance, and correctness
- `reference_answer` fields in `rag_gold_standard.jsonl` are the ground truth
- Extends the benchmark harness to run the full pipeline (retrieval + generation), not just retrieval
- Enables detecting the gap: good Recall@k but bad answers → points to synthesis context expansion

**Trigger**: After spec 009 lands and retrieval quality is stable enough to isolate generation quality as the variable.

---

## Spec 016 — Retrieval Tuning & Few-Shot Prompting

**Intent**: Squeeze quality out of the retrieval + generation stack *after* the extraction path is locked by the vision benchmark (spec 015). This is the deferred tuning work from feature 014 plus the untapped few-shot headroom in the enricher.

- **Few-shot prompt upgrades** (all enricher prompts are zero-shot today — `packages/rag/rag/knowledge/enricher.py`):
  - **Query expansion** — add worked examples of good game-specific rephrasings; most likely to move retrieval.
  - **Rerank** — add few-shot examples; prime suspect for the feature-014 judge-score regression.
  - **Chunk enrichment** (topic / access_level / headline) — few-shot for more consistent metadata.
- **Hyperparameter tuning** (retrieval-side params need no re-ingestion, so iterate fast):
  - Hybrid-search keyword/vector weights, RRF `k`, per-collection `top_k`.
  - Enrichment model choice (`knowledge_enrich_model` is `llama3.2`, a small model — treat as a knob).
- **Close out the feature-014 SC-003 judge regression** (−3.3pp) — this spec owns fixing it. Supersedes the standalone "hybrid search tuning follow-up" note.
- **Method**: change one variable at a time, re-baseline against the winning extraction path from spec 015. Do NOT start until 015 has picked the corpus/extraction path — otherwise prompts are tuned against a corpus about to be replaced.

**Trigger**: After spec 015 (vision extraction benchmark) lands and the extraction path is chosen.

---

## Deferred / contingency — LLM corpus reformatting pass

**Intent**: A generative pass that rewrites each corpus segment (post PDF→markdown) into clean markdown to fix residual table/format problems.

**Status**: **Not scheduled — likely superseded by vision extraction (spec 015).** Vision (Nanonets-OCR-s reading the rendered page) delivers the same clean-tables benefit while grounded in actual pixels, so it can't fabricate text the way a blind text→text rewrite can. Blindly rewriting a *rules* corpus with a local model risks silent fidelity loss (dropped clauses, altered stat-block numbers) with no cheap way to detect it.

**Only revisit if**: tables are *still* bad after the vision benchmark — and then only as a **scoped, table-only** reformatting pass where cell counts can be diffed against the source, never a whole-corpus rewrite.
