# Research: Smart Chunking Strategy & Gold Standard Eval

**Feature**: `007-chunking-strategy-gold-standard`
**Date**: 2026-06-24
**Status**: Complete (benchmark scores TBD — filled during implementation)

---

## Decision 1 — Chunker Abstraction Design

**Decision**: Replace the concrete `MarkdownChunker` dependency with a `BaseChunker` ABC.
Both ingestors (`PdfIngestor`, `MarkdownIngestor`) accept a `BaseChunker` instance; a factory
function `create_chunker()` reads `KNOWLEDGE_CHUNKING_STRATEGY` from the environment and
returns the correct implementation.

**Rationale**: The existing ingestors hard-wire `MarkdownChunker`. Extracting an ABC keeps the
three implementations swappable without changing callers, satisfying Principle II (provider
abstraction). The factory pattern means switching strategy requires only an env-var change —
no code edits, no restart other than re-ingestion.

**Alternatives considered**:

- Pass strategy name as a string into `IngestionPipeline` — rejected; leaks configuration
  concerns into the pipeline instead of resolving them at the boundary.
- Make chunking a method on `Ingestor` — rejected; mixes conversion (PDF→MD) with splitting,
  making each concern harder to test independently.

---

## Decision 2 — Async Interface for Chunkers

**Decision**: `BaseChunker` exposes:
- `def chunk(self, text: str) -> list[str]` — sync, used by `HeadingChunker` and
  `SemanticChunker`
- `async def async_chunk(self, text: str) -> list[str]` — default implementation calls
  `chunk()` in a thread pool; overridden only by `AgenticChunker`

`IngestionPipeline._extract_chunks` becomes `async def _extract_chunks(...)` and calls
`await chunker.async_chunk(text)`.

**Rationale**: `AgenticChunker` must call the LLM for every section, making it inherently
async. `HeadingChunker` and `SemanticChunker` are CPU-bound and safe to run in a thread.
The default `async_chunk → thread pool → sync chunk` pattern avoids duplicating logic and
keeps the public interface consistent without forcing callers to branch on strategy type.

**Alternatives considered**:

- All-sync interface — rejected; blocks the event loop during LLM calls in `AgenticChunker`.
- All-async interface — rejected; forces `HeadingChunker` and `SemanticChunker` to be async
  unnecessarily, adding complexity with no benefit.

---

## Decision 3 — Semantic Chunking Algorithm

**Decision**: Implement `SemanticChunker` using a sliding-window sentence-embedding similarity
approach:

1. Split text into sentences using a lightweight regex sentence splitter (no heavy NLP dep).
2. Embed each sentence using the existing embedding function (`get_embed_fn()` from
   `rag.knowledge.embedder`). Batch all sentence embeddings in one call.
3. Compute cosine similarity between each consecutive sentence pair.
4. Identify breakpoints where similarity drops below a configurable percentile threshold
   (`KNOWLEDGE_SEMANTIC_BREAKPOINT_PERCENTILE`, default 95th percentile of all similarities
   in the document, i.e., the bottom 5% most dissimilar pairs become split points).
5. Group consecutive sentences between breakpoints into chunks.
6. Post-process: merge chunks below a minimum token count; split chunks above the max token
   budget at sentence boundaries. Apply table atomicity logic from `HeadingChunker`.

**Rationale**: This algorithm reuses the existing embedding model (nomic-embed-text via Ollama),
adds zero new dependencies, requires no LLM calls during ingestion, and typically improves
retrieval quality 10–20% over fixed-size chunking on factual Q&A corpora. The percentile
threshold is robust across documents of different lengths and topic densities.

**Alternatives considered**:

- Fixed cosine similarity threshold (e.g., < 0.7) — rejected; too sensitive to corpus
  variation (a Earthdawn table section and a lore section have inherently different similarity
  distributions; a fixed threshold would over-split one and under-split the other).
- External library (LangChain's `SemanticChunker`) — rejected; introduces a large transitive
  dependency for functionality the project can implement in ~100 lines using its existing
  embedding stack (Principle III: no package may exist solely for organizational purposes;
  each must have a declared domain responsibility).

---

## Decision 4 — Agentic Chunking Algorithm

**Decision**: Implement `AgenticChunker` using a heading-segmented proposition extraction
approach to keep LLM call count tractable:

1. First split text at heading boundaries (same as `HeadingChunker`) to produce N segments.
2. For each heading segment, send one LLM prompt: "Given this section of a rulebook, identify
   where it should be split into self-contained propositions. Return a JSON list of split
   indices (sentence numbers)."
3. Apply the returned split indices to produce chunks within the segment.
4. Post-process: same min/max token and table atomicity rules as Semantic.

LLM call count = N heading segments (not N sentences). For a 300-page Earthdawn PDF converted
to ~500 heading sections, this is ~500 LLM calls ≈ 8–15 minutes of ingestion time at typical
Ollama speeds. This is 2–3× slower than Semantic chunking but still within the background
processing window (spec FR-015 / user story in spec 005).

**Rationale**: Pure proposition-based agentic chunking (one LLM call per sentence pair) would
require thousands of calls per large PDF, making ingestion time exceed 30–60 minutes — an
unacceptable UX for a document management tool. The heading-segmented variant limits calls to
section count while still allowing the LLM to make intra-section split decisions that
semantic similarity cannot (e.g., "this paragraph introduces a new mechanic even though it
follows naturally from the previous sentence").

**Alternatives considered**:

- Pure proposition extraction (Kamradt's original approach, one LLM call per sentence) —
  rejected; O(N_sentences) calls → 30-60 min ingestion for large PDFs, unacceptable.
- Agentic chunking of full document in one shot — rejected; exceeds LLM context window for
  any document > 10 pages.

---

## Decision 5 — Gold Standard Harness Integration

**Decision**: Add `harness/knowledge_qa/test_gold_standard.py` that:

1. Loads questions from `harness/knowledge_qa/rag_gold_standard.jsonl` (path configurable via
   `GOLD_STANDARD_PATH` env var, defaulting to the repo-relative path).
2. Requires a running Ollama instance and populated ChromaDB — skips (not fails) if Ollama is
   unreachable (same auto-skip pattern as `test_integration.py`).
3. Runs all 118 questions through `ChromaKnowledgeRetriever.search()` at k=10.
4. Calls `evaluate_question()` and `aggregate_results()` from the existing `evaluator.py`.
5. Writes results to `harness/knowledge_qa/benchmark_results.jsonl` (appended, not overwritten)
   with a `strategy` field and ISO timestamp so multiple runs can be compared.
6. Asserts that the active strategy's aggregate Recall@10 ≥ 0.40 (a sanity check, not a
   performance gate — the ≥10% improvement gate is checked by comparing benchmark_results).

**Rationale**: A persistent `benchmark_results.jsonl` makes the three strategy runs directly
comparable without relying on human memory or external spreadsheets. Skipping when Ollama is
absent keeps CI green in environments without a running model server (matches spec 005 pattern).

**Alternatives considered**:

- Print-only benchmark (no persisted file) — rejected; scores from different runs cannot be
  compared programmatically.
- Assert strict numeric thresholds (MRR > 0.6, etc.) — rejected; the corpus content is
  user-supplied and varies across environments; only the relative improvement claim (≥10%
  over baseline) is meaningful and that requires comparing two run records.

---

## Decision 6 — Retrieval Chunking vs LLM Synthesis Context (Scope Boundary)

**Decision**: This feature improves *retrieval chunking only* — how text is split before
being embedded and stored in ChromaDB. The granularity of context supplied to the LLM for
answer synthesis is a **separate, independent concern** and is explicitly out of scope here.

**Why they are different**:

| Dimension | Retrieval chunking | LLM synthesis context |
|-----------|--------------------|-----------------------|
| Goal | Precision — find the most relevant fragment | Completeness — give the LLM enough context to write a good answer |
| Optimal size | Small (50–300 tokens) — fine-grained retrieval catches exact facts | Larger (300–1500 tokens) — LLM needs surrounding context to avoid hallucinating |
| Stored where | ChromaDB vectors | Assembled at query time from retrieved chunks |
| Changed by this spec? | ✅ Yes | ❌ No |

**What the current system does**: The chunk stored in ChromaDB IS the text sent to the LLM.
This means the same chunk size must serve both purposes — a compromise that may hurt either
retrieval precision (if chunks are too large) or answer quality (if chunks are too small).

**What is NOT in scope for this feature**: Techniques like "small-to-big retrieval" (store
small child chunks, but retrieve and send the parent section to the LLM), "sentence window
retrieval" (retrieve by sentence, expand to surrounding N sentences before synthesis), or
"parent document retrieval" (index individual sentences, return full document sections to
the LLM). These are valid future improvements but orthogonal to the chunking strategy
selection this feature addresses.

**How to detect if it matters**: If the gold standard benchmark shows good Recall@10 (the
right chunk is being retrieved) but users still report poor answer quality, the gap is likely
in the synthesis context size, not the retrieval strategy — that would be the trigger for a
context-expansion follow-up spec.

**Alternatives considered**:

- Implement "small-to-big" context expansion in this spec — rejected; doubles the scope and
  requires a separate metadata relationship (child chunk → parent section) that the current
  ChromaDB schema does not support. The retrieval metric improvement must be validated first.

---

## Benchmark Score Table

*To be filled during implementation, one row per strategy run.*

| Strategy | Mean MRR | Mean nDCG | Mean Recall@10 | Date |
|----------|----------|-----------|----------------|------|
| heading (baseline) | 0.5046 | 0.5890 | 0.8674 | 2026-06-25 |
| semantic (percentile=80, max=600) | 0.5607 | 0.6186 | 0.8660 | 2026-06-25 |
| agentic (1 section, max=600) | 0.5625 | 0.6227 | 0.8881 | 2026-06-25 |
| agentic (3 sections, max=2000) | 0.5767 | 0.6413 | 0.8966 | 2026-06-25 |

**Recommendation**: **`agentic` with `KNOWLEDGE_AGENTIC_BATCH_SECTIONS=3` and
`KNOWLEDGE_MAX_CHUNK_TOKENS=2000` is the winning strategy** and should become the new default.

**Quality signal**: Agentic (3 sections) achieved MRR 0.5767 — a **+14.3% improvement over the
heading baseline** (0.5046) and +2.8% over semantic (0.5607). It also leads on nDCG (+8.9% vs
heading) and Recall@10 (+3.4% vs heading). All three metrics point to the same winner. The
primary driver is cross-section merging: by giving the LLM visibility across 3 consecutive
heading sections at once, it can recognise when an "Overview" section and its adjacent "Rules"
and "Example" sections together describe a single mechanic — and keep them as one chunk. Embedding
similarity alone (semantic) cannot detect this because the transition between related sections
can be lexically smooth while still representing a meaningful boundary or non-boundary in RPG
rule structure.

**Ingestion cost**: Agentic requires the LLM to be available at ingestion time — one LLM call
per batch of 3 heading sections. For the Earthdawn PDF (~300 pages → ~500 heading sections →
~170 batches), ingestion takes 60–120 minutes with `llama3.1` on local hardware. This is
acceptable given that ingestion is a background, user-triggered operation (spec FR-015), and
the knowledge base is not expected to change frequently. If the LLM is unavailable, the chunker
falls back to one chunk per section (heading-chunker quality) and logs a WARNING — no data loss,
no silent degradation.

**Edge cases observed**: The fallback to one-chunk-per-section on LLM parse failure performed
correctly during testing. Table atomicity (heading + table rows stay together) was preserved
across all runs. The larger `max_tokens=2000` cap allows cross-section merged chunks to remain
intact without the `_split_large` path fragmenting them unnecessarily.

**Why not semantic**: Semantic chunking achieved MRR 0.5607 (+11.1% vs heading) and is a strong
second. Its main advantage — no LLM dependency at ingestion time — is outweighed by a 2.8%
MRR gap versus agentic. Recall@10 for semantic (0.8660) actually regressed slightly vs heading
(0.8674), suggesting that embedding-similarity breakpoints occasionally split related content
that the heading splitter kept together. For a future deployment where Ollama is unavailable,
`semantic` is the recommended fallback.

**Configuration to adopt** (already set in `.env`):

```
KNOWLEDGE_CHUNKING_STRATEGY=agentic
KNOWLEDGE_AGENTIC_BATCH_SECTIONS=3
KNOWLEDGE_MAX_CHUNK_TOKENS=2000
KNOWLEDGE_ENRICH_MODEL=llama3.1
```
