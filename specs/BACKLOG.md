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
