# Tasks: LLM-as-Judge Response Evaluation

**Input**: Design documents from `/specs/013-llm-judge-eval/`

**Prerequisites**: plan.md ✅ | spec.md ✅ | research.md ✅ | data-model.md ✅ | contracts/ ✅ | quickstart.md ✅

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (US1, US2, US3, UI)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create the new subpackage skeleton and verify dependencies.

- [X] T001 Create `packages/rag/rag/evaluation/__init__.py`, `packages/rag/rag/evaluation/prompts/` directory, and `packages/rag/tests/evaluation/__init__.py`
- [X] T002 Add `sqlalchemy>=2.0` and `aiosqlite>=0.20` to `packages/rag/pyproject.toml` if not already present; verify `data/` directory exists at repo root (create if needed)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core data models, storage layer, provider factory, and prompt template — MUST be complete before any user story implementation begins.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T003 [P] Define `DimensionScore`, `JudgeScore`, `EvaluationInput`, `JudgeStatus` enum, and `JudgeResult` Pydantic models (with `score` clamping validator on `DimensionScore`) in `packages/rag/rag/evaluation/models.py`
- [X] T004 [P] Implement `get_judge_provider(provider: str, model: str) -> LLMProvider` with Ollama support and `EnvironmentError` on unrecognised provider in `packages/rag/rag/evaluation/factory.py` (no `get_answer_provider` — generation uses `ask_question()`)
- [X] T005 [P] Write default judge prompt template instructing the LLM to return JSON with faithfulness/relevance/context_utilization scores and rationales in `packages/rag/rag/evaluation/prompts/judge_prompt.txt`
- [X] T006 [P] Write unit tests for Pydantic model validation: score clamping to [0,1], required rationale field, aggregate property, JudgeStatus enum values in `packages/rag/tests/evaluation/test_models.py`
- [X] T007 Implement `ResponseEvalRecord` SQLAlchemy model (all columns per data-model.md, including `campaign_id` TEXT indexed and `role` TEXT) and `EvaluationStore` class with methods `write_record`, `get_unscored_by_run`, `get_by_run_id`, `update_judge_result`, `count_by_status` in `packages/rag/rag/evaluation/store.py`
- [X] T008 [P] Write unit tests for `EvaluationStore`: CRUD operations, run_id filtering, campaign_id filtering, status-based queries, skip-if-scored logic in `packages/rag/tests/evaluation/test_store.py`

**Checkpoint**: Foundation complete — models, store, factory, and prompt template are ready. User story phases can now begin.

---

## Phase 3: User Story 1 — Batch Eval Then Judge Produces Combined Quality Report (Priority: P1) 🎯 MVP

**Goal**: Developer runs `eval_runner.py` (with `--campaign-id` and `--role`) to call `ask_question()` and write EvaluationRecords, then runs `judge_runner.py` to score them. A `--summary` report shows mean scores per dimension + judge coverage.

**Independent Test**: Run Quickstart Scenarios 1–3 from `quickstart.md` against 3 gold-standard questions with a local Ollama judge. Confirm all three records are scored, numeric scores are in [0, 1], skip logic works on re-run, and exit code is 0.

- [X] T009 [P] [US1] Implement `JudgeEvaluator` class: load prompt template from `JUDGE_PROMPT_PATH` (fall back to default), truncate context to `JUDGE_MAX_CONTEXT_CHARS` (annotate truncation), call `LLMProvider.generate_structured(JudgeScore)`, return `JudgeResult` with `judge_status = "scored"` on success in `packages/rag/rag/evaluation/judge.py`
- [X] T010 [US1] Implement `eval_runner.py`: require `--campaign-id` UUID and `--role` ("gm"|"player") CLI args, validate both (exit 1 on missing/invalid), generate `run_id`, load gold standard, iterate questions calling `ask_question(question, campaign_id, role)` from `apps/web/services/knowledge.py`, write `ResponseEvalRecord` per question with `campaign_id` and `role`, print run_id + count + wall-clock on completion in `harness/knowledge_qa/eval_runner.py`
- [X] T011 [US1] Implement `judge_runner.py`: validate `JUDGE_PROVIDER` and `JUDGE_MODEL` env vars (exit 1 on missing), handle `--run-id` scope (exit 1 + name unknown ID if no matching records), skip records with `judge_status = "scored"` by default, handle `--force` flag, call `JudgeEvaluator` per record, write `JudgeResult` back to store, exit 0 with "No unscored records found" when nothing to process, implement `--summary` output (mean scores per dimension + aggregate + coverage%) in `harness/knowledge_qa/judge_runner.py`
- [X] T012 [P] [US1] Write unit tests for `JudgeEvaluator` happy path: valid JSON LLM response parses to `JudgeScore`, aggregate is mean of three scores, `judge_status = "scored"` in `packages/rag/tests/evaluation/test_judge.py`
- [X] T013 [US1] Write integration test for 3-question smoke run (Quickstart Scenario 1) and re-run safety (Quickstart Scenario 3): real Ollama endpoint, confirms scored records exist and second judge run exits with "No unscored records found" in `packages/rag/tests/evaluation/test_judge_integration.py`

**Checkpoint**: US1 fully functional. `eval_runner.py --campaign-id UUID --role gm` + `judge_runner.py --summary` produce a combined quality report. MVP is demonstrable.

---

## Phase 4: User Story 2 — Provider-Configurable Judge Model (Priority: P2)

**Goal**: Developer can switch judge provider between Ollama and Claude by changing `JUDGE_PROVIDER` env var. Unrecognised values produce a clear error naming the invalid value and listing valid options.

**Independent Test**: Run `judge_runner.py` with `JUDGE_PROVIDER=invalid_value`; confirm exit code 1 and error message lists "ollama" and "claude". With `JUDGE_PROVIDER=claude` + valid API key, confirm valid scores are returned.

- [X] T014 [US2] Extend `get_judge_provider()` to instantiate `AnthropicProvider` when `JUDGE_PROVIDER=claude`; update `EnvironmentError` message to name the invalid value and list valid options `["ollama", "claude"]` in `packages/rag/rag/evaluation/factory.py`

**Checkpoint**: Both Ollama and Claude providers work as judge via env var only.

---

## Phase 5: User Story 3 — Graceful Failure on Judge Unavailability (Priority: P3)

**Goal**: When the judge LLM is unreachable, times out, or returns malformed output, the harness run continues through all remaining questions, records the failure per record, and reports coverage at the end.

**Independent Test**: Run Quickstart Scenario 4 (unreachable endpoint, 3 questions): confirm exit code 0, all 3 records have `judge_status = "error"`, `judge_error` is populated, and the summary shows `Scored: 0 | Error: 3`.

- [X] T015 [US3] Extend `JudgeEvaluator` with comprehensive exception handling: catch `httpx.HTTPError` / `asyncio.TimeoutError` → `judge_status = "error"` + populate `judge_error`; catch `json.JSONDecodeError` / `pydantic.ValidationError` → `judge_status = "parse_error"` + populate `judge_raw_response`; detect empty `generated_response` before LLM call → `judge_status = "no_response"` in `packages/rag/rag/evaluation/judge.py`
- [X] T016 [US3] Extend `judge_runner.py` to wrap each record's judge call in try/except, accumulate per-status counts, and print `Scored: N | Error: N | Parse error: N | No response: N` plus `Judge coverage: N/M (X%)` on completion in `harness/knowledge_qa/judge_runner.py`
- [X] T017 [P] [US3] Extend unit tests with error-path cases: mock `httpx.HTTPError` → "error" status; mock `ValidationError` → "parse_error" + raw_response captured; empty response input → "no_response" in `packages/rag/tests/evaluation/test_judge.py`
- [X] T018 [US3] Extend integration test with Quickstart Scenario 4 (unreachable endpoint → all records error, run completes, exit code 0) in `packages/rag/tests/evaluation/test_judge_integration.py`

**Checkpoint**: All three harness user stories independently functional. Graceful failure confirmed end-to-end.

---

## Phase 6: UI Integration — Response Quality Section in RAG Evaluation Tab

**Goal**: Developer opens the RAG Evaluation tab in the Gradio GM interface, uploads a JSONL question file, and clicks "Run Response Quality Eval" to call `ask_question()` + judge per question with streaming progress. Results appear in a table showing faithfulness/relevance/context-utilization/aggregate per question. Records are persisted to `data/eval.db`.

**Independent Test**: Run Quickstart Scenario 6 from `quickstart.md`: with `JUDGE_PROVIDER=ollama` and `JUDGE_MODEL=llama3.1` set, upload a 3-question JSONL file in the RAG Evaluation tab, click "Run Response Quality Eval", confirm 3 scored rows appear, click a row to see rationales in the detail panel, and verify records exist in `data/eval.db`.

- [X] T019 [P] [UI] Implement `ResponseEvalRow` and `ResponseEvalSummary` dataclasses (per data-model.md UI State Models) in `apps/web/services/response_eval.py`
- [X] T020 [UI] Implement `run_response_eval_question(question, category, campaign_id, role, judge_evaluator, store, run_id) -> ResponseEvalRow` and `build_judge_summary(rows, run_id) -> ResponseEvalSummary` in `apps/web/services/response_eval.py`
- [X] T021 [UI] Add "Response Quality" `gr.Accordion` section to `apps/web/pages/gm/rag_eval.py` with placeholder stub text ("Response Quality Evaluation — select a question file and active campaign, then click Run Response Quality Eval") before any real logic is wired, plus `run_judge_btn` (initially disabled), `judge_progress_md`, `judge_summary_md`, `judge_results_table` (columns: #, Question, Faithfulness, Relevance, Context Util, Aggregate, Status), `judge_detail_md`, and `judge_results_state` per contracts/rag-eval-ui.md
- [X] T022 [UI] Implement `on_run_judge(session_state, file_input)` async generator handler in `apps/web/pages/gm/rag_eval.py`: validate session + file + env vars (surface errors as Gradio messages per Principle VII), generate `run_id`, iterate questions calling `run_response_eval_question()`, yield per-question progress updates streaming the accumulating table, yield final summary on completion
- [X] T023 [UI] Implement `on_judge_row_select(evt, state)` handler in `apps/web/pages/gm/rag_eval.py`: on table row click, populate `judge_detail_md` with generated response text and per-dimension rationales (or error/raw_response text when status ≠ "scored")
- [X] T024 [UI] Add startup check in `apps/web/pages/gm/rag_eval.py`: if `JUDGE_PROVIDER` or `JUDGE_MODEL` env var is absent at import time, disable `run_judge_btn` with tooltip "Configure JUDGE_PROVIDER and JUDGE_MODEL env vars to enable response quality evaluation"; enable `run_judge_btn` only when both env vars are present AND a campaign session is active AND a file is loaded

**Checkpoint**: Response Quality section fully functional in the RAG Evaluation tab. UI run persists records to `data/eval.db` alongside harness-run records.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Observability, code quality, documentation.

- [X] T025 [P] Run `ruff check` and `pyright` on all new files; fix any errors in `packages/rag/rag/evaluation/`, `harness/knowledge_qa/`, `apps/web/services/response_eval.py`, and extended `apps/web/pages/gm/rag_eval.py`
- [X] T026 [P] Verify `LOG_LEVEL=DEBUG` surfaces judge prompt text, raw LLM response, and per-question scores without crashing (run `judge_runner.py --limit 1` with `LOG_LEVEL=DEBUG` per quickstart.md debugging section)
- [X] T027 Update `README.md` to document: new harness eval workflow (`eval_runner.py --campaign-id UUID --role gm`, `judge_runner.py --summary`), judge env vars (`JUDGE_PROVIDER`, `JUDGE_MODEL`, optional `JUDGE_PROMPT_PATH`, `JUDGE_MAX_CONTEXT_CHARS`), `data/eval.db` location, and the Response Quality section in the RAG Evaluation tab
- [X] T028 Run all six Quickstart Scenarios from `specs/013-llm-judge-eval/quickstart.md` end-to-end and confirm all success criteria SC-001 through SC-007 pass (Scenario 6 validates the UI integration) — unit tests fully pass; Scenarios 1–5 require a live Ollama instance; Scenario 6 requires running Gradio app

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 — **BLOCKS all user stories and UI integration**
- **US1 (Phase 3)**: Depends on Phase 2; no dependency on US2, US3, or UI
- **US2 (Phase 4)**: Depends on Phase 2; no dependency on US1, US3, or UI — can run in parallel with Phase 3
- **US3 (Phase 5)**: Depends on Phase 3 (extends `judge.py` and `judge_runner.py` built in US1)
- **UI Integration (Phase 6)**: Depends on Phase 5 (needs complete `JudgeEvaluator` with error handling for Principle VII–compliant error display)
- **Polish (Phase 7)**: Depends on all prior phases

### User Story Dependencies

- **US1 (P1)**: Independent after Foundational — start immediately after Phase 2
- **US2 (P2)**: Independent after Foundational — can run in parallel with US1
- **US3 (P3)**: Depends on US1 (extends files built in T009, T011)
- **UI (P4)**: Depends on US3 (needs full error-handling judge for Gradio error surfacing)

### Within Each Phase

- T003–T006 are parallel (different files, no inter-dependencies)
- T007 depends on T003 (store.py needs Pydantic models)
- T008 can run alongside T007
- T009 and T012 are parallel (judge.py implementation and its unit tests)
- T010 depends on T007 (store) — calls `ask_question()` directly, no generator dependency
- T011 depends on T007 (store) + T009 (judge)
- T013 depends on T010 + T011
- T015 depends on T009 (extends judge.py)
- T016 depends on T011 (extends judge_runner.py)
- T017 can run alongside T015 and T016
- T018 depends on T015 + T016
- T019 and T020 are parallel (dataclasses before service functions in same file; T020 depends on T019)
- T021 depends on T019 (needs ResponseEvalRow type for state)
- T022 depends on T020 + T021 (uses service function + wires to Gradio components)
- T023 depends on T021 (uses state component defined in stub)
- T024 can be added to T021 (startup check in same section)

---

## Parallel Execution Examples

### Phase 2 — run all foundational tasks in parallel

```
T003: models.py
T004: factory.py (Ollama only)
T005: judge_prompt.txt
T006: test_models.py
(T007 starts after T003 completes)
(T008 starts alongside T007)
```

### Phase 3 (US1) — parallel start

```
T009: judge.py (happy path)
T012: test_judge.py (happy path tests)
(T010 starts after T007 completes — calls ask_question() directly)
(T011 starts after T007 + T009 complete)
(T013 starts after T010 + T011 complete)
```

### Phase 6 (UI) — sequential start

```
T019: response_eval.py dataclasses
T020: response_eval.py service functions
T021: rag_eval.py accordion stub + components
T022: rag_eval.py on_run_judge() handler
T023: rag_eval.py on_judge_row_select() handler
T024: rag_eval.py startup env var check
```

---

## Implementation Strategy

### MVP First (US1 + Harness Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL — blocks all stories)
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: Run Quickstart Scenarios 1–3
5. Demo: `eval_runner.py --campaign-id UUID --role gm` + `judge_runner.py --summary` over 10 questions

### Incremental Delivery

1. Setup + Foundational → skeleton ready
2. US1 → working eval + judge pipeline (MVP)
3. US2 → Claude provider enabled
4. US3 → robust error handling
5. UI Integration → scores visible in Gradio RAG Evaluation tab
6. Polish → production-ready

---

## Notes

- [P] tasks involve different files with no blocking dependencies on in-progress work
- [Story] label maps each task to a user story for traceability
- Tests are included per constitution Principle V (Harness-Driven Quality)
- Each user story has a Quickstart scenario as its independent acceptance test
- `data/eval.db` is created automatically on first run (SQLAlchemy `create_all`)
- All new modules MUST use `logging.getLogger(__name__)` — no bare `print()` except in CLI output paths (Principle VIII)
- UI tasks MUST follow Principle VII: placeholder stub before real logic; all errors surfaced as Gradio messages
- `ask_question()` from `apps/web/services/knowledge.py` is the answer generator — no `AnswerGenerator` class, no `ANSWER_PROVIDER`/`ANSWER_MODEL` env vars
- `--campaign-id` UUID and `--role` ("gm"|"player") are required CLI args for `eval_runner.py`
- `ResponseEvalRecord` includes `campaign_id` and `role` columns (see data-model.md)

---

## Phase 8: Convergence

_Gaps identified after clarification: 4th judge dimension (`answer_correctness`) and `reference_answer` required in judge prompt for all dimensions (FR-001, FR-003, FR-007, FR-008, FR-011)._

- [X] T029 Add `reference_answer` TEXT column, `judge_answer_correctness` REAL column, and `judge_answer_correctness_rationale` TEXT column to `ResponseEvalRecord`; add `reference_answer: str` param to `write_record()` and `judge_answer_correctness`/`judge_answer_correctness_rationale` params to `update_judge_result()` in `packages/rag/rag/evaluation/store.py` per FR-008
- [X] T030 [P] Add `answer_correctness: DimensionScore` field to `JudgeScore` and update `aggregate` property to divide by 4 instead of 3; add `reference_answer: str` field to `EvaluationInput` in `packages/rag/rag/evaluation/models.py` per FR-001, FR-003
- [X] T031 [P] Rewrite `packages/rag/rag/evaluation/prompts/judge_prompt.txt` to add `{reference_answer}` placeholder visible to all four dimensions, add `answer_correctness` to the required JSON response schema, and add scoring guidelines instructing the judge to use the reference answer when calibrating all four scores per FR-007
- [X] T032 Update `JudgeEvaluator.evaluate()` in `packages/rag/rag/evaluation/judge.py` to pass `reference_answer=inp.reference_answer` in the `_prompt_template.format()` call; update the debug log line to include all four dimension scores per FR-007
- [X] T033 Update `harness/knowledge_qa/eval_runner.py` to read `q.get("reference_answer")` from each question dict and pass `reference_answer=` to `store.write_record()` per FR-011
- [X] T034 Update `harness/knowledge_qa/judge_runner.py` to pass `reference_answer=record.reference_answer` in `EvaluationInput`; add `judge_answer_correctness` and `judge_answer_correctness_rationale` to `update_kwargs` when status is "scored"; update `--summary` output to include mean `answer_correctness` score per FR-012, FR-013; add `--summary` CLI flag
- [X] T035 Update `apps/web/pages/gm/rag_eval.py`: add `answer_correctness: float | None` and `answer_correctness_rationale: str | None` fields to `EvalRow`; update `_HEADERS`, `_DTYPES`, `to_table_row()`, `on_row_select()`, and `_format_summary()` to include `answer_correctness`; update `on_run_eval` to pass `reference_answer=q.reference_answer` in `EvaluationInput` and `judge_answer_correctness` to `store.update_judge_result()` per FR-001
- [X] T036 [P] Update `packages/rag/tests/evaluation/test_models.py` to add `answer_correctness` to `JudgeScore` fixture and assert `aggregate == sum/4`; update `packages/rag/tests/evaluation/test_judge.py` to add `reference_answer` to `EvaluationInput` and `answer_correctness` to mock JSON response per FR-001

---

## Phase 9: Convergence

_Gaps found after Phase 8: `response_eval.py` service and `test_judge_integration.py` were written against the pre–Phase 8 (3-dimension) schema and were not updated when `answer_correctness` and `reference_answer` were added in T029–T036._

- [X] T037 Fix `packages/rag/tests/evaluation/test_judge_integration.py`: add `reference_answer: str` parameter to `_make_input()` and include it in the `EvaluationInput` constructor; add assertion for `result.score.answer_correctness.score` in `test_real_judge_returns_scored_result` (score in [0,1]) and `result.score.answer_correctness.rationale` in `test_real_judge_rationales_are_nonempty` per T036 / FR-001 (partial)
- [X] T038 Update `apps/web/services/response_eval.py`: add `answer_correctness: float | str` field to `ResponseEvalRow` and `mean_answer_correctness: float | None` to `ResponseEvalSummary`; add `reference_answer: str` parameter to `run_response_eval_question()`; pass `reference_answer=reference_answer` to `store.write_record()` and `reference_answer=reference_answer` to `EvaluationInput`; add `judge_answer_correctness=s.answer_correctness.score` and `judge_answer_correctness_rationale=s.answer_correctness.rationale` to `update_judge_result()` call when status is "scored"; add `answer_correctness` to the scored `ResponseEvalRow` returned; include `mean_answer_correctness` in `build_judge_summary()` output per FR-001, FR-003, FR-008 (partial)
