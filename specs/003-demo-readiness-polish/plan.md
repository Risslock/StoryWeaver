# Implementation Plan: Demo-Readiness QA & Incremental Polish

**Branch**: `003-demo-readiness-polish` | **Date**: 2026-06-19 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/003-demo-readiness-polish/spec.md`

---

## Summary

Fix 34 failing integration tests (root cause: `campaigns.owner_id NOT NULL` added in spec 002 was not reflected in pre-002 test fixtures), clean up 317 ruff linting violations, enhance the session summary handler to call the LLM in AI mode, pre-populate the scene description input from selected-session events, and update README to reflect current implemented state.

No new packages, tables, or migrations. Entire scope is confined to existing files in `apps/web/`, `tests/integration/`, and `pyproject.toml`.

---

## Technical Context

**Language/Version**: Python 3.12

**Primary Dependencies**:
- Gradio 4.0+ — UI framework; event handler wiring
- SQLAlchemy 2.0+ async + aiosqlite — ORM and async sessions
- pytest + pytest-asyncio (`asyncio_mode = "auto"`) — test runner
- ruff — linting (target: zero violations after this cycle)
- `packages/llm/` OllamaProvider — LLM call for session summary
- `packages/imagegen/` — image provider (existing, unchanged)

**Storage**: SQLite WAL (unchanged). No new migrations.

**Testing**: `uv run pytest -v` — target: 70/70 tests PASS (39 integration + 31 unit).

**Target Platform**: Local server, desktop/tablet browser.

**Project Type**: Gradio web application.

**Performance Goals**: No new performance requirements. LLM session summary call is async and non-blocking.

**Constraints**:
- No new packages, tables, or Alembic migrations
- No new Gradio components (existing components only)
- LLM call in session summary MUST fall back to event-list format on error or degraded mode
- Ruff clean pass MUST not alter runtime behavior (linting only)

**Scale/Scope**: Small group (5–20 concurrent users). Single SQLite database.

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Spec-Driven Development | ✅ PASS | Spec at `specs/003-demo-readiness-polish/spec.md`. README update is a mandatory delivery gate (Principle I + workflow step 6). |
| II. Provider Abstraction | ✅ PASS | LLM call for session summary uses existing `packages/llm/` interface. No direct Ollama SDK calls in app code. |
| III. Package Isolation | ✅ PASS | No new packages introduced. All changes in `apps/web/` or test files. |
| IV. Local-First, Cloud-Optional | ✅ PASS | LLM session summary uses local Ollama; degrades gracefully when unavailable. No cloud dependency added. |
| V. Harness-Driven Agent Quality | ✅ PASS | No new agents or tools. The integration test fix (FR-011) is the primary quality obligation. Existing harness evals unaffected. |

**No ADR required**: No new framework, infrastructure component, or architectural pattern introduced.

**Post-Phase-1 re-check**: ✅ All principles satisfied. Data model and contracts introduce no new packages, cloud dependencies, or agent changes.

---

## Project Structure

### Documentation (this feature)

```text
specs/003-demo-readiness-polish/
├── plan.md              # This file
├── research.md          # Phase 0 — test failures, linting state, UX findings
├── data-model.md        # Phase 1 — no new tables; fixture fix pattern
├── quickstart.md        # Phase 1 — validation scenarios
├── contracts/
│   └── ux-improvements.md   # Session summary, scene pre-pop, linting, rename contracts
└── tasks.md             # Phase 2 output (/speckit-tasks — not created here)
```

### Source Code (changed files only)

```text
tests/integration/
├── conftest.py                       # NEW: shared test_owner_id fixture
├── test_character_creation.py        # FIX: campaign fixture → add owner_id
├── test_role_access.py               # FIX: campaign fixture → add owner_id
├── test_story_history.py             # FIX: campaign fixture → add owner_id
├── test_shared_campaign.py           # FIX: campaign fixture + inline campaign creation
├── test_image_generation.py          # FIX: campaign fixture → add owner_id
└── test_session_planning.py          # FIX: campaign fixture → add owner_id

apps/web/pages/gm/
└── history.py                        # ENHANCE: on_generate_summary LLM call;
                                      #          on_populate_scene_description (new);
                                      #          view_session_selector second .change;
                                      #          on_log_event variable rename

pyproject.toml                        # ADD: "harness/**" = ["E501"] per-file-ignore

README.md                             # UPDATE: reflect current implemented state
```

**Structure Decision**: Single-project fix cycle. No new packages or sub-applications. `tests/integration/conftest.py` is the only new source file.

---

## Milestones

### M1 — Fix Integration Tests (FR-011, SC-006, SC-007)

**Deliverable**: All 39 integration tests pass with zero errors.

**Steps**:

1. Create `tests/integration/conftest.py` with a shared `test_owner_id` pytest-asyncio fixture.
   - Depends on `backend: SQLiteBackend` from each test file's local backend fixture.
   - Creates a `User` row (imports `User` from `core.models`; `hash_password` from `apps.web.services.auth`) and returns `user.id: uuid.UUID`.

2. Update the `campaign` fixture in each of the 6 test files:
   - Add `test_owner_id: uuid.UUID` parameter
   - Add `owner_id=test_owner_id` to `Campaign(...)` constructor

3. In `test_shared_campaign.py::test_concurrent_gm_player_no_data_corruption`:
   - This test creates a Campaign inline (not via fixture) in a file-based DB.
   - Create a `User` inline in the same `async with` block before creating the `Campaign`.
   - Pass `owner_id=user.id` to the `Campaign` constructor.

4. Verify: `uv run pytest tests/integration/ -v` → 39/39 PASS.

**Files**: `tests/integration/conftest.py` (new), 6 existing test files.

---

### M2 — Ruff Linting Clean

**Deliverable**: `uv run ruff check .` exits 0.

**Steps**:

1. Add `"harness/**" = ["E501"]` to `[tool.ruff.lint.per-file-ignores]` in `pyproject.toml`.
   Removes 107 harness-runner violations from scope; all other rules still apply to harness.

2. Run `uv run ruff check --fix .` — auto-fixes 68 violations (import sort, unused imports, f-strings, UP/UP035/UP017 upgrades).

3. Run `uv run pytest -v` to confirm no regressions from auto-fix.

4. Manually fix remaining violations in `apps/` and `packages/`:
   - **E501** (~107 lines): wrap with `(` `)` line continuation
   - **ANN401**: annotate Gradio handlers returning `gr.update()` as `dict[str, Any]`
   - **SIM102**: collapse nested `if` where safe
   - **B905**: add `strict=False` to `zip()` calls (preserves current behavior)
   - **F841**: remove or rename unused variables to `_`
   - **N806**: lowercase local variable names in functions

5. Run `uv run ruff check .` — confirm 0 violations.
6. Run `uv run pytest -v` — confirm all tests still pass.

**Files**: `pyproject.toml`, various `apps/` and `packages/` files (no behavior change).

---

### M3 — Session Summary LLM Enhancement (FR-004, US-5)

**Deliverable**: `on_generate_summary` returns a 2–3 sentence narrative in AI mode; falls back to event list in degraded mode or on LLM error.

**Steps** (all in `apps/web/pages/gm/history.py`):

1. Import at module level:
   ```python
   from llm.factory import get_llm_provider
   from llm.errors import ProviderUnavailableError
   ```

2. Refactor `on_generate_summary`:
   - If `not state.ai_available`: return current event-list format (unchanged behavior)
   - Else: build prompt per [contracts/ux-improvements.md](contracts/ux-improvements.md#contract-1--session-summary-ai-enhanced) and call `provider.complete(prompt)`
   - Wrap in `try/except ProviderUnavailableError`: fall back to event-list with inline note

3. Run `uv run pytest -v` — confirm no regressions.

**Files**: `apps/web/pages/gm/history.py` only.

---

### M4 — Scene Description Pre-population (FR-006, US-6)

**Deliverable**: Selecting a session in the history filter pre-fills `scene_description_input` with a brief text summary of up to 5 session events.

**Steps** (all in `apps/web/pages/gm/history.py`):

1. Add `async def on_populate_scene_description(state, session_label, session_map) -> str` per
   [contracts/ux-improvements.md](contracts/ux-improvements.md#contract-2--scene-description-pre-population).

2. Register a second `.change` listener on `view_session_selector` with `outputs=[scene_description_input]`.

3. Rename confusing variables in `on_log_event` per
   [contracts/ux-improvements.md](contracts/ux-improvements.md#contract-4--on_log_event-variable-rename).

4. Manual smoke test: log events → select session → verify scene description input is pre-filled.

**Files**: `apps/web/pages/gm/history.py` only.

---

### M5 — README Currency (Constitution Principle I)

**Deliverable**: `README.md` accurately describes current implemented state as of spec 003.

**Steps**:

1. Read current `README.md`
2. Add/update sections:
   - Auth: custom sign-in / create-account panel (not Gradio built-in `auth=`)
   - Admin dashboard: campaign list, create, resume
   - GM dashboard: NPC twin chat, story history, AI-enhanced session summary, scene illustration with pre-populated description
   - Player dashboard: join by code, character upsert, twin chat, portrait generation
   - Degraded mode behavior (all AI features disabled gracefully)
   - How to run tests (`uv run pytest -v`)
   - Known limitations (Ollama required for LLM/image features)
3. Remove any references to planned-but-not-yet-implemented functionality

**Files**: `README.md` only.

---

## Acceptance Gates (ordered)

| # | Gate | Command | Pass Condition |
|---|------|---------|---------------|
| 1 | Integration tests | `uv run pytest tests/integration/ -v` | 39/39 PASS |
| 2 | Full suite | `uv run pytest -v` | 70/70 PASS |
| 3 | Linting | `uv run ruff check .` | Exit 0 |
| 4 | App starts | `uv run python apps/web/main.py` | No startup errors |
| 5 | Manual smoke | Quickstart scenarios 1–6 | All scenarios pass |
| 6 | README | Read `README.md` | Accurately describes current state |

All gates must pass for this spec's milestone to be complete.
