# Tasks: Demo-Readiness QA & Incremental Polish

**Input**: Design documents from `specs/003-demo-readiness-polish/`

**Prerequisites**: [plan.md](plan.md) | [spec.md](spec.md) | [research.md](research.md) | [data-model.md](data-model.md) | [contracts/ux-improvements.md](contracts/ux-improvements.md) | [quickstart.md](quickstart.md)

**Tests**: This cycle fixes existing broken tests (FR-011). New test tasks are only added where the spec explicitly requires new coverage (FR-012: critical demo path with no existing test).

**Organization**: Tasks follow milestone order from plan.md. M1 (test fix) is the hard prerequisite — everything gates on a clean test suite.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task maps to (US1–US7)
- All task descriptions include exact file paths

---

## Phase 1: Setup (Baseline Snapshot)

**Purpose**: Confirm starting state before any changes so regressions can be caught.

- [X] T001 Run `uv run pytest -v` and note which 34 integration tests fail — confirms the M1 fix is needed and provides a diff baseline

---

## Phase 2: Foundational — Fix Integration Tests (US-7 P1, M1)

**Purpose**: All integration tests must pass before anything else is verified. This is the hardest dependency gate in the cycle.

**⚠️ CRITICAL**: All Phase 3+ work assumes the test suite is green. Complete and verify this phase first.

**Goal**: Zero `NOT NULL constraint failed: campaigns.owner_id` errors; 39/39 integration tests PASS.

**Independent Test**: `uv run pytest tests/integration/ -v` exits 0 with all 39 tests PASS.

- [X] T002 [US7] Create `tests/integration/conftest.py` — shared `test_owner_id` pytest-asyncio fixture that creates a `User` row (imports `User` from `core.models`, `hash_password` from `apps.web.services.auth`) and returns `user.id: uuid.UUID`
- [X] T003 [P] [US7] Add `test_owner_id: uuid.UUID` parameter to `campaign` fixture and add `owner_id=test_owner_id` to `Campaign(...)` in `tests/integration/test_character_creation.py`
- [X] T004 [P] [US7] Same campaign fixture fix in `tests/integration/test_role_access.py`
- [X] T005 [P] [US7] Same campaign fixture fix in `tests/integration/test_story_history.py`
- [X] T006 [P] [US7] Same campaign fixture fix in `tests/integration/test_image_generation.py`
- [X] T007 [P] [US7] Same campaign fixture fix in `tests/integration/test_session_planning.py`
- [X] T008 [US7] Fix `tests/integration/test_shared_campaign.py`: update `campaign` fixture (add `test_owner_id` param + `owner_id=test_owner_id`) AND fix inline `Campaign(...)` creation in `test_concurrent_gm_player_no_data_corruption` (create a `User` inline in the same `async with` block before creating the `Campaign`, pass `owner_id=user.id`)
- [X] T009 [US7] CHECKPOINT: Run `uv run pytest tests/integration/ -v` — confirm 39/39 PASS before proceeding

---

## Phase 3: Foundational — Linting Clean (Cross-Cutting, M2)

**Purpose**: `ruff check .` must exit 0 before this milestone closes. Tasks T010–T011 can start immediately after T002 (different files); T012–T016 require T010–T011 to be complete.

**Goal**: Zero ruff violations. No behavior changes — linting fixes only.

**Independent Test**: `uv run ruff check .` exits 0 and `uv run pytest -v` still passes.

- [X] T010 [P] Add `"harness/**" = ["E501"]` under `[tool.ruff.lint.per-file-ignores]` in `pyproject.toml` (removes 107 harness-runner violations from scope per contracts/ux-improvements.md Contract 3)
- [X] T011 Run `uv run ruff check --fix .` to auto-fix 68 violations (import sort, unused imports, f-string cleanup, UP007/UP017/UP035 upgrades)
- [X] T012 CHECKPOINT: Run `uv run pytest -v` — confirm no regressions after auto-fix
- [X] T013 [P] Manually fix E501 line-length violations in `apps/web/pages/` (wrap lines longer than 88 chars using `(` `)` continuation)
- [X] T014 [P] Manually fix E501 line-length violations in `apps/web/services/` and `packages/` files
- [X] T015 [P] Fix ANN401 violations in `apps/web/pages/` — annotate Gradio event handler inner functions that return `gr.update()` as `dict[str, Any]` or explicit typed tuples/unions
- [X] T016 [P] Fix SIM102 (collapsible nested if), B905 (add `strict=False` to `zip()` calls), F841 (remove unused local variables or rename to `_`), and N806 (lowercase local variable names) across `apps/` and `packages/`
- [X] T017 CHECKPOINT: Run `uv run ruff check .` — confirm 0 violations; run `uv run pytest -v` — confirm all tests still pass

---

## Phase 4: US-7 Acceptance Gate — App Startup & Player Join Fix

**Purpose**: Confirm both M1 and M2 deliverables are satisfied AND fix two discovered runtime bugs before beginning enhancement work.

**Bugs identified during T019**:
1. `apps/web/main.py` has no `__main__` entry point — running `uv run python apps/web/main.py` defines the ASGI module and exits silently without starting a server.
2. `_navigate` in `apps/web/app.py` checks `if user is None: → auth_col` before checking session — players who join via join code (no User account; only `session_state` is set by `pages/landing.py::on_join`) are incorrectly routed back to the auth screen instead of `player_col`.

- [X] T018 [US7] Run `uv run pytest -v` (full suite) — confirm 70/70 PASS, exit code 0 (39 integration + 31 unit)
- [X] T019 [US7] Add `__main__` entry point to `apps/web/main.py` — append the block below so that `uv run python apps/web/main.py` starts uvicorn on localhost:7860 (currently no `__main__` block exists so Python exits immediately after module-level evaluation):
  ```python
  if __name__ == "__main__":
      import uvicorn
      uvicorn.run("main:app", host="0.0.0.0", port=7860, reload=False)
  ```
  Run `uv run python apps/web/main.py` and verify the server starts at `http://localhost:7860`.
- [ ] T020 [US1] Fix player navigation bug in `apps/web/app.py::_navigate` — the current logic routes to `auth_col` whenever `user is None`, even when a `CampaignSession` with `role="player"` has been set by `pages/landing.py::on_join`. Change the guard from `if user is None:` to `if user is None and session is None:`, then add a new branch immediately after: when `user is None` and `session is not None` (i.e. player joined via join code), return `player_col` visible and `auth_col` hidden (pattern mirrors the existing `role == "player"` return at the bottom of the function, with `show_banner = not session.ai_available`)
- [ ] T021 [US1] CHECKPOINT: Start the app with `uv run python apps/web/main.py`; open `http://localhost:7860`; enter a valid campaign name, join code, and player name; click "Join Campaign"; verify `player_col` becomes visible and the welcome message appears. Run `uv run pytest -v` — confirm no regressions.

---

## Phase 5: US-5 — Session Summary LLM Enhancement (P2, M3)

**Goal**: `on_generate_summary` returns a 2–3 sentence LLM-written narrative in AI mode; falls back to the current formatted event list in degraded mode or on LLM error (never blank when events exist).

**Independent Test**: Log 3+ events in a session; with Ollama running, click "Generate Session Summary" and verify a narrative paragraph appears. Restart app with Ollama stopped; generate summary and verify the event list (not blank, not an error).

- [ ] T022 [US5] Read `packages/llm/` to confirm the correct import path for the LLM provider and any error classes — look for `factory.py`, `interface.py`, and exception classes in `packages/llm/llm/` before writing the import
- [ ] T023 [US5] Add LLM provider imports to `apps/web/pages/gm/history.py` (e.g., `from llm.factory import get_llm_provider` and the provider unavailable error class — exact symbols confirmed in T022)
- [ ] T024 [US5] Refactor `on_generate_summary` in `apps/web/pages/gm/history.py`: if `not state.ai_available` return current event-list format unchanged; else build prompt per `contracts/ux-improvements.md` Contract 1 (system + user message with `[{type}] content` event lines), call LLM, return response text; wrap in try/except for provider error → fall back to event list with inline note `*(AI summary unavailable — showing event log)*`
- [ ] T025 [US5] CHECKPOINT: Run `uv run pytest -v` — confirm no regressions; run manual smoke test: log 3 events → "Generate Session Summary" → verify narrative in AI mode and event list in degraded mode

---

## Phase 6: US-6 — Scenery Creation Pre-population (P2, M4)

**Goal**: When GM selects a session in the history filter, `scene_description_input` is automatically pre-filled with up to 5 events from that session as scene-setting context.

**Independent Test**: Log 3 events in a session; in Story History tab, select the session in the filter dropdown; verify the Scene Description input field populates with `[Type] content` lines. Verify it is editable (pre-fill is a suggestion, not locked).

- [ ] T026 [US6] Add `async def on_populate_scene_description(state, session_label, session_map) -> str` function to `apps/web/pages/gm/history.py` per `contracts/ux-improvements.md` Contract 2: query events for the selected session (reuse existing `_fetch_event_rows` or equivalent helper), format up to 5 as `[Type] content` lines, return `""` if session is None or has no events
- [ ] T027 [US6] Register a second `.change` listener on `view_session_selector` in `apps/web/pages/gm/history.py` with `inputs=[session_state, view_session_selector, session_map_state]` and `outputs=[scene_description_input]` — this is additive to the existing listener, which continues unchanged
- [ ] T028 [US6] Rename confusing variables in `on_log_event` in `apps/web/pages/gm/history.py` per `contracts/ux-improvements.md` Contract 4: `_` → `log_sel_update`, `new_session_map` → `view_sel_update`, `view_update` → `summary_sel_update`, `updated_session_map` → `session_map` (values unchanged, names only)
- [ ] T029 [US6] CHECKPOINT: Run `uv run pytest -v` — confirm no regressions; run manual smoke: log events → select session → verify scene_description_input pre-filled; verify editing is possible after pre-fill

---

## Phase 7: Demo Path Verification (US-1, US-2, US-3, US-4 P1/P2)

**Purpose**: Validate that existing implementations still work end-to-end. These are verification tasks only — no new code unless a bug is found. If a bug is found, fix it and add a test.

**All tasks in this phase can run in parallel** (independent demo paths, no shared state between them).

- [ ] T030 [P] [US1] Validate auth flow per `quickstart.md` Scenario 1: create account → immediate dashboard navigation (no reload); sign out; sign in → campaign list; wrong credentials → clear error. Fix any broken behavior found.
- [ ] T031 [P] [US2] Validate GM experience per `quickstart.md` Scenario 2: create campaign → resume → join code visible; create NPC → appears in selector; NPC twin chat response (AI mode); log event → appears in timeline. Fix any broken behavior found.
- [ ] T032 [P] [US3] Validate player experience per `quickstart.md` Scenario 3: join by code → "Joined! Welcome, [name]"; create character → appears in selector; character sheet renders all fields; rejoin in new tab → character already available. Fix any broken behavior found.
- [ ] T033 [P] [US4] Validate portrait generation per `quickstart.md` Scenario 6: AI mode — generate portrait → image persists on reselection; missing physical description → clear error message; degraded mode — button disabled, banner shown. Fix any broken behavior found.

---

## Phase 8: Polish — README Currency (M5, Constitution Principle I)

**Purpose**: `README.md` must accurately describe the current implemented state. A README describing planned or superseded functionality is a constitution defect.

- [ ] T034 Read current `README.md` and identify all sections that reference the auth flow, GM/player experience, image generation, session summary, or test commands
- [ ] T035 Update `README.md` auth section: describe the custom Sign In / Create Account panel (not Gradio built-in `auth=`); include that `register_user` validates username (3–50 chars, alphanumeric+underscore) and password (≥8 chars)
- [ ] T036 Update `README.md` GM dashboard section: add NPC twin chat, AI-enhanced session summary (Ollama required), and scene illustration with auto-populated description from session events
- [ ] T037 Update `README.md` player dashboard section: join by code, character upsert semantics (same name = update, not duplicate), portrait persistence
- [ ] T038 Update `README.md` developer section: test commands (`uv run pytest -v`, `uv run ruff check .`), startup command (`uv run python apps/web/main.py`), known limitations (Ollama required for LLM/image features; degraded mode behavior), remove any planned-but-unimplemented feature descriptions
- [ ] T039 FINAL CHECKPOINT: Run all acceptance gates from `quickstart.md` (Gates 1–4); confirm README accurately describes what was just delivered

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Baseline)**: No dependencies — run immediately
- **Phase 2 (Test Fix)**: Depends only on Phase 1 — T003–T008 are independent of each other [P]
- **Phase 3 (Linting)**: T010 can start in parallel with Phase 2 (different files); T013–T016 can start after T012; T011 depends on T010
- **Phase 4 (Acceptance Gate + Bug Fixes)**: Depends on Phase 2 + Phase 3 completion; T020 depends on T019
- **Phase 5 (US-5)**: Depends on Phase 4 (clean suite + app starts + player join works)
- **Phase 6 (US-6)**: Depends on Phase 4; can run in parallel with Phase 5 (different logical sections of same file — coordinate edits to `history.py` to avoid merge conflicts)
- **Phase 7 (Verification)**: Depends on Phase 5 + Phase 6 (all enhancements must be in place)
- **Phase 8 (README)**: Depends on Phase 7 (README must reflect final delivered state)

### User Story Dependencies

- **US-7 (P1)**: Phases 2–4 — blocks all other work; no story dependencies
- **US-1 (P1)**: T020–T021 in Phase 4 — player navigation bug fix; also verified in T030 (Phase 7)
- **US-5 (P2)**: Phase 5 — depends only on clean test suite from US-7
- **US-6 (P2)**: Phase 6 — depends only on clean test suite from US-7; coordinate `history.py` edits with US-5
- **US-2, US-3, US-4 (P1/P2)**: Phase 7 — verification only; all can run in parallel after enhancements land

### Parallel Opportunities Within Phases

**Phase 2** (after T002 is created):
```
T003, T004, T005, T006, T007 can all start simultaneously (different test files)
T008 must be handled separately (two changes in one file)
```

**Phase 3** (after T011 auto-fix):
```
T013, T014, T015, T016 can all start simultaneously (different files or rule categories)
```

**Phase 7** (after Phase 6 complete):
```
T030, T031, T032, T033 can all start simultaneously (independent demo paths)
```

---

## Implementation Strategy

### MVP: Test Suite Green + App Runs (US-7 + bug fixes)

1. Phase 1: Baseline snapshot (T001)
2. Phase 2: Fix integration tests (T002–T009)
3. Phase 3: Linting clean (T010–T017)
4. Phase 4: Acceptance gate + startup and navigation bug fixes (T018–T021)
5. **STOP**: Test suite is green, app starts, player join works. Ship or continue.

### Incremental Delivery

1. MVP (above) → test suite green, app functional
2. Phase 5 → session summary narrative (US-5)
3. Phase 6 → scene pre-population (US-6)
4. Phase 7 → verify all demo paths (US-1 through US-4)
5. Phase 8 → README reflects delivered state

### Single-Developer Strategy (Sequential)

Work in task-ID order: T001 → T002 → T003–T008 (commit as a batch) → T009 → T010 → T011 → T012 → T013–T016 (commit as a batch) → T017 → T018 → T019 → T020 → T021 → T022–T025 → T026–T029 → T030–T033 (run all) → T034–T039.

---

## Notes

- [P] tasks = different files or truly independent work; no risk of conflicts
- US-5 and US-6 both touch `apps/web/pages/gm/history.py` — coordinate edits or do them sequentially (Phase 5 then Phase 6)
- T008 is NOT marked [P] because it modifies both the fixture AND an inline creation in the same file
- T022 (LLM import research) is a prerequisite for T023; always read packages/llm/ before writing the import
- T020 (navigation fix) is NOT marked [P] — it depends on T019 (startup fix must be verified first so you can smoke-test the fix interactively)
- If any Phase 7 verification task finds a bug, fix it and re-run `uv run pytest -v` before proceeding
- Constitution gate: T039 (README currency) MUST complete before milestone is declared done (Principle I)