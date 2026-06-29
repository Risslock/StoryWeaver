# Implementation Plan: LLM-as-Judge Response Evaluation

**Branch**: `013-llm-judge-eval` | **Date**: 2026-06-28 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/013-llm-judge-eval/spec.md`

## Summary

Add LLM-as-judge response quality evaluation to both the harness and the RAG Evaluation Gradio tab. The existing `knowledge_qa` harness measures only retrieval quality (MRR/nDCG/Recall@10); this feature adds:

1. **Two new harness commands**: `eval_runner.py` (calls `ask_question()` from `apps/web/services/knowledge.py` with required `--campaign-id` and `--role` CLI args → writes EvaluationRecords to SQLite) and `judge_runner.py` (reads EvaluationRecords, calls a configurable judge LLM, writes back faithfulness/relevance/context-utilization scores).
2. **UI integration**: A new "Response Quality" section inside the existing RAG Evaluation Gradio tab (`apps/web/pages/gm/rag_eval.py`) that runs the same pipeline interactively — same JSONL question file, `campaign_id` + `role` from the active session, async streaming progress per question — and persists results to the same `data/eval.db` store.

The judge is wired through the existing `packages/llm/` provider abstraction with a `get_judge_provider()` factory. Structured JSON output is parsed via `LLMProvider.generate_structured()`. The generation step reuses the existing `ask_question()` function directly — no new generation component is built.

---

## Technical Context

**Language/Version**: Python 3.11+

**Primary Dependencies**:
- *Existing*: `packages/llm/` (`LLMProvider`, `generate_structured()`), `packages/rag/` (retrieval pipeline), `packages/storage/` (SQLAlchemy 2.x + aiosqlite), `apps/web/services/knowledge.py` (`ask_question()`), `apps/web/pages/gm/rag_eval.py` (existing RAG Eval tab)
- *New in `packages/rag/`*: `pydantic` (already present), no new external packages required
- *Harness*: `pytest>=8`, `pytest-asyncio`, `pyyaml` (all already present)

**Storage**: New SQLite database `data/eval.db` for `ResponseEvalRecord` rows via the existing `packages/storage/` SQLAlchemy 2.x + aiosqlite infrastructure. Both harness scripts and the Gradio UI write to the same store. `benchmark_results.jsonl` (retrieval metrics) is unchanged.

**Generation**: The answer generation step calls `ask_question(question, campaign_id, role)` from `apps/web/services/knowledge.py` directly — the production pipeline used in the Knowledge Q&A tab (multi-query expansion → `ChromaKnowledgeRetriever` → RRF ranking → `OllamaProvider` synthesis). No new generation component is built. The `campaign_id` (UUID) and `role` ("gm" | "player") are supplied as:
- **CLI path**: required `--campaign-id` and `--role` args on `eval_runner.py`
- **UI path**: read from the active `CampaignSession` in Gradio `session_state`

**UI**: A new "Response Quality" accordion/section appended to `apps/web/pages/gm/rag_eval.py` — no new tab. Uses the same JSONL question file already loaded in the tab, the same async-generator streaming pattern as `on_run_eval()`, and `session_state.campaign_id` / `session_state.role`. A thin service `apps/web/services/response_eval.py` wraps `ask_question()` + `JudgeEvaluator` for the UI handler. Provider configuration (`JUDGE_PROVIDER`, `JUDGE_MODEL`) is read from env vars at startup; the UI does not expose provider controls.

**Testing**: `pytest` + `pytest-asyncio` for unit and integration tests; integration test uses a real Ollama provider.

**Target Platform**: Local (Windows/Linux), Ollama as default judge provider; Claude as optional cloud provider.

**Performance Goals**: ≤60 s per question on a local Ollama judge (SC-001). UI streams one result row per question via Gradio async generator.

**Constraints**:
- Sequential processing only — no concurrency (FR-009)
- `JUDGE_PROVIDER` and `JUDGE_MODEL` are required env vars with no code-level default
- `--campaign-id` (UUID) and `--role` ("gm"|"player") are required CLI args for `eval_runner.py` (FR-011)
- `ask_question()` governs provider selection for generation; no new `ANSWER_PROVIDER`/`ANSWER_MODEL` env vars
- Judge prompt template must be a file path, not a hard-coded string (FR-007)
- Re-scoring already-scored records requires explicit opt-in (`--force` flag on `judge_runner.py`)
- All logging via `logging.getLogger(__name__)`; no bare `print()` in non-CLI paths (Principle VIII)
- UI must follow Principle VII: visible placeholder before any judge run; all errors surfaced in Gradio

**Scale/Scope**: 118 gold-standard questions per harness run; EvaluationRecords accumulate across runs. UI typically processes 10–50 questions interactively.

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Spec-Driven Development | ✅ PASS | Spec exists at `specs/013-llm-judge-eval/spec.md`; all clarifications resolved |
| II. Provider Abstraction | ✅ PASS | `get_judge_provider()` factory; switching judge requires only env var change |
| III. Package Isolation | ✅ PASS | New library code in `packages/rag/rag/evaluation/`; harness in `harness/knowledge_qa/`; UI extension stays within existing `apps/web/` |
| IV. Local-First, Cloud-Optional | ✅ PASS | Ollama is the required local judge; Claude is opt-in via env var |
| V. Harness-Driven Quality | ✅ PASS | Feature IS harness infrastructure; unit + integration tests included; quickstart scenarios are acceptance tests |
| VI. Product-First Development | ✅ PASS | UI integration delivers observable value (judge scores in RAG Eval tab); no new auth, API, or infra layer |
| VII. Placeholder-First & Explicit Failures | ✅ PASS | Response Quality section renders a placeholder stub before any judge run; judge errors surface as Gradio messages (never log-only) |
| VIII. Structured Logging & Observability | ✅ PASS | All new modules use `logging.getLogger(__name__)`; `LOG_LEVEL=DEBUG` exposes judge prompt, raw response, and per-question scores |

**Gate Result**: ✅ ALL PASS — No violations require justification.

---

## Project Structure

### Documentation (this feature)

```text
specs/013-llm-judge-eval/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   ├── eval-runner-cli.md    # Phase 1 output — harness CLI contract
│   ├── judge-runner-cli.md   # Phase 1 output — harness CLI contract
│   └── rag-eval-ui.md        # Phase 1 output — UI contract for response quality section
└── tasks.md             # Phase 2 output (via /speckit-tasks — NOT created here)
```

### Source Code

```text
packages/rag/rag/evaluation/        # NEW subpackage
├── __init__.py
├── models.py                       # Pydantic models: EvaluationInput, DimensionScore, JudgeResult, JudgeScore, JudgeStatus
├── store.py                        # SQLAlchemy model (ResponseEvalRecord) + EvaluationStore
├── judge.py                        # JudgeEvaluator: calls LLM, parses JSON, handles all error states
├── factory.py                      # get_judge_provider() — reads JUDGE_PROVIDER / JUDGE_MODEL env vars
└── prompts/
    └── judge_prompt.txt            # Default judge prompt template (configurable via JUDGE_PROMPT_PATH)

packages/rag/tests/evaluation/      # NEW test directory
├── __init__.py
├── test_models.py                  # Unit: Pydantic validation, score clamping to [0,1]
├── test_store.py                   # Unit: EvaluationStore CRUD, run_id filtering, skip/overwrite logic
├── test_judge.py                   # Unit: JSON parse success/failure paths, all status assignments
└── test_judge_integration.py       # Integration: real Ollama judge on 3 sample questions

harness/knowledge_qa/
├── benchmark_results.jsonl         # Unchanged — retrieval metrics only
├── rag_gold_standard.jsonl         # Unchanged — gold-standard questions
├── eval_runner.py                  # NEW: --campaign-id + --role → ask_question() → EvaluationRecords
└── judge_runner.py                 # NEW: EvaluationRecords → judge scores (+ --summary report)

apps/web/pages/gm/
└── rag_eval.py                     # EXTENDED: adds "Response Quality" section with judge integration

apps/web/services/
└── response_eval.py                # NEW: thin async service wrapping ask_question() + JudgeEvaluator for UI

data/
└── eval.db                         # NEW: SQLite for ResponseEvalRecord (auto-created on first run)
```

**Structure Decision**: Single-project layout. New library code is a subpackage inside `packages/rag/`; no new top-level packages. Harness scripts sit in `harness/knowledge_qa/`. UI extension stays within the existing `apps/web/` application: `rag_eval.py` is extended (not replaced), and a thin `response_eval.py` service keeps Gradio page code free of business logic while sharing `packages/rag/rag/evaluation/` infrastructure with the harness.

---

## Complexity Tracking

No constitution violations.
