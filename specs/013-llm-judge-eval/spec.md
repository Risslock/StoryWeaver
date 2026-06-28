# Feature Specification: LLM-as-Judge Response Evaluation

**Feature Branch**: `013-llm-judge-eval`

**Created**: 2026-06-28

**Status**: Draft

**Input**: User description: "I want to add response evaluation using an LLM as judge."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Batch Eval Then Judge Produces Combined Quality Report (Priority: P1)

A developer first runs the harness eval command to generate responses and write EvaluationRecords, then runs the separate judge command to score those records. After both steps, a summary report shows retrieval metrics (MRR/nDCG/Recall@10) alongside response quality scores (faithfulness, answer relevance, context utilization) in a single view.

**Why this priority**: Retrieval metrics tell us *what* was found; response quality metrics tell us *how well* the system answered. Without this, a response that hallucinates or ignores the context is indistinguishable from a correct one at the harness level.

**Independent Test**: Can be fully tested by running the eval command on a 5–10 question dataset, then running the judge command, and confirming that EvaluationRecords in the store contain both the stored response and all judge score fields.

**Acceptance Scenarios**:

1. **Given** a harness dataset with gold-standard questions, a `--campaign-id` pointing to a campaign with the ED4 rulebook ingested, and a `--role` value, **When** the developer runs the eval command, **Then** each EvaluationRecord is written to the evaluation store with the question reference, generated response, retrieved context chunks, campaign_id, and role — but with no judge score fields yet.
2. **Given** EvaluationRecords written in the previous step, **When** the developer runs the judge command, **Then** each record is updated with `judge_faithfulness`, `judge_relevance`, `judge_context_utilization`, and `judge_aggregate` scores in [0, 1].
3. **Given** fully scored EvaluationRecords, **When** the developer views the summary report, **Then** it displays mean scores for all four judge fields alongside the existing MRR/nDCG/Recall@10 summary, with judge coverage clearly stated.
4. **Given** a scored record where the judge found partial faithfulness, **When** the developer inspects it, **Then** a `judge_rationale` field contains a natural language explanation for each dimension score.

---

### User Story 2 - Provider-Configurable Judge Model (Priority: P2)

A developer switches the judge LLM between a local Ollama model and a cloud provider (e.g., a Claude or OpenAI-compatible endpoint) by changing a single environment variable, without modifying any code.

**Why this priority**: Principle II (Provider Abstraction) is non-negotiable in this project, and local-first (Principle IV) means Ollama must work out of the box. Cloud judges offer higher judgment quality for occasional offline analysis but must remain optional.

**Independent Test**: Can be fully tested by running the judge evaluator against two identical inputs — once with `JUDGE_PROVIDER=ollama` pointing to a local model and once with `JUDGE_PROVIDER=claude` — and confirming both produce valid structured scores.

**Acceptance Scenarios**:

1. **Given** `JUDGE_PROVIDER=ollama` and a running Ollama instance, **When** the evaluator is invoked, **Then** it calls the local Ollama endpoint and returns valid scores without any cloud traffic.
2. **Given** `JUDGE_PROVIDER=claude` and a valid API key, **When** the evaluator is invoked, **Then** it calls the configured Claude endpoint and returns valid scores.
3. **Given** an unrecognised `JUDGE_PROVIDER` value, **When** the evaluator is initialised, **Then** it raises a clear configuration error naming the invalid value and listing supported providers.

---

### User Story 3 - Graceful Failure on Judge Unavailability (Priority: P3)

When the judge model is unavailable (network failure, model not loaded, rate-limit), the harness run continues to completion for all remaining questions, marks affected results as unscored, and reports how many questions were skipped at the end.

**Why this priority**: Harness runs can be long (hundreds of questions). A single judge timeout should not abort the entire run and discard all retrieval metrics already collected.

**Independent Test**: Can be fully tested by pointing `JUDGE_PROVIDER` at a nonexistent endpoint and running the evaluator against 3 questions; confirm all 3 results contain `judge_status: "error"` and a human-readable `judge_error` message, and that MRR/nDCG/Recall@10 are still populated for those rows.

**Acceptance Scenarios**:

1. **Given** a judge endpoint that is unreachable, **When** the evaluator processes a question, **Then** the result row contains `judge_status: "error"` and `judge_error` describing the failure, while all retrieval metric fields remain populated.
2. **Given** a judge that returns a response that is not valid JSON or does not match the expected score schema, **When** the evaluator processes the response, **Then** the result is marked `judge_status: "parse_error"` and the raw judge output is preserved in a `judge_raw_response` field for debugging.
3. **Given** a completed harness run where some questions were unscored, **When** the summary report is printed, **Then** it displays `Judge coverage: N/M questions scored (X%)` so the developer knows how complete the evaluation is.

---

### Edge Cases

- What happens when retrieved context is empty (retrieval returned zero chunks)? Faithfulness and context utilization scores are not meaningful; the judge must be instructed to mark these dimensions as N/A and score only answer relevance.
- What happens when the generated response is empty or a fallback message? The judge must detect this and return a zero score across all dimensions with a specific `judge_status: "no_response"` marker.
- What happens when context exceeds the judge model's context window? The system must truncate context to a configurable maximum token budget and log a warning; scores remain valid but are annotated with `judge_context_truncated: true`.
- What happens when judge scores are outside the [0, 1] range? The evaluator must clamp or reject out-of-range values and log a warning rather than propagating invalid data into benchmark results.
- What happens when a run identifier is provided to the judge command but no matching records exist in the store? The command must exit with a clear error naming the unknown run identifier rather than silently completing with zero records processed.
- What happens when the judge command is run against a store where all records are already scored? It must exit cleanly with a message stating that no unscored records were found, rather than silently completing with no output.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST evaluate generated responses along three dimensions: faithfulness (response claims are grounded in retrieved context), answer relevance (response addresses the question asked), and context utilization (response draws meaningfully from retrieved context rather than ignoring it).
- **FR-002**: Each dimension MUST be scored on a continuous scale from 0 (completely fails the criterion) to 1 (fully satisfies the criterion).
- **FR-003**: The evaluator MUST produce an aggregate score per response, computed as the equally-weighted mean of the three dimension scores.
- **FR-004**: The evaluator MUST produce a natural language rationale for each dimension score, explaining why that score was assigned, so developers can understand and audit judge decisions.
- **FR-005**: The judge LLM MUST be invoked through the existing provider abstraction layer (`packages/llm/`), configured via a `JUDGE_PROVIDER` environment variable with no hard-coded default provider.
- **FR-006**: The evaluator MUST support at least: Ollama (local, default for development), and the existing Claude abstraction (cloud, optional).
- **FR-007**: The judge prompt template MUST be stored in a configurable location (not hard-coded in business logic) so it can be modified without code changes. The template MUST instruct the judge LLM to return a JSON object containing per-dimension scores and rationales; the evaluator treats any non-JSON or schema-invalid response as a parse failure.
- **FR-008**: The system MUST persist generated responses and their judge outcomes in a dedicated evaluation record store (separate from `benchmark_results.jsonl`, which retains only retrieval metrics). Each record MUST include the question or gold-standard reference, the generated response, the retrieved context chunks used, and all judge outcome fields.
- **FR-009**: The evaluator MUST process questions sequentially (one at a time); no parallel or concurrent execution of judge calls is required or supported.
- **FR-010-a**: When the judge fails for a specific question (network error, timeout, parse failure), the system MUST record the failure in the result row and continue processing the next question in sequence.
- **FR-010-b**: When context exceeds the judge model's configured maximum token budget, the system MUST truncate context, annotate the result, and continue — not fail.
- **FR-011**: The main harness eval command MUST accept a required `--campaign-id` argument (campaign UUID) and a required `--role` argument (`"gm"` or `"player"`), and call the existing Knowledge Q&A pipeline (`ask_question()` in `apps/web/services/knowledge.py`) for each gold-standard question passing both values. The resulting (question, answer, context_chunks) MUST be written as an EvaluationRecord to the evaluation store — with the campaign_id and role recorded — without running the judge. A unique run identifier MUST be assigned to all records from that invocation. Judge scoring is a separate subsequent step.
- **FR-013**: A dedicated judge command MUST read EvaluationRecords from the evaluation store and write judge scores and rationales back to each processed record. The command MUST support scoping to a specific run identifier so that only records from that run are evaluated; when no run identifier is provided, all unscored records across all runs are processed. This is the primary and only mode of judge invocation.
- **FR-014**: By default, the judge command MUST skip EvaluationRecords that already have a completed judge status (i.e., `judge_status` is present and not `"error"` or `"parse_error"`). Re-scoring already-scored records MUST require an explicit opt-in (e.g., a flag or config setting); without it, those records are left unchanged.
- **FR-012**: The harness summary report MUST include judge coverage (questions scored vs. total), mean scores per dimension, and mean aggregate score alongside existing retrieval metrics.

### Key Entities

- **EvaluationRecord**: The persistent unit of evaluation data, stored in a dedicated evaluation store (format determined at planning). Contains: a run identifier (assigned by the eval command to group all records from a single run), the campaign UUID evaluated, the role used (`"gm"` or `"player"`), a question identifier or raw question text (or gold-standard reference when sourced from the benchmark dataset), the generated LLM response (not chunks), the retrieved context chunk texts used during generation, and the judge outcome fields. Lifecycle states: **unscored** (written by the eval command, no judge fields yet) → **scored** (judge fields populated successfully) or **error/parse_error** (judge attempted but failed). Records in an error state are retried on the next judge run; scored records are skipped unless overwrite is explicitly requested.
- **DimensionScore**: A (score: float[0,1], rationale: str) pair for one evaluation dimension.
- **JudgeResult**: The complete judge output for one EvaluationRecord — three DimensionScores, an aggregate score, a status, and an optional error or raw-response field.
- **JudgePromptTemplate**: The configurable prompt structure sent to the judge LLM. Defines how question, context, and response are presented, and instructs the judge to return a JSON object with per-dimension scores (float [0,1]) and rationale strings.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Each evaluated response receives scores in all three defined dimensions within 60 seconds per question on a local Ollama judge.
- **SC-002**: Judge dimension scores are internally consistent: a response that receives a high faithfulness score does not simultaneously contain claims unsupported by the provided context, as verified by manual spot-check of at least 10 sample results.
- **SC-003**: After running the eval command followed by the judge command over the existing ED4 benchmark dataset (≥100 questions), a summary report includes both retrieval metrics (MRR, nDCG, Recall@10) and response quality scores (mean faithfulness, relevance, context utilization, aggregate) in a single output.
- **SC-004**: The system operates fully offline using a locally hosted Ollama judge model with no cloud dependencies required.
- **SC-005**: Switching the judge provider from Ollama to Claude requires only changing environment variables — zero code modifications.
- **SC-006**: When any judge call fails, the harness run continues and completes; the final result file contains a valid entry for every question regardless of judge status.
- **SC-007**: Re-running the judge-only eval step against a previously generated results file produces scores that differ by less than 0.1 per dimension on average from the first run (consistency check across repeated invocations with the same model).

## Clarifications

### Session 2026-06-28

- Q: Should the judge evaluator process questions sequentially or in parallel? → A: Sequential only — one question at a time.
- Q: How does the judge communicate scores back — JSON output or natural language parsing? → A: Judge is prompted to return a JSON object directly; parser validates the JSON structure.
- Q: For standalone re-scoring, where does the evaluator read responses from? → A: `benchmark_results.jsonl` stores retrieval metrics only, not generated answers. A new dedicated evaluation record store (file or collection) must be built to persist the generated answer and question (or gold-standard reference) alongside judge scores.
- Q: Does the judge run inline with the main eval command or as a dedicated separate command? → A: Dedicated separate command — the main eval command writes EvaluationRecords (without judge scores); the judge command reads them and adds scores independently.
- Q: When the judge command is re-run on already-scored records, should it skip, overwrite, or version? → A: Skip already-scored records by default; overwriting requires explicit opt-in.
- Q: Does the judge command always score all unscored records, or can it be scoped to a specific run? → A: Can be scoped to a specific run identifier; useful when comparing pipeline configurations across runs.
- Q: Which pipeline generates the answers being evaluated? → A: The existing `ask_question()` function in `apps/web/services/knowledge.py` — the same pipeline used in the Knowledge Q&A Gradio tab (retrieval via `ChromaKnowledgeRetriever` + LLM synthesis via `OllamaProvider`, returns `(answer_text, list[KnowledgeChunk])`). The eval_runner calls it directly; no new generation component is required.
- Q: How does eval_runner identify the campaign to evaluate against when calling `ask_question()`? → A: Via a `--campaign-id` CLI argument — developer supplies the UUID of the campaign that has the target rulebook ingested.
- Q: What role should eval_runner use when calling `ask_question()`? → A: Configurable via a `--role` CLI argument (`"gm"` or `"player"`), so player-facing and GM-facing quality can be measured separately.

## Assumptions

- The generation step is the existing `ask_question()` function in `apps/web/services/knowledge.py`, which performs the full Knowledge Q&A pipeline (multi-query expansion, vector retrieval, RRF ranking, LLM synthesis) and returns `(answer_text, list[KnowledgeChunk])`. The eval_runner calls this function directly — no new generation component is built. The env vars that govern the pipeline (`KNOWLEDGE_LLM_MODEL`, `KNOWLEDGE_EMBED_MODEL`, `KNOWLEDGE_ENRICH_MODEL`, etc.) remain unchanged.
- The judge LLM is a chat-capable model (instruction-following), not a specialized scoring model; the quality of scores depends on model capability.
- Evaluation is batch and offline — judge scoring is not part of the real-time RAG query path in the Gradio UI; it runs exclusively in the harness.
- `benchmark_results.jsonl` stores retrieval metrics only (MRR/nDCG/Recall@10); it does not contain generated responses. A new dedicated evaluation record store must be introduced to hold generated responses and judge scores — its concrete format (JSONL, SQLite table, or other) is a planning-phase decision.
- Prompt iteration on the judge template is expected; the spec does not fix the exact prompt wording, only the structure of what information is passed to the judge.
- Concurrent or parallel judge execution is explicitly out of scope; sequential processing is the only required mode.
- The three evaluation dimensions (faithfulness, answer relevance, context utilization) are sufficient for the current eval goals; domain-specific dimensions (e.g., Earthdawn rules accuracy) are out of scope for this feature and may be addressed in a follow-on spec.
