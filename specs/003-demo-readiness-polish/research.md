# Research: Demo-Readiness QA & Incremental Polish

**Date**: 2026-06-19 | **Plan**: [plan.md](plan.md)

---

## Finding 1 — Test Suite State

**Decision**: 31/31 unit tests in `apps/web/tests/` pass. 34 integration tests in `tests/integration/` ERROR on fixture setup; 1 FAILS inline; 4 pass. All integration failures share a single root cause.

**Root cause**: `Campaign.owner_id` was added as `NOT NULL` in spec 002 migration (`0002_auth_admin_ui.py`). All six integration test files pre-date spec 002 and create `Campaign` objects without `owner_id`, violating the constraint. The integration tests exercise correct business logic — they are not wrong about what they test; they are simply missing a required field in their fixtures.

**Affected files** (all 6 have this fixture gap):
- `tests/integration/test_character_creation.py` — `campaign` fixture
- `tests/integration/test_role_access.py` — `campaign` fixture
- `tests/integration/test_story_history.py` — `campaign` fixture
- `tests/integration/test_shared_campaign.py` — `campaign` fixture + inline campaign in `test_concurrent_gm_player_no_data_corruption`
- `tests/integration/test_image_generation.py` — `campaign` fixture
- `tests/integration/test_session_planning.py` — `campaign` fixture

**Fix**: Create `tests/integration/conftest.py` with a shared `test_owner_id` pytest-asyncio fixture that creates a minimal `User` row using the calling test's `backend` fixture. Update every `campaign` fixture in the 6 test files to accept `test_owner_id` and pass `owner_id=test_owner_id` to the `Campaign` constructor. Fix the inline campaign creation in `test_concurrent_gm_player_no_data_corruption` to also create a `User` first.

**Secondary warning** (benign): `test_player_character_id_restored_on_rejoin` (in `apps/web/tests/test_player_join.py`) emits a `PytestUnhandledThreadExceptionWarning` from an aiosqlite background thread that fires after the per-function event loop closes. The test passes; the warning is a known aiosqlite + pytest-asyncio interaction. It can be suppressed by adding `asyncio_default_fixture_loop_scope = "session"` to pytest config or by using a session-scoped loop, but this is a low-priority cleanup separate from the main fixes.

---

## Finding 2 — Ruff Linting State

**Decision**: Run `ruff check --fix` for auto-fixable issues (68 total); add `harness/**` to per-file E501 exclusion (removes 107 harness-only issues from scope); manually fix remaining E501 and other issues in app/package code.

**Breakdown** (from `ruff check . --statistics`):

| Rule | Count | Fixable? | Primary location |
|------|-------|----------|-----------------|
| E501 Line too long (>88) | 214 | No | 107 in `harness/runner.py`, rest spread across app/package files |
| I001 Import sort/format | 41 | ✅ Auto | All app/package files |
| ANN401 Any type annotation | 21 | No | Gradio handler return types |
| F401 Unused imports | 13 | ✅ Auto | Various |
| SIM102 Collapsible if | 7 | No | Various |
| UP007 Non-PEP 604 union | 6 | ✅ Auto | Various |
| F541 f-string no placeholder | 4 | ✅ Auto | Various |
| B905 zip() without strict | 3 | No | Various |
| F841 Unused variable | 2 | No | Various |
| N806 Non-lowercase in function | 2 | No | Various |
| UP017 datetime-timezone-utc | 2 | ✅ Auto | Various |
| UP035 Deprecated imports | 2 | ✅ Auto | Various |
| **Total** | **317** | **68 auto** | |

**Harness ruling**: `harness/runner.py` alone contributes 107 of the 214 E501 violations. Harness is evaluation tooling; its line-length style should not block the app CI gate. Adding `"harness/**" = ["E501"]` to `[tool.ruff.lint.per-file-ignores]` in `pyproject.toml` removes these from scope and reduces the manual E501 burden to ~107 lines across `apps/` and `packages/`.

**ANN401 strategy**: Most appear in Gradio event handler inner functions that return `gr.update()`. The Gradio return type is `dict[str, Any]` at runtime. Annotating inner handler return types as `dict[str, Any]` or `tuple[Any, ...]` resolves ANN401. Where the function already returns a typed union, use `X | Y` (PEP 604 style).

**Tests and migrations** are already excluded from E501 in `pyproject.toml` (`**/tests/**` and `**/models.py`); no change needed there.

---

## Finding 3 — Session Summary Enhancement

**Decision**: Call the existing LLM provider (via `packages/llm/llm/interface.py`) from `on_generate_summary` in `apps/web/pages/gm/history.py`. Fall back to formatted event list when `ai_available=False` or LLM call fails.

**Current state**: `on_generate_summary` concatenates events with emoji prefixes and returns a markdown string. No LLM call.

**Proposed prompt structure**:
```
System: You are a tabletop RPG scribe. Write a 2–3 sentence narrative summary 
        of the session events listed below. Use past tense. Be concise and vivid.
        Do not reference game mechanics or dice rolls.

User: Session: {session_label}
      Events:
      - [Dialogue] ...
      - [Discovery] ...
      (up to all events for the session, both public and private)
```

**Implementation**: Import `OllamaProvider` inside the handler (same pattern as character portrait generation in `character.py`). If `state.ai_available is False`, skip the LLM call and use the existing text-list format as fallback. Catch `ProviderUnavailableError` and fall back to text list with an inline note.

**Token estimate**: A session with 10 events at ~50 words each = ~500 input tokens. Response target: ~100 tokens. Well within Ollama local model limits.

---

## Finding 4 — Scene Description Pre-population

**Decision**: Wire `view_session_selector.change` to a second output that pre-fills `scene_description_input` with a brief text summary of events from the selected session. No LLM needed — pure Python formatting of already-loaded event data.

**Implementation**: Add `async def on_populate_scene_description(state, session_label, session_map)` in `history.py`. This function calls `_fetch_event_rows` for the selected session and formats up to 3 events as `[Type] content` lines. Wire it as a second listener on `view_session_selector.change` with `outputs=[scene_description_input]`.

If the selected session has no events, set `scene_description_input` to an empty string.

**Design note**: Pre-population is a suggestion; the GM can edit before generating. The text should be brief and actionable, not a full transcript.

---

## Finding 5 — on_log_event Variable Naming

**Decision**: Variable names are confusing but the values flow through correctly to the right outputs. Rename for clarity during the manual linting pass.

**Traced mapping**: `load_page()` returns `(log_sel_upd, view_sel_upd, summary_sel_upd, session_map, rows, ids, summary_btn_upd, scene_btn_upd)`. The unpacking `_, new_session_map, view_update, updated_session_map, rows, ids, ...` assigns misleading names but the return statement maps values to outputs in the correct order. Behavior is correct.

---

## Finding 6 — Portrait Button Loading State

**Decision**: No code change needed. Gradio 4.x automatically disables a `gr.Button` for the duration of its async `.click()` handler, providing the built-in loading state described in FR-003.
