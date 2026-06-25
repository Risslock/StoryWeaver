---

description: "Task list for RAG Evaluation Tab & Q&A Source Visibility"
---

# Tasks: RAG Evaluation Tab & Q&A Source Visibility

**Input**: Design documents from `/specs/006-rag-eval-qa-ux/`

**Prerequisites**: plan.md ✅ | spec.md ✅ | research.md ✅ | data-model.md ✅ | contracts/evaluator_api.md ✅

**Tests**: Harness unit + integration tests included (metric functions are pure and critical to correctness).

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Exact file paths included in every task

---

## Phase 1: Setup

**Purpose**: No new project or package needed — extending existing workspace.

- [X] T001 Confirm `packages/rag/rag/knowledge/` and `apps/web/services/` exist and are importable (smoke check before writing new files)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The `TestQuestion` model/loader and the metric functions in `evaluator.py` are shared
by the evaluation service and all harness tests. Both user stories US1 and US2 depend on them.

**⚠️ CRITICAL**: No user story work can begin until T002–T005 are complete.

- [X] T002 [P] Create `TestQuestion` Pydantic model and `load_test_questions(file_path: str) -> list[TestQuestion]` in `packages/rag/rag/knowledge/test_questions.py`. Model fields: `question: str`, `keywords: list[str]`, `reference_answer: str`, `category: str`. Loader reads JSONL line-by-line; raises `ValueError("Row N: missing field '<field>'")` for missing required fields; propagates `json.JSONDecodeError`; returns `[]` for empty file.

- [X] T003 [P] Create `RetrievalEvalResult` and `EvalSummary` Pydantic models in `packages/rag/rag/knowledge/evaluator.py`. `RetrievalEvalResult` fields: `question: str`, `category: str`, `mrr: float`, `ndcg: float`, `recall_at_k: float`, `keywords_found: int`, `total_keywords: int`, `k: int`, `retrieved_chunks: list[KnowledgeChunk]`, `keyword_ranks: dict[str, int | None]`. `EvalSummary` fields: `mean_mrr: float`, `mean_ndcg: float`, `mean_recall_at_k: float`, `total_questions: int`, `k: int`.

- [X] T004 Implement `calculate_mrr(keyword: str, chunks: list[KnowledgeChunk]) -> float`, `calculate_ndcg(keyword: str, chunks: list[KnowledgeChunk], k: int) -> float`, and `calculate_recall_at_k(keyword: str, chunks: list[KnowledgeChunk], k: int) -> float` in `packages/rag/rag/knowledge/evaluator.py`. All use case-insensitive substring match on `chunk.text`. MRR returns `1/rank` of first match or `0.0`. nDCG uses binary relevance with `log2(i+2)` discount; returns `0.0` when IDCG is 0. Recall@k returns `1.0` if keyword found in any of `chunks[:k]`, else `0.0`. Handles `k > len(chunks)` gracefully. (Depends on T003)

- [X] T005 Implement `evaluate_question(test: TestQuestion, chunks: list[KnowledgeChunk], k: int) -> RetrievalEvalResult` and `aggregate_results(results: list[RetrievalEvalResult]) -> EvalSummary` in `packages/rag/rag/knowledge/evaluator.py`. `evaluate_question` computes mean MRR/nDCG/Recall@k across all keywords and builds `keyword_ranks` dict. `aggregate_results` returns zero-valued `EvalSummary` for empty input. (Depends on T004)

**Checkpoint**: Foundational complete — metric functions and models ready. US1, US2, and harness tests can now begin.

---

## Phase 3: User Story 1 — GM Runs RAG Retrieval Evaluation (Priority: P1) 🎯 MVP

**Goal**: GM loads a JSONL test file, runs evaluation, and sees per-question MRR/nDCG/Recall@k
with a live progress counter and aggregate summary.

**Independent Test**: Upload `harness/knowledge_qa/tests.jsonl`, click Run Evaluation with k=10,
verify row count matches JSONL lines and all metrics are floats ∈ [0, 1].

### Harness Tests for US1

- [X] T006 [P] [US1] Write unit tests for `calculate_mrr`, `calculate_ndcg`, `calculate_recall_at_k`, `evaluate_question`, `aggregate_results` in `harness/knowledge_qa/test_evaluator.py`. Cover: empty chunks (→ 0.0), keyword found at rank 1 (MRR=1.0), keyword not found (→ 0.0), k larger than chunk count (no crash), empty keywords list (→ 0.0 for all metrics), aggregate of empty list (→ zero EvalSummary).

- [X] T007 [P] [US1] Write integration tests for `run_evaluation()` in `harness/knowledge_qa/test_eval_service.py`. Use a real (or fixture-backed) ChromaDB instance. Verify: result count matches input question count; `EvalSummary.total_questions` correct; `ProviderUnavailableError` propagated; malformed JSONL raises `ValueError`.

### Implementation for US1

- [X] T008 [US1] Implement `async run_evaluation(file_path: str, campaign_id: uuid.UUID, k: int) -> tuple[list[RetrievalEvalResult], EvalSummary]` in `apps/web/services/eval.py`. Calls `load_test_questions(file_path)`, then for each question calls `ChromaKnowledgeRetriever().search(query=q.question, campaign_id=str(campaign_id).replace("-",""), role="gm", top_k=k)`, then `evaluate_question(q, chunks, k)`. Logs run start/end at `INFO` via `logging.getLogger(__name__)`; logs per-question errors at `ERROR` and scores 0.0 for that question rather than aborting. Calls `aggregate_results()` and returns `(results, summary)`. (Depends on T002, T005)

- [X] T009 [US1] Build `build_rag_eval_page(session_state: gr.State) -> None` scaffold in `apps/web/pages/gm/rag_eval.py` (call inside `gr.Tab("RAG Evaluation")`). Components: `gr.File(file_types=[".jsonl"])` for test file upload; `gr.Slider(minimum=1, maximum=20, value=10, step=1, label="k")` for retrieval depth; `gr.Button("Run Evaluation", variant="primary", interactive=False)`; placeholder `gr.Markdown("Load a JSONL file to begin evaluation.")` (visible when no file loaded, hidden after file chosen); `gr.Markdown("")` for live progress text; `gr.Markdown("")` for aggregate summary; `gr.Dataframe(headers=["#","Question","Category","MRR","nDCG","Recall@k","Found/Total"], interactive=False)` for per-question results; `gr.Markdown("")` for drill-down detail panel. (Depends on T008)

- [X] T010 [US1] Implement `on_file_change`, `on_run_eval` event handlers in `apps/web/pages/gm/rag_eval.py` and wire all components. `on_file_change` enables the Run button and hides the placeholder when a file is selected. `on_run_eval` is a generator function that: (1) calls `run_evaluation()` question-by-question using an async loop with `gr.Progress` or by yielding progress markdown after each question (e.g., "Evaluating question 3 / 50…"); (2) accumulates `RetrievalEvalResult` objects; (3) on completion yields the filled dataframe rows and formatted aggregate summary markdown. Stores full results list in `eval_results_state`. Clears results on `session_state.change`. (Depends on T009)

- [X] T011 [US1] Register `build_rag_eval_page(session_state)` inside the `gm_col` tabs block in `apps/web/app.py`, importing from `pages.gm.rag_eval`. Add the import at the top of `app.py` alongside the other GM page imports. (Depends on T010)

**Checkpoint**: At this point, US1 is fully functional — GM can load a JSONL file, run evaluation, and see live progress + per-question results table + aggregate metrics.

---

## Phase 4: User Story 2 — GM Inspects Single Question Detail (Priority: P2)

**Goal**: GM clicks a row in the results table to see the retrieved chunk excerpts and
per-keyword rank breakdown for that question.

**Independent Test**: After running evaluation, click any row; verify the detail panel shows
retrieved chunk titles + excerpts and a keyword → rank mapping (or "not found").

### Implementation for US2

- [X] T012 [US2] Wire `gr.Dataframe.select()` event in `apps/web/pages/gm/rag_eval.py` to an `on_row_select(evt: gr.SelectData, results: list[RetrievalEvalResult]) -> str` handler. The handler reads `results[evt.index[0]]`, formats the drill-down markdown: section header with question text; keyword rank table (`keyword | rank` or `keyword | not found`); then up to `k` retrieved chunk excerpts (`**doc_title — headline** (topic)\n> text[:300]…`). Returns the formatted markdown to the detail panel `gr.Markdown`. Updates `selected_idx_state`. (Depends on T011)

**Checkpoint**: US1 and US2 are both independently functional. GM can run full evaluation and drill into any question's detail.

---

## Phase 5: User Story 3 — Q&A Tab Sources Separated (Priority: P3)

**Goal**: Both GM and player Q&A chatbots show the LLM answer without inline citations.
A collapsed "Show sources" accordion below reveals cited chunks on demand.

**Independent Test**: Submit a question; verify chatbot message contains no "**Sources:**" block;
expand accordion; verify chunk excerpts appear; collapse; verify they disappear.

### Implementation for US3

- [X] T013 [P] [US3] Modify `on_ask()` in `apps/web/pages/gm/knowledge_qa.py`: (1) Remove the citation suffix block (lines that build `citation_lines` and append to `full`); (2) Instead, format citations as a separate markdown string (same `doc_title — headline / topic / excerpt` format); (3) Change `on_ask` return signature to `(history, "", citations_md)` — three outputs. Add `sources_md = gr.Markdown("", elem_id="gm-knowledge-sources")` inside a `gr.Accordion("Show sources", open=False)` placed below the chatbot. Wire the third output of `ask_btn.click` and `ask_input.submit` to `sources_md`. Clear `sources_md` on `session_state.change`. When no chunks are returned, set `citations_md = ""` so the accordion is empty.

- [X] T014 [P] [US3] Apply the identical sources accordion pattern to `apps/web/pages/player/knowledge_qa.py`: remove any inline citation suffix from the player `on_ask()` handler; add `gr.Accordion("Show sources", open=False)` containing `gr.Markdown("", elem_id="player-knowledge-sources")`; wire the citations output; clear on session change. (Read the player file first to locate the equivalent `on_ask` implementation before editing.)

**Checkpoint**: All three user stories are independently functional. Q&A on both GM and player dashboards shows clean answers with sources on demand.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Verification, logging audit, and documentation.

- [X] T015 [P] Verify `LOG_LEVEL=DEBUG` surfaces expected log lines from `apps/web/services/eval.py` (run start, per-question, run end) without crashing. Confirm no bare `print()` statements in any new or modified file.

- [X] T016 [P] Run `uv run pytest harness/knowledge_qa/test_evaluator.py harness/knowledge_qa/test_eval_service.py -v` and confirm all tests pass.

- [X] T017 Run `uv run ruff check packages/rag/rag/knowledge/evaluator.py packages/rag/rag/knowledge/test_questions.py apps/web/services/eval.py apps/web/pages/gm/rag_eval.py` and fix any lint errors.

- [X] T018 Run `uv run pyright packages/rag/rag/knowledge/evaluator.py packages/rag/rag/knowledge/test_questions.py apps/web/services/eval.py apps/web/pages/gm/rag_eval.py` and resolve type errors.

- [X] T019 Run the full application (`uv run uvicorn apps.web.main:app --reload`), sign in as GM, and validate all five quickstart scenarios from `specs/006-rag-eval-qa-ux/quickstart.md`.

- [X] T020 Update `README.md` to reflect: new GM-only RAG Evaluation tab, `LOG_LEVEL` env var usage, and the updated Q&A tab behaviour (sources accordion). Remove any description of inline citation format.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — immediate
- **Foundational (Phase 2)**: Depends on Phase 1 — **blocks all user stories**
- **US1 (Phase 3)**: Depends on Foundational (T002, T005)
- **US2 (Phase 4)**: Depends on US1 completion (T011) — drill-down extends the eval tab
- **US3 (Phase 5)**: Depends only on Foundational (can start in parallel with US1 after T001)
- **Polish (Phase 6)**: Depends on all user stories complete

### User Story Dependencies

- **US1 (P1)**: Starts after Foundational — no dependency on US2 or US3
- **US2 (P2)**: Starts after US1 (extends the same Gradio tab page)
- **US3 (P3)**: Starts after Foundational — **independent of US1/US2** (different files)

### Within Each Phase

- T002 and T003 are parallel (different files)
- T004 depends on T003; T005 depends on T004
- T006 and T007 (harness tests) are parallel and can start immediately after T005
- T013 and T014 are parallel (different files)

### Parallel Opportunities

```bash
# Foundational — run in parallel:
Task: T002  # test_questions.py
Task: T003  # evaluator.py models

# US1 harness tests — run in parallel once T005 done:
Task: T006  # test_evaluator.py
Task: T007  # test_eval_service.py

# US3 — run in parallel once Foundational done:
Task: T013  # gm/knowledge_qa.py
Task: T014  # player/knowledge_qa.py

# Polish — run in parallel:
Task: T015  # logging smoke check
Task: T016  # pytest
Task: T017  # ruff
Task: T018  # pyright
```

---

## Implementation Strategy

### MVP First (US1 Only)

1. Complete Phase 1 (T001)
2. Complete Phase 2: Foundational (T002–T005)
3. Complete Phase 3: US1 (T006–T011)
4. **STOP and VALIDATE**: Load JSONL, run evaluation, confirm metrics display
5. Demo to GM — evaluation tab is fully usable at this point

### Incremental Delivery

1. Foundational → US1 → **Demo: GM can evaluate retrieval**
2. Add US2 (T012) → **Demo: GM can drill into any question**
3. Add US3 (T013–T014) → **Demo: Q&A answers are clean on both dashboards**
4. Polish (T015–T020) → ship

### Parallel Strategy (if two streams available)

- Stream A: Foundational → US1 → US2
- Stream B: (after Foundational) US3 → harness tests

---

## Notes

- [P] tasks touch different files — safe to run concurrently
- [USN] label traces each task to its user story for review traceability
- US3 is independent of US1/US2 and can be started right after Foundational
- Harness tests (T006, T007) should be written before implementation (T008–T011) where possible
- No new packages, DB tables, or migrations required — all changes are additive
