# Feature Specification: Hybrid Search for Knowledge Retrieval

**Feature Branch**: `014-hybrid-search`

**Created**: 2026-07-07

**Status**: Draft

**Input**: User description: "Add hybrid search to the RAG retrieval pipeline, combining keyword-based search (e.g. BM25) with the existing vector similarity search, so that retrieval quality improves for queries where pure semantic/vector search and reranking currently miss the best-fitting chunks. This should be measurable using the existing retrieval eval harness (MRR, nDCG, Recall@10) and the LLM-as-judge answer evaluation pipeline from spec 013, to confirm hybrid search actually improves both retrieval and downstream answer quality over the current vector+rerank approach."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Exact-Term Queries Return the Right Chunk (Priority: P1)

A player or GM asks a question that references a specific rule name, item name, spell, or numeric value (e.g. "What does the Second Wind talent do?" or "What's the Threshold for a Sturdy target?"). Today, pure semantic search sometimes ranks paraphrased or thematically related chunks above the chunk that contains the literal term, so the answer is incomplete or wrong. With hybrid search, the chunk containing the literal term is reliably retrieved and surfaced to the reranker.

**Why this priority**: This is the concrete quality gap the user has observed — reranking alone cannot fix retrieval when the correct chunk was never in the candidate set to begin with.

**Independent Test**: Can be fully tested by running a query containing an exact rule/item name against the retrieval pipeline with hybrid search enabled and confirming the chunk containing that literal term appears in the top-k candidates, where it previously did not with vector-only search.

**Acceptance Scenarios**:

1. **Given** a query containing an exact term that appears verbatim in exactly one indexed chunk, **When** the query is run through hybrid search, **Then** that chunk is present in the returned candidate set.
2. **Given** the same query run through the current vector-only pipeline, **When** compared against the hybrid result, **Then** the evaluator can confirm whether hybrid search recovered a chunk that vector-only search missed.

---

### User Story 2 - Measurable Retrieval and Answer Quality Improvement (Priority: P1)

A developer runs the existing retrieval eval harness and LLM-as-judge pipeline once with hybrid search disabled (baseline) and once with it enabled, over the same gold-standard question set, and gets a side-by-side comparison of retrieval metrics (MRR, nDCG, Recall@10) and response quality scores (faithfulness, answer relevance, context utilization, answer correctness).

**Why this priority**: Without this, hybrid search is a guess. The project already has the measurement infrastructure (spec 013); this feature is only worth shipping if it demonstrably improves outcomes on that infrastructure.

**Independent Test**: Can be fully tested by running the harness eval + judge commands twice (hybrid off, hybrid on) against the same gold-standard dataset and confirming both runs produce complete metric reports that can be compared side by side.

**Acceptance Scenarios**:

1. **Given** the gold-standard benchmark dataset and hybrid search disabled, **When** the developer runs the harness eval and judge commands, **Then** a baseline report of retrieval metrics and judge scores is produced.
2. **Given** the same dataset and hybrid search enabled, **When** the developer runs the same commands, **Then** a comparable report is produced using the same metric definitions.
3. **Given** both reports, **When** the developer compares them, **Then** the comparison clearly shows whether hybrid search improved, regressed, or had no effect on each metric.

---

### User Story 3 - Toggle Hybrid Search Without Code Changes (Priority: P2)

A developer enables or disables hybrid search, and adjusts how much weight keyword matches get relative to semantic matches, via configuration only — consistent with how the judge provider and other pipeline behaviors are already configured in this project.

**Why this priority**: The project's provider-abstraction principle requires this to be safe to experiment with and roll back without a deploy. It's also required to produce the baseline-vs-hybrid comparison in User Story 2.

**Independent Test**: Can be fully tested by flipping a configuration value, restarting the pipeline, and confirming retrieval behavior changes accordingly with no code modification.

**Acceptance Scenarios**:

1. **Given** hybrid search is disabled via configuration, **When** a query is run, **Then** retrieval behaves exactly as it does today (vector search only).
2. **Given** hybrid search is enabled via configuration, **When** a query is run, **Then** both keyword and vector signals contribute to the candidate set.
3. **Given** an invalid or out-of-range configuration value for hybrid weighting, **When** the pipeline starts, **Then** it fails with a clear configuration error rather than silently falling back to a default.

---

### Edge Cases

- What happens when a query has no meaningful keyword overlap with any indexed chunk (fully conversational or paraphrased query)? The system must fall back to relying on the vector signal without degrading result quality versus today's vector-only baseline.
- What happens when a query matches many chunks on keywords but few or none are semantically relevant (e.g. a common word appears in many unrelated chunks)? The fused ranking must not let keyword-only noise crowd out semantically strong candidates.
- What happens when new documents are ingested, or existing chunks are updated/deleted? The keyword-searchable index must reflect the same set of chunks as the vector store — no chunk should be findable by one signal but not the other.
- What happens to role-based visibility filtering (`player_visible` vs GM-only content)? Keyword search results must respect the same access-level filtering already applied to vector search results.
- What happens when hybrid search is enabled but the keyword index has not yet been built for a given collection (e.g. right after a fresh ingestion)? The system must not silently return empty or partial results — it must either build the index as part of ingestion or clearly signal that hybrid search is unavailable for that collection.
- What happens for very short or single-word queries, which historically produce noisy keyword matches? The candidate set size considered per signal before fusion must remain bounded, consistent with how vector search already bounds candidates per query variant.

## Clarifications

### Session 2026-07-07

- Q: SC-001/SC-002/SC-003 use unquantified terms ("no more than a negligible margin", "improves measurably"). What threshold should the eval harness use to decide pass/fail when comparing baseline vs. hybrid runs? → A: Absolute ≤2 percentage points — a metric only counts as regressed if it drops by more than 2 points, and only counts as improved if it rises by more than 2 points, relative to the baseline run.
- Q: SC-004 requires "no re-ingestion of already-embedded content required" to compare baseline vs. hybrid. How should the lexical index be built for collections ingested before hybrid search ships? → A: An explicit, developer-invoked one-time migration command backfills the lexical index from already-stored chunk text, without re-embedding or re-ingesting.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST support a keyword-based (lexical) search signal over the same chunk text already indexed for vector search, in addition to — not instead of — the existing vector similarity search.
- **FR-002**: The system MUST combine lexical and vector search results into a single fused, ranked candidate list before the existing LLM reranking step runs, using the same rank-fusion approach already used to combine multi-query vector results.
- **FR-003**: Lexical search MUST operate over the same two-tier collection scope as vector search today (global knowledge base plus the active campaign's knowledge base), and MUST apply the same role-based access-level filtering (`player_visible` vs GM-only) as vector search.
- **FR-004**: Hybrid search MUST be togglable on/off via configuration, with no code changes required, so it can be A/B compared against the current vector-only pipeline.
- **FR-005**: When hybrid search is enabled, the relative contribution of keyword vs. vector signals in the fused ranking MUST be adjustable via configuration.
- **FR-006**: The keyword-searchable index MUST stay in sync with the vector store automatically as part of the existing ingestion, update, and deletion flows — no separate manual sync step.
- **FR-007**: The existing LLM reranking step MUST continue to run unchanged on the fused candidate list, regardless of whether hybrid search is enabled.
- **FR-008**: When a query produces no meaningful keyword matches, the system MUST still return results, ranked using the vector signal, with quality no worse than today's vector-only baseline.
- **FR-009**: The retrieval eval harness MUST be able to run the full benchmark (retrieval metrics and LLM-judge response quality) with hybrid search enabled or disabled via the same configuration toggle used in production, so both configurations can be evaluated against the same gold-standard dataset without code changes between runs.
- **FR-010**: The system MUST expose, per returned chunk, enough information to determine whether it was surfaced via the keyword signal, the vector signal, or both — to support debugging and tuning of the fusion behavior.
- **FR-011**: The system MUST provide an explicit, developer-invoked one-time migration command that backfills the Lexical Index for chunks ingested before hybrid search was introduced, operating on already-stored chunk text without re-invoking embedding generation or re-ingestion, so that SC-004's baseline-vs-hybrid comparison can run without re-ingesting the existing gold-standard dataset.

### Key Entities

- **Lexical Index**: A keyword-searchable structure over chunk text (and associated searchable metadata such as headline/breadcrumb), scoped per collection (global and per-campaign) the same way the vector store is scoped today. Kept in sync with the vector store's chunk lifecycle (create, update, delete).
- **Fused Candidate**: A knowledge chunk in the retrieval result set, carrying a combined rank/score derived from whichever signal(s) — lexical, vector, or both — returned it, before reranking is applied. Extends the existing retrieved-chunk representation rather than replacing it.
- **Hybrid Search Configuration**: The set of configuration values controlling whether hybrid search is active and how keyword vs. vector signals are weighted in fusion.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On the existing gold-standard benchmark, enabling hybrid search improves Recall@10 and/or MRR versus the current vector+rerank baseline by more than 2 percentage points, with no metric regressing by more than 2 percentage points versus the baseline.
- **SC-002**: For gold-standard questions that reference exact rule names, item names, or numeric values, Recall@10 for that subset improves by more than 2 percentage points when hybrid search is enabled, compared to the vector-only baseline on the same subset.
- **SC-003**: Downstream answer quality, as measured by the LLM-as-judge aggregate score, does not regress by more than 2 percentage points when hybrid search is enabled, and improves by more than 2 percentage points on the exact-term question subset from SC-002.
- **SC-004**: A developer can produce a full side-by-side comparison (baseline vs. hybrid) of retrieval metrics and judge scores by toggling one configuration value and re-running the existing harness commands — no code changes and no re-ingestion of already-embedded content required.
- **SC-005**: Enabling or disabling hybrid search in a running environment does not require rebuilding existing vector embeddings.

## Assumptions

- The existing multi-query vector retrieval and RRF-based fusion in `packages/rag/rag/knowledge/retriever.py` is the integration point: hybrid search adds a keyword-based result set into the same fusion step that today only combines multiple vector query variants.
- The existing LLM-based reranking step (`ChunkEnricher.rerank`) is retained unchanged; hybrid search is strictly a retrieval-stage (pre-reranking) improvement.
- The existing gold-standard dataset (`rag_gold_standard.jsonl`) and harness (spec 013's eval + judge commands) are reused for measurement; no new evaluation infrastructure is built, though the dataset may need a small number of questions tagged as "exact-term" to measure SC-002 as a distinct subset.
- Keyword index storage/technology is a planning-phase decision; this spec only requires that a lexical signal exists, stays in sync with the vector store, and is measurable — not which library or storage engine implements it.
- Fusion weighting defaults to equal contribution between keyword and vector signals unless configured otherwise, consistent with the equal-weighting behavior of the existing multi-query RRF fusion.
- This feature applies uniformly across all source types (`rulebook`, `supplement`, `handwritten`, `novel`); no source-type-specific keyword search behavior is required for v1.
