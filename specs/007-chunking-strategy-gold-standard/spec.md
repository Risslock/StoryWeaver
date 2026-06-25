# Feature Specification: Smart Chunking Strategy & Gold Standard Eval

**Feature Branch**: `007-chunking-strategy-gold-standard`

**Created**: 2026-06-24

**Status**: Draft

**Input**: User description: "I want to improve the chunking and read strategy, specially for big pdf files. Research this two options to try and find the best for the product: Semantic Chunking and Agentic chunking. Also i want to use a gold standard file to check the retrieval. This file is now located in ""C:\Users\juane\Downloads\rag_gold_standard.jsonl"" but should be copied into the repo for easy eval and testing"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Run Retrieval Eval Against Gold Standard (Priority: P1)

A GM or developer triggers the RAG evaluation harness using the committed gold standard file
(`harness/knowledge_qa/rag_gold_standard.jsonl`). The harness runs every question through the
retrieval pipeline and reports MRR, nDCG, and Recall@k so the team can objectively compare
chunking strategies before and after any change.

**Why this priority**: Without a fixed, reproducible benchmark the team cannot know whether a
new chunking strategy is an improvement or a regression. The gold standard file anchors all
chunking experiments to a consistent question set.

**Independent Test**: Point the evaluation harness at `rag_gold_standard.jsonl`, run it against
the current knowledge base, and verify numeric MRR / nDCG / Recall@10 scores are produced for
all 118 questions.

**Acceptance Scenarios**:

1. **Given** `rag_gold_standard.jsonl` is present in `harness/knowledge_qa/`, **When** the
   evaluation harness is invoked, **Then** it loads all questions from that file without error.
2. **Given** a knowledge base is populated with the Earthdawn rulebook content, **When** the
   evaluation runs, **Then** per-question MRR, nDCG, and Recall@10 are produced for all 118
   questions and aggregate means are reported.
3. **Given** two chunking strategies have each been evaluated, **When** their aggregate scores
   are compared, **Then** the improvement (or regression) in mean MRR / nDCG / Recall@10 is
   quantifiable.

---

### User Story 2 - Adopt Winning Chunking Strategy for Large PDFs (Priority: P1)

After the two chunking strategies are benchmarked using the gold standard, the winning approach
replaces the current heading-based `MarkdownChunker`. The new chunker handles large PDFs
(hundreds of pages, multi-column layouts, dense tables) without the quality degradation seen
with the current fixed-size heading split.

**Why this priority**: Chunking quality directly determines retrieval quality. The current
heading-based splitter loses context across large tables and multi-paragraph rules; both
Semantic and Agentic chunking address this in different ways.

**Independent Test**: Ingest a large PDF (≥ 100 pages), run the gold standard evaluation,
and confirm that mean MRR, nDCG, and Recall@10 are each ≥ 10% higher than the baseline
recorded with the old chunker.

**Acceptance Scenarios**:

1. **Given** a large PDF is submitted for ingestion, **When** the new chunker processes it,
   **Then** chunks are produced without error and each chunk is semantically coherent (does not
   cut mid-sentence or split a rule from its table at an arbitrary size boundary).
2. **Given** a document with dense tables (e.g., race attributes), **When** chunked by the new
   strategy, **Then** each table is contained in a single chunk alongside its heading, not split
   across multiple chunks.
3. **Given** the new chunker is active, **When** the gold standard evaluation is run,
   **Then** aggregate mean MRR and nDCG improve over the recorded baseline.
4. **Given** the new chunker fails for any reason, **Then** a descriptive error is surfaced in
   the UI and ingestion is marked as failed (Principle VII) — no silent partial ingest.

---

### User Story 3 - Semantic Chunking vs Agentic Chunking Research & Decision (Priority: P2)

The team researches Semantic Chunking (split on embedding similarity drops between adjacent
sentences) and Agentic Chunking (LLM decides where to split by actively labeling propositions).
Both are benchmarked against the gold standard. Findings and the decision rationale are
recorded in a research document so future contributors understand what was tried and why the
winning strategy was chosen.

**Why this priority**: Choosing blindly risks picking a strategy that is slower (Agentic) or
less precise (Semantic) for this specific corpus. A documented comparison prevents relitigating
the decision later.

**Independent Test**: A research document exists in `specs/007-chunking-strategy-gold-standard/`
with benchmark scores for both strategies and a recommendation with rationale.

**Acceptance Scenarios**:

1. **Given** both strategies are implemented as swappable backends behind the `packages/rag/`
   abstraction, **When** each is benchmarked with the gold standard, **Then** scores for both
   are captured in the research document.
2. **Given** the research document is complete, **When** a developer reads it,
   **Then** they can reproduce either benchmark run and understand the decision without needing
   additional context.

---

### Edge Cases

- What happens when a PDF has no headings (scanned text converted via OCR)?
  The chunker MUST fall back to paragraph-boundary splitting and MUST NOT produce empty chunks.
- What happens when a single paragraph or table row exceeds the maximum chunk token budget?
  The chunker MUST hard-split at the nearest sentence boundary and log a WARNING with the
  source document and position.
- What happens when the LLM is unavailable during Agentic chunking?
  Ingestion MUST fail explicitly with a user-visible error — it MUST NOT silently fall back to
  structural splitting without the user's knowledge.
- What happens when the gold standard file is absent or malformed?
  The evaluation harness MUST report a clear error naming the missing or invalid file;
  evaluation MUST NOT silently skip questions.
- What happens when a very large PDF (500+ pages) takes too long to chunk?
  Background processing (per FR-015 in spec 005) remains in effect; the UI shows "processing"
  status throughout and does not time out the user session.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The file `harness/knowledge_qa/rag_gold_standard.jsonl` MUST be committed to the
  repository so any developer or CI run can execute the gold standard benchmark without
  obtaining the file from an external location.
- **FR-002**: The evaluation harness MUST accept a configurable path to a gold standard JSONL
  file; `rag_gold_standard.jsonl` MUST be the default path for all benchmark runs.
- **FR-003**: The chunking strategy MUST be selectable via an environment variable or
  configuration file with no code changes required to switch between strategies (Principle II).
- **FR-004**: Both Semantic and Agentic chunking strategies MUST be implemented as discrete,
  independently testable backends behind the existing `packages/rag/` abstraction interface.
- **FR-005**: The Semantic chunking strategy MUST split content at points where embedding
  similarity between adjacent text units falls below a configurable threshold, grouping
  semantically related sentences into a single chunk.
- **FR-006**: The Agentic chunking strategy MUST use a language model to identify proposition
  boundaries and decide where to split content based on thematic completeness, treating each
  self-contained fact or rule as a candidate chunk.
- **FR-007**: Both strategies MUST preserve table atomicity: a table and its heading MUST remain
  in the same chunk unless the table alone exceeds the maximum chunk token budget.
- **FR-008**: Both strategies MUST produce chunks that are each independently enrichable
  (headline, summary, topic, access level) by the existing enricher pipeline.
- **FR-009**: The research document (`research.md`) for this feature MUST record:
  - Baseline MRR, nDCG, Recall@10 with the current heading-based chunker.
  - MRR, nDCG, Recall@10 for Semantic chunking.
  - MRR, nDCG, Recall@10 for Agentic chunking.
  - The recommended strategy with written rationale (quality, cost, latency trade-offs).
- **FR-010**: The winning strategy MUST replace the current `MarkdownChunker` as the default
  while the losing strategy remains available behind the environment-variable toggle.
- **FR-011**: The system MUST log the active chunking strategy name at `INFO` level when an
  ingestion run starts (Principle VIII).
- **FR-012**: All chunking errors MUST be caught and surfaced to the user with a descriptive
  message in the Gradio UI; no silent partial ingestion (Principles VII, VIII).

### Key Entities

- **GoldStandardQuestion**: One evaluation case in `rag_gold_standard.jsonl` — `question`
  (string), `keywords` (list[str]), `reference_answer` (string), `category` (string).
  118 questions covering direct facts, rule lookups, and multi-step reasoning about the
  Earthdawn rulebook.
- **ChunkingStrategy**: An interchangeable backend (`semantic` | `agentic` | `heading`) selected
  via environment variable. Each strategy implements the same interface: accepts text, returns
  `list[str]` of chunks.
- **ChunkBenchmarkResult**: Scores recorded per strategy: `strategy` (string), `mean_mrr`
  (float), `mean_ndcg` (float), `mean_recall_at_k` (float), `k` (int), `total_questions` (int).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: `harness/knowledge_qa/rag_gold_standard.jsonl` is present in the repository and
  the evaluation harness can load and run all 118 questions without any manual file placement
  by the developer.
- **SC-002**: The gold standard benchmark run completes in under 5 minutes against a populated
  knowledge base on typical development hardware.
- **SC-003**: The winning chunking strategy achieves a mean MRR ≥ 10% higher than the baseline
  heading-based chunker score, measured against the gold standard.
- **SC-004**: The winning chunking strategy achieves a mean Recall@10 ≥ 10% higher than the
  baseline heading-based chunker score, measured against the gold standard.
- **SC-005**: A developer can switch between chunking strategies by changing a single
  environment variable and re-running ingestion — no code edits required.
- **SC-006**: Large PDFs (≥ 100 pages) ingest without error or timeout under either new strategy.
- **SC-007**: The research document records all three strategy benchmark scores and a written
  rationale for the final recommendation, verifiable by reading `research.md`.

## Assumptions

- The gold standard file (`rag_gold_standard.jsonl`, 118 questions) is authoritative and
  comprehensive enough to distinguish meaningful chunking quality differences; additional
  questions may be added in a future spec if coverage gaps are discovered.
- The current `MarkdownChunker` heading-based approach is the baseline to beat; its scores
  are established first before either new strategy is implemented.
- Semantic chunking will use the same embedding model already configured in `packages/rag/`
  (nomic-embed-text via Ollama for local; cloud embeddings via environment variable);
  no new embedding model or provider is introduced.
- Agentic chunking uses the same LLM already configured for the enricher; adding a chunking
  pass increases ingestion cost but reuses existing provider infrastructure (Principle II, IV).
- The PDF-to-Markdown conversion step (upstream of chunking) remains unchanged; both new
  strategies receive Markdown text as input, same as the current `MarkdownChunker`.
- Table preservation is a hard requirement given the Earthdawn rulebook's heavy use of
  attribute tables, skill tables, and spell lists where splitting a table would destroy
  retrievability.
- Both strategies are evaluated on the same ingested corpus (same PDF, same conversion output)
  to ensure a fair comparison; only the chunking step differs.
- Switching the default chunker is a breaking change for existing indexed data; re-ingestion
  of all documents is required after the strategy change and is considered acceptable for
  the current development stage.
- Mobile support remains out of scope; the evaluation harness and chunking pipeline are
  server-side concerns.
