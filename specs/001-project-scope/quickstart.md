# Quickstart Validation Guide: StoryWeaver

**Branch**: `001-project-scope` | **Date**: 2026-06-18

Runnable validation scenarios that prove each milestone's feature set works end-to-end. For entity shapes see [data-model.md](data-model.md). For UI flow inputs/outputs see [contracts/ui-flows.md](contracts/ui-flows.md).

---

## Prerequisites

- Python 3.11+ and `uv` installed (`pip install uv` or via system package manager)
- Ollama installed and a model pulled: `ollama pull llama3.1`
- Docker + Docker Compose (for containerized validation scenarios)
- (M3+) ComfyUI running locally, or a HuggingFace API token in `.env`

---

## Setup

```bash
# Install all workspace packages
uv sync

# Configure environment
cp .env.example .env
# Default .env works for local validation (SQLite + Ollama, no changes needed)

# Run database migrations
uv run alembic upgrade head

# Start the Gradio app
uv run python apps/web/app.py
# App available at: http://localhost:7860
```

---

## M0 — Monorepo Scaffolding

**Goal**: Confirm project structure, config, and tooling are wired up correctly before any feature code exists.

```bash
# Lint
uv run ruff check .

# Type check
uv run pyright

# Unit tests (stubs pass)
uv run pytest tests/unit/ -v
```

**Expected**: No lint or type errors. Unit test suite passes (stubs/placeholders are acceptable at M0).

---

## M1 — Character Creation (SC-001 partial)

**Goal**: A player can complete the guided character creation flow and view their character sheet.

1. Open `http://localhost:7860`.
2. Create a Campaign: enter a campaign name and your GM display name. Note the join code shown.
3. Open a second browser tab; join with the same join code and a different display name (Player role).
4. In the Player tab, click **New Character** and complete the form:
   - Name, race, discipline, circle (all required)
   - At least one talent entry
   - Background, personality, goals (twin grounding fields — required)
5. Save. View the character sheet and verify all entered data is displayed correctly.
6. Create a second character for the same player — confirm both appear in the character selector.

**Automated assertion**:
```bash
uv run pytest tests/integration/test_character_creation.py -v
```

**Acceptance**: All User Story 1 acceptance scenarios 1 and 3 pass. Data displayed accurately and completely.

---

## M2 — Digital Twin Dialogue (SC-001, SC-006)

**Goal**: The character digital twin responds in-character and handles edge cases gracefully.

**Prerequisites**: Ollama running with at least one model pulled; character from M1 exists.

1. In the Player tab, open **My Twin** and select the M1 character.
2. Submit three distinct prompts:
   - "My village has just been attacked by a Horror. What does my character do first?"
   - "How does my character feel about the merchant we traded with last session?"
   - "What are my character's deepest long-term goals right now?"
3. Have a human reviewer evaluate each response for in-character consistency and grounding in the character's profile.
4. Submit an out-of-character or nonsensical prompt: "What's the weather on Mars?" — verify a graceful, non-harmful response.

**Harness run** (deterministic scoring over 10 scenarios):
```bash
uv run python harness/scenarios/twin_dialogue/run_scenarios.py --scenario m2_baseline
```

**Acceptance**: ≥3/3 prompts judged in-character by human reviewer (SC-006 partial). Out-of-character prompt handled gracefully (User Story 1 acceptance scenario 4). Harness score ≥ 8/10.

---

## M2 — GM NPC Twin

1. As GM, open **NPCs** and create a new NPC with a full profile (personality, goals, secrets).
2. Use the NPC twin chat to request in-character dialogue for a specific scene.
3. Create a second NPC with a distinct personality; request the same scene from each twin.
4. Verify the two responses are clearly distinct and match each NPC's profile.

**Acceptance**: User Story 2 acceptance scenarios 1 and 2 pass.

---

## M2 — Role-Scoped Access

1. As GM, create an NPC with `is_visible_to_players = False`.
2. In the Player browser tab, refresh. Verify the NPC does not appear in any Player view.
3. As GM, toggle visibility to `True`. As Player, refresh. Verify the NPC now appears.
4. As GM, create a story event with `is_public = False`. Verify Player's Story History tab does not show it.

**Automated assertion**:
```bash
uv run pytest tests/integration/test_role_access.py -v
```

**Acceptance**: User Story 2 acceptance scenario 3 and User Story 5 acceptance scenario 1 pass.

---

## M3 — Image Generation (SC-007)

**Goal**: Portrait and scene images are generated, displayed, and survive a refresh.

**Prerequisites**: ComfyUI running on default port, or `.env` set to `IMAGE_PROVIDER=huggingface HF_API_KEY=...`.

1. On a Player character sheet, click **Generate Portrait**. Wait for completion. Verify the image is displayed and reflects the character's physical description.
2. Refresh the page. Verify the portrait is still displayed (persisted via `portrait_url`).
3. As GM, create an NPC and generate its portrait. Verify same persistence behaviour.
4. Stop the image provider (or set `IMAGE_PROVIDER` to an invalid value). Request a portrait. Verify a clear error message appears and no crash occurs.

**Automated assertion**:
```bash
uv run pytest tests/integration/test_image_generation.py -v
```

**Acceptance**: ≥7/10 generated images judged to reflect their request by a human reviewer (SC-007). Graceful error when provider unavailable (User Story 4 acceptance scenario 3).

---

## M4 — Story History (SC-008)

**Goal**: Campaign history is persistent, queryable, correctly role-scoped, and loads within 5 seconds.

1. As GM, log 20+ story events across at least 5 sessions (mix of public and GM-only events; mix of event types).
2. Open the Story History tab as a Player. Verify:
   - Only public events are shown.
   - Events appear in chronological order (by session, then event order within session).
3. Open the Story History tab as GM. Verify GM-only events are also visible.
4. Measure load time for the full history view.
5. With a twin interaction that references a recent event: ask the twin "What happened with [event topic]?" and verify the response reflects awareness of that event (User Story 3 acceptance scenario 3).

**Automated timing assertion**:
```bash
uv run pytest tests/integration/test_story_history.py::test_history_load_time -v
# Asserts load < 5 seconds for 5+ sessions / 20+ events (SC-008)
```

**Acceptance**: All User Story 3 acceptance scenarios pass. SC-008 timing assertion passes.

---

## M4 — GM Session Planning

1. With at least one completed session in history, open **Session Plan** as GM.
2. Click **Generate Plan** for the next session.
3. Verify the generated plan references specific past events and open plot threads from the story history.
4. Edit the plan text. Save. Refresh. Verify edits persisted.
5. Invoke planning with an empty story history (first session): verify a usable starter plan is generated with a note that history is minimal.

**Acceptance**: User Story 6 acceptance scenarios 1, 2, and 3 pass.

---

## M5 — End-to-End Demo in Both Modes (SC-001, SC-002, SC-003)

**Goal**: The full demo runs in both local and cloud modes; provider swap requires only config changes.

### Local mode (Docker Compose)

```bash
docker compose -f deploy/compose/docker-compose.local.yml up
# Full demo at http://localhost:7860 — Ollama + SQLite + ChromaDB, no internet required
```

Run the full M1–M4 validation sequence. All scenarios must pass (SC-002).

### Cloud mode (Docker Compose)

```bash
# Requires: DATABASE_URL, LLM_PROVIDER, HF_API_KEY in environment
docker compose -f deploy/compose/docker-compose.cloud.yml up
# Full demo with cloud LLM + Postgres + pgvector
```

Run the full M1–M4 validation sequence. All scenarios must pass (SC-002).

### Provider swap test (SC-003)

```bash
# Change only .env: LLM_PROVIDER=huggingface HF_API_KEY=... HF_LLM_MODEL=mistralai/Mistral-7B-Instruct-v0.3
# Restart app — no code changes
uv run python apps/web/app.py
# Re-run M2 twin dialogue validation
```

**Acceptance**: Provider swap requires only `.env` changes (SC-003). Full demo passes in both deployment modes (SC-002).

---

## Degraded Mode Validation

**Goal**: App starts and remains functional when the AI provider is unavailable.

1. Stop Ollama, or set `OLLAMA_BASE_URL=http://localhost:9999` (unreachable).
2. Start the app: `uv run python apps/web/app.py`.
3. Verify:
   - App starts without crashing.
   - Persistent banner visible: "AI features are currently unavailable. Character sheets, story history, and campaign navigation remain accessible."
   - Character sheets, story history browsing, and campaign navigation work normally.
   - Twin chat submit button: `interactive=False`.
   - Portrait generate buttons: `interactive=False`.
   - Session planning generate button: `interactive=False`.

**Automated assertion**:
```bash
uv run pytest tests/integration/test_degraded_mode.py -v
```

**Acceptance**: Degraded mode resolved edge case from spec (see spec.md Edge Cases) — all non-AI features remain functional.