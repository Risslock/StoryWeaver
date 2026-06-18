# Tasks: StoryWeaver — Project Scope & Vision

**Input**: Design documents from `/specs/001-project-scope/`

**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅, quickstart.md ✅

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story. No test tasks are included unless explicitly requested.

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no dependencies within the phase)
- **[Story]**: Maps to a user story from spec.md (US1–US6)
- Exact file paths are included in every task description

---

## Phase 1: Setup — Monorepo Scaffolding (M0)

**Purpose**: Initialize the uv workspace, directory structure, tooling, and container configuration before any feature code.

- [ ] T001 Initialize uv workspace: create root `pyproject.toml` with `[tool.uv.workspace]` members `["apps/*", "packages/*"]` and dev dependency group (pytest≥8, ruff≥0.4, pyright≥1.1, alembic≥1.13)
- [ ] T002 [P] Create all package directories under `apps/web/` and `packages/` (core, rules_earthdawn, agents, llm, imagegen, rag, storage, story) with stub `pyproject.toml` per research.md §4 subpackage pattern
- [ ] T003 [P] Configure ruff linting and pyright type-checking in root `pyproject.toml` (target Python 3.11+; strict pyright mode)
- [ ] T004 [P] Create `.env.example` with all required environment variable keys: `DATABASE_URL`, `LLM_PROVIDER`, `OLLAMA_BASE_URL`, `OLLAMA_MODEL`, `IMAGE_PROVIDER`, `HF_API_KEY`, `COMFYUI_URL`, `EMBEDDING_PROVIDER`
- [ ] T005 [P] Create `deploy/docker/Dockerfile.web` (apps/web Gradio entry point) and `deploy/docker/Dockerfile.ollama` (Ollama sidecar)
- [ ] T006 [P] Create `deploy/compose/docker-compose.local.yml` and `deploy/compose/docker-compose.cloud.yml` stubs (services: web, ollama, chromadb for local; web, postgres, pgvector for cloud)
- [ ] T007 [P] Create `docs/adr/ADR-005-agent-framework.md` documenting Pydantic-AI selection, rationale, and alternatives considered (required before M2 per constitution and plan.md open compliance item)

**Checkpoint**: `uv sync` installs cleanly; `ruff check .` and `pyright` pass on stub files; directory tree matches plan.md project structure.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before any user story implementation begins.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [ ] T008 Create `packages/core/config.py` — typed `Settings` dataclass loaded from environment variables via `pydantic-settings`: `database_url`, `llm_provider`, `ollama_base_url`, `ollama_model`, `image_provider`, `hf_api_key`, `comfyui_url`, `embedding_provider`, `max_twin_turns` (default 20)
- [ ] T009 [P] Create `packages/core/errors.py` — domain exceptions: `AccessDeniedError`, `ProviderUnavailableError`, `EntityNotFoundError`, `CampaignJoinError`, `ValidationError`
- [ ] T010 Create `packages/core/models.py` — SQLAlchemy 2.x `DeclarativeBase` ORM models for all entities from data-model.md: `Campaign`, `Character`, `NPC`, `DigitalTwin`, `Session`, `StoryEvent`, `SessionPlan` (all fields, indexes, unique constraints, and ON DELETE CASCADE as specified)
- [ ] T011 Create `packages/core/schemas.py` — Pydantic v2 schemas mirroring all ORM entities: `CampaignSchema`, `CharacterSchema`, `NPCSchema`, `DigitalTwinSchema`, `SessionSchema`, `StoryEventSchema`, `SessionPlanSchema`, `CampaignSession` dataclass; also `PlayerNPCSchema` (Player-visible NPC fields: `id`, `name`, `role`, `race`, `personality`, `portrait_url` — excludes `gm_notes` and `background`)
- [ ] T012 Create `alembic.ini` at repo root and `packages/core/migrations/` with initial Alembic migration generated from `packages/core/models.py`; configure async DB URL from `packages/core/config.py`
- [ ] T013 Create `packages/storage/interface.py` — `StorageBackend` ABC with async methods: `get_session()`, `execute()`, `initialize_db()`
- [ ] T014 Create `packages/storage/sqlite/` — SQLite adapter using `aiosqlite` via SQLAlchemy async engine; set `PRAGMA journal_mode=WAL` at connection-open time for concurrent reader support (research.md §5)
- [ ] T015 Create `packages/llm/interface.py` — `LLMProvider` ABC with async `generate(prompt: str, system: str) -> str` method
- [ ] T016 Create `packages/llm/providers/ollama.py` — Ollama provider using OpenAI-compat REST API; reads `OLLAMA_BASE_URL` and `OLLAMA_MODEL` from config; raises `ProviderUnavailableError` on connection failure
- [ ] T017 Create `apps/web/app.py` — Gradio `gr.Blocks()` app factory: `gr.State(value=None)` holding `CampaignSession`, conditional tab visibility routing (Player tabs vs. GM tabs) based on role, degraded-mode banner integration point
- [ ] T018 Create `apps/web/components/banner.py` — persistent `gr.HTML` AI-unavailable banner component; shown when `CampaignSession.ai_available = False`; content: "AI features are currently unavailable. Character sheets, story history, and campaign navigation remain accessible."
- [ ] T019 Create `apps/web/pages/landing.py` — Campaign create flow (name + GM display name → join code displayed) and join flow (join code + display name → role resolution: GM re-join if display name matches `Campaign.gm_display_name`, else Player); AI health check at join time sets `CampaignSession.ai_available`

**Checkpoint**: `uv run alembic upgrade head` creates the DB schema; app launches with `uv run python apps/web/app.py`; join flow creates and joins a campaign; AI unavailable banner appears when Ollama is unreachable.

---

## Phase 3: User Story 1 — Player Character Companion (Priority: P1) 🎯 MVP

**Goal**: A player creates their Earthdawn 4E character and uses its digital twin to explore in-character responses grounded in the character's profile.

**Independent Test**: Create a character profile and have the digital twin respond to three distinct in-game scenarios; verify each response is in-character and consistent with the profile without requiring image generation or multi-user features.

- [ ] T020 [P] [US1] Create `packages/rules_earthdawn/data/` — distilled mechanics tables (no copyrighted prose): `disciplines.json` (name, tier, key_attributes), `races.json` (name, attribute_bonuses), `circle_tables.json` (tier breakpoints)
- [ ] T021 [P] [US1] Create `packages/rules_earthdawn/character_builder.py` — guided creation flow: step definitions (race → discipline → attributes → talents → background), field defaults, creation-state helper functions
- [ ] T022 [P] [US1] Create `packages/rules_earthdawn/validator.py` — sanity-check validation: required fields present (`name`, `race`, `discipline`, `background`, `personality`), `circle` in range 1–15, attribute step values are positive integers
- [ ] T023 [US1] Create `apps/web/pages/player/character.py` — Player character tab: `gr.Dropdown` character selector (all player-owned characters in campaign), new character form (all Character entity fields from data-model.md), save button, character sheet display, `gr.Button` generate portrait (set `interactive=False` in degraded mode)
- [ ] T024 [US1] Create `packages/agents/twin/agent.py` — Pydantic-AI `Agent` for the digital twin: system prompt builder from entity profile fields, model-agnostic via `LLMProvider` ABC, one `Agent` instance per Character or NPC entity
- [ ] T025 [P] [US1] Create `packages/agents/twin/tools.py` — register `recall_story_events` and `describe_entity_trait` tools on the twin Agent using typed `RecallEventsInput`, `RecallEventsOutput`, `DescribeTraitInput`, `DescribeTraitOutput` schemas from contracts/agent-tools.md; access-control: character twin receives only `is_public=True` events
- [ ] T026 [US1] Create `apps/web/pages/player/twin_chat.py` — Player twin chat tab: `gr.Dropdown` character selector, `gr.Textbox` prompt input, `gr.Chatbot` rolling history, submit `gr.Button` (`interactive=False` in degraded mode), append each response to `DigitalTwin.conversation_history` and persist
- [ ] T027 [US1] Implement max-turns pruning in `packages/agents/twin/agent.py` — after appending each new turn to `DigitalTwin.conversation_history`, truncate oldest entries so the list never exceeds `Settings.max_twin_turns` (default 20) before persisting; prevents unbounded conversation history from exceeding the LLM context window
- [ ] T028 [P] [US1] Create `harness/scenarios/twin_dialogue/` — YAML scenario fixtures for `m2_baseline`: 10 prompt/profile-alignment pairs covering US1 acceptance scenarios 2 (in-character responses grounded in character profile) and 4 (out-of-character prompt handled gracefully without harmful output)
- [ ] T029 [US1] Create `harness/scoring/rubrics.py` — deterministic in-character scoring: keyword-alignment score (profile terms present in response), graceful-refusal detection (out-of-character prompt produces non-harmful response), composite 0–10 rubric
- [ ] T030 [P] [US1] Create `tests/integration/test_character_creation.py` — US1 acceptance scenarios 1 (create character → all fields saved to DB) and 3 (character sheet displays all saved data accurately and completely)
- [ ] T031 [P] [US1] Create `tests/integration/test_degraded_mode.py` — app starts without Ollama reachable; banner is visible; twin chat submit button is `interactive=False`; generate portrait button is `interactive=False`; character sheet and navigation remain functional

**Checkpoint**: US1 is fully functional and independently testable. A player can create a character, view its sheet, and converse with its twin. Conversation history is bounded by `MAX_TWIN_TURNS`. `uv run pytest tests/integration/test_character_creation.py -v` passes.

---

## Phase 4: User Story 2 — GM NPC Management (Priority: P2)

**Goal**: A GM creates and manages NPCs with digital twins, generates in-character dialogue, and accesses GM-only views that are inaccessible to Players.

**Independent Test**: Create two NPC profiles with distinct personalities; request in-character dialogue from each twin; verify responses are clearly distinct and consistent with each NPC's profile.

- [ ] T032 [P] [US2] Create `packages/agents/player_agent/` — `player_agent.py` with tools `get_character_sheet`, `update_character_field`, `list_own_characters`; enforce `player_display_name` access control; raise `AccessDeniedError` when character belongs to another player
- [ ] T033 [P] [US2] Create `packages/agents/gm_agent/` — `gm_agent.py` with tools `create_story_event`, `toggle_npc_visibility`, `get_all_npcs` using typed input/output schemas from contracts/agent-tools.md
- [ ] T034 [US2] Create `apps/web/pages/gm/npcs.py` — NPC management tab: `gr.Dropdown` NPC selector, new NPC form (all NPC fields including `gm_notes`), visibility toggle `gr.Checkbox` (`is_visible_to_players`), save button, NPC twin `gr.Chatbot`, generate portrait button (degraded-aware); Player-visible NPC responses use `PlayerNPCSchema` (excludes `gm_notes`)
- [ ] T035 [P] [US2] Create `apps/web/pages/gm/characters.py` — GM characters overview: `gr.Dataframe` listing all campaign characters (name, race, discipline, player display name), read-only character detail `gr.Markdown` on row selection
- [ ] T036 [P] [US2] Create `apps/web/pages/gm/world_notes.py` — GM world notes tab: `gr.Code` markdown editor, save as `StoryEvent(event_type="world_change", is_public=False)`, `gr.Dataframe` notes history (newest first)
- [ ] T037 [P] [US2] Create `tests/integration/test_role_access.py` — NPC with `is_visible_to_players=False` does not appear in Player view; GM toggles to `True`, Player refresh shows NPC using `PlayerNPCSchema` (no `gm_notes`); GM-only `StoryEvent` (`is_public=False`) absent from Player history; `gm_notes` never returned in Player-role queries
- [ ] T038 [P] [US2] Create `harness/scenarios/player_agent/` — YAML scenario fixtures for all three Player Agent tools: `get_character_sheet` (own character returns `CharacterSchema`; another player's character raises `AccessDeniedError`), `update_character_field` (valid field updates; `portrait_url` update rejected; unknown field name rejected), `list_own_characters` (returns only characters where `player_display_name` matches session display name)
- [ ] T039 [P] [US2] Create `harness/scenarios/gm_agent/` — YAML scenario fixtures for GM Agent tools: `create_story_event` (public event appears in player role query; private event filtered from player query but present in GM query), `toggle_npc_visibility` (hidden→visible flow; Player sees NPC after toggle; visible→hidden flow; Player no longer sees NPC), `get_all_npcs` (all NPCs returned including hidden; `gm_notes` present in output schema)

**Checkpoint**: US2 is fully functional. GM can create NPCs, chat with NPC twins, toggle visibility, and access private views. `uv run pytest tests/integration/test_role_access.py -v` passes. Harness scenarios exist for all Player Agent and GM Agent tools (Constitution Principle V).

---

## Phase 5: User Story 3 — Campaign Story History (Priority: P2)

**Goal**: Players and GM can review a persistent, shared timeline of campaign events — accurately role-scoped and chronologically ordered — without anyone maintaining it by hand.

**Independent Test**: Log five events across two sessions; verify all events appear in correct order in story history and are accessible to both GM and relevant players after a refresh.

- [ ] T040 [US3] Create `packages/story/session.py` — `Session` CRUD: `create_session(campaign_id, title, date_played)`, `list_sessions(campaign_id)`, `get_session(session_id)`; enforce `(campaign_id, session_number)` unique constraint
- [ ] T041 [US3] Create `packages/story/history.py` — `StoryEvent` CRUD and query: `create_event(...)`, `list_events(campaign_id, role, session_id=None)` with role-scoped filter (`is_public=True` for Player role), chronological ordering by `(session_number, event_order)`, leveraging composite index on `(campaign_id, session_id, event_order)` from data-model.md
- [ ] T042 [P] [US3] Create `apps/web/pages/player/history.py` — Player history tab: `gr.Dropdown` session selector, `gr.CheckboxGroup` event-type filter, `gr.Dataframe` or `gr.Markdown` event list (public events only); performance target < 5s for ≥5 sessions / ≥20 events (SC-008)
- [ ] T043 [P] [US3] Create `apps/web/pages/gm/history.py` — GM history tab: all events including GM-only, log event form (`gr.Group`: type, content, participants, public flag), log event button, generate session summary button (`interactive=False` in degraded mode); scene illustration wiring added in T052
- [ ] T044 [P] [US3] Create `harness/scenarios/history_recall/` — YAML scenario fixtures: semantic-query retrieval of specific events, chronological-order verification, role-scoped filtering (player context returns only `is_public=True` events), edge cases (empty session, query with no matching events)
- [ ] T045 [US3] Create `tests/integration/test_story_history.py` — US3 acceptance scenarios 1 (GM logs event → Player refresh sees it) and 2 (events in chronological order with session context); SC-008 timing assertion: `test_history_load_time` asserts load < 5 seconds for ≥5 sessions / ≥20 events

**Checkpoint**: US3 is fully functional. Story history is persistent, role-scoped, and loads within the SC-008 time budget. `uv run pytest tests/integration/test_story_history.py -v` passes.

---

## Phase 6: User Story 4 — Character and Scene Image Generation (Priority: P3)

**Goal**: Players and GMs generate portraits for characters and scene illustrations for locations; the system degrades gracefully when the image provider is unavailable.

**Independent Test**: Generate a character portrait from a profile and a scene illustration from a GM description; a human reviewer judges each image as meaningfully reflecting its request.

- [ ] T046 [US4] Create `packages/imagegen/interface.py` — `ImageProvider` ABC with `async generate(request: ImageGenRequest) -> ImageGenResponse`; define `ImageGenRequest` and `ImageGenResponse` Pydantic models from contracts/agent-tools.md
- [ ] T047 [P] [US4] Create `packages/imagegen/providers/comfyui.py` — ComfyUI local provider: workflow JSON submission to ComfyUI REST API, result polling, image bytes/URL return, `ProviderUnavailableError` on connection failure
- [ ] T048 [P] [US4] Create `packages/imagegen/providers/huggingface.py` — HuggingFace Inference API provider (cloud M5+): SDXL model call via HF REST API, image bytes to URL, graceful error on rate limit or key-not-set
- [ ] T049 [P] [US4] Create `apps/web/components/image_display.py` — `gr.Image` portrait/scene display widget with placeholder shown when `portrait_url` is `None`
- [ ] T050 [US4] Wire image generation into `apps/web/pages/player/character.py` — generate portrait button → `packages/imagegen` with prompt constructed from `Character.physical_description` → update `Character.portrait_url` → refresh portrait display
- [ ] T051 [US4] Wire image generation into `apps/web/pages/gm/npcs.py` — generate NPC portrait button → `packages/imagegen` with prompt from `NPC.physical_description` → update `NPC.portrait_url` → refresh portrait display
- [ ] T052 [US4] Wire scene illustration into `apps/web/pages/gm/history.py` — add `gr.Textbox` scene description prompt and `gr.Button` "Generate Scene Art" (`interactive=False` in degraded mode); on submit construct `ImageGenRequest` from GM description and call `packages/imagegen`; display result via `image_display.py` widget; handle `ImageGenResponse.error` with visible error message without crash (US4 acceptance scenario 2; FR-005)
- [ ] T053 [P] [US4] Create `harness/scenarios/imagegen/` — deterministic scenario fixtures: provider-unavailable path (mock provider raises `ProviderUnavailableError` → `ImageGenResponse.error` is non-None and `image_url` is `None`); prompt-construction test (Character `physical_description` fields yield expected keyword set in constructed prompt); response-handling test (valid `image_url` from response persisted to `Character.portrait_url` in DB after generation)
- [ ] T054 [P] [US4] Create `tests/integration/test_image_generation.py` — portrait generated end-to-end (mock provider), `portrait_url` persists across page refresh, clear error message when provider unavailable without crashing (US4 acceptance scenario 3)

**Checkpoint**: US4 is fully functional. Character and NPC portraits and GM scene illustrations can be generated and persist. Provider-unavailable path shows a clear error and does not crash. Harness scenarios cover all deterministic imagegen behaviors (Constitution Principle V).

---

## Phase 7: User Story 5 — Shared Campaign Session (Priority: P3)

**Goal**: A GM and one or more players join the same campaign with role-appropriate access; shared updates are visible after a refresh; no data corruption from concurrent actions.

**Independent Test**: GM and one player join same campaign; GM logs a public event and creates a private NPC note; player refreshes and sees the shared event but not the private note.

- [ ] T055 [US5] Integrate multi-user session isolation in `apps/web/app.py` — verify `gr.State()` is per-browser-tab (Gradio 4.x isolation), `CampaignSession` does not leak across concurrent user sessions, `PRAGMA journal_mode=WAL` is active for concurrent SQLite writers (from packages/storage/sqlite/)
- [ ] T056 [P] [US5] Create `tests/integration/test_shared_campaign.py` — GM logs public event → Player refresh sees it in story history (US5 scenario 2); GM creates private NPC note → Player cannot see it (US5 scenario 1); concurrent GM + Player actions produce no data corruption (US5 scenario 3)

**Checkpoint**: US5 is fully functional. Multi-user shared campaign works correctly with role-scoped visibility and refresh-based sync.

---

## Phase 8: User Story 6 — GM Session Planning (Priority: P4)

**Goal**: GM uses a dedicated planning tool to prepare for sessions, drawing on story history and conversing with a planning agent; plans persist and are editable.

**Independent Test**: With ≥1 completed session in story history, request a session plan and verify it references specific past events and open plot threads.

- [ ] T057 [US6] Implement `generate_session_plan` tool in `packages/agents/gm_agent/` — LLM call with full story history context, `focus_hints` from GM, `GenerateSessionPlanInput`/`GenerateSessionPlanOutput` schemas; when history is empty, return starter plan with note that history is minimal (US6 acceptance scenario 3)
- [ ] T058 [US6] Create `apps/web/pages/gm/session_plan.py` — session selector `gr.Dropdown`, generate plan `gr.Button` (`interactive=False` in degraded mode), `gr.Code` markdown plan editor, save to `SessionPlan` (persists content + updates `updated_at`), live `gr.Markdown` preview, planning unavailable notice
- [ ] T059 [P] [US6] Create `tests/integration/test_session_planning.py` — US6 scenario 1 (plan references past events and plot threads); scenario 2 (GM edits persisted, available on next open); scenario 3 (empty-history produces usable starter plan with minimal-history note)
- [ ] T060 [P] [US6] Create `harness/scenarios/session_planning/` — YAML scenario fixtures for `generate_session_plan`: single-session history produces plan that cites that session's events by content; multi-session history produces plan referencing `event_type=plot_thread_opened` events; empty history returns starter plan containing the minimal-history note (covers all three US6 acceptance scenarios deterministically)

**Checkpoint**: US6 is fully functional. GM session planning tool generates context-aware plans, persists edits, and handles empty history gracefully. Harness scenarios cover all US6 acceptance scenarios (Constitution Principle V).

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Cloud provider implementations, RAG layer, full demo validation (SC-001, SC-002, SC-003), and final quality pass.

- [ ] T061 [P] Create `packages/llm/providers/anthropic.py`, `packages/llm/providers/openai.py`, `packages/llm/providers/huggingface.py` — cloud LLM provider implementations conforming to `LLMProvider` ABC; switched via `LLM_PROVIDER` env var (cloud M5+)
- [ ] T062 [P] Create `packages/storage/postgres/` — Postgres adapter using `asyncpg` via SQLAlchemy async engine; same `StorageBackend` ABC as SQLite adapter; DB URL from `packages/core/config.py`
- [ ] T063 [P] Create `packages/rag/interface.py` — `Retriever` ABC; create `packages/rag/history/` (ChromaDB-backed campaign event index; local embedding via Ollama `nomic-embed-text`; cloud override via `EMBEDDING_PROVIDER` env var), `packages/rag/character/` (character profile index for twin grounding), `packages/rag/rules/` (Earthdawn mechanics index)
- [ ] T064 Wire RAG semantic retrieval into `packages/agents/twin/tools.py` — `recall_story_events` uses `packages/rag/history/` for semantic search when available, falls back to SQL chronological query when RAG is unavailable
- [ ] T065 [P] Finalize `deploy/compose/docker-compose.local.yml` (web + ollama + chromadb + SQLite volume) and `deploy/compose/docker-compose.cloud.yml` (web + postgres + pgvector + cloud LLM env vars)
- [ ] T066 [P] Run full M1–M4 quickstart.md validation sequence in local Docker mode (`docker compose -f deploy/compose/docker-compose.local.yml up`) to confirm SC-001, SC-002, SC-003 pass
- [ ] T067 [P] Final `uv run ruff check .` and `uv run pyright` pass; update `README.md` with current architecture, milestone map, and developer setup instructions

**Checkpoint**: Full end-to-end demo runs in both local and cloud Docker modes. Provider swap via `.env` requires no code changes (SC-003). All harness scenarios pass.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 completion — **BLOCKS all user stories**
- **User Stories (Phases 3–8)**: All depend on Foundational phase
  - US1 (P1) and US2 (P2) can be worked in parallel after Phase 2
  - US3 (P2) depends on Phase 2 only; can parallel with US1 and US2
  - US4 (P3) depends on Phase 2; image wiring tasks (T050, T051, T052) require US1 and US2 pages to exist first
  - US5 (P3) depends on the shared session infrastructure from Phases 2–5
  - US6 (P4) depends on US3 (story history must exist as planning context)
- **Polish (Phase 9)**: Depends on all user stories complete

### User Story Dependencies

- **US1 (P1)**: Can start after Phase 2 — no US dependency
- **US2 (P2)**: Can start after Phase 2 — no US dependency
- **US3 (P2)**: Can start after Phase 2 — no US dependency
- **US4 (P3)**: Can start after Phase 2; wire-up tasks (T050, T051, T052) require US1 and US2 pages to exist
- **US5 (P3)**: Can start after Phases 2–5 to exercise the integrated system
- **US6 (P4)**: Depends on US3 (story history as planning context)

### Within Each User Story

- Models/schemas before services
- Services before agent tools
- Agent tools before UI pages
- Wiring tasks (T050, T051, T052) after both the imagegen package and the target UI page are complete
- Story complete before advancing to lower priority

### Parallel Opportunities

Within each phase, all tasks marked `[P]` can be executed in parallel.

Across phases (once Phase 2 is complete):
- US1 and US2 can run in parallel
- US3 can run in parallel with US1 and US2
- US4 package creation (T046–T049) can begin once Phase 2 is done; wire-up tasks (T050–T052) require US1 and US2 pages

---

## Parallel Example: User Story 1

```bash
# These US1 tasks can run in parallel (different files, no cross-dependency):
T020: packages/rules_earthdawn/data/
T021: packages/rules_earthdawn/character_builder.py
T022: packages/rules_earthdawn/validator.py
T025: packages/agents/twin/tools.py
T028: harness/scenarios/twin_dialogue/
T030: tests/integration/test_character_creation.py
T031: tests/integration/test_degraded_mode.py

# Then sequentially (dependencies):
T023: apps/web/pages/player/character.py  (needs T020–T022)
T024: packages/agents/twin/agent.py       (needs T015, T016)
T026: apps/web/pages/player/twin_chat.py  (needs T024, T025)
T027: max-turns pruning in twin/agent.py  (needs T024, T026)
T029: harness/scoring/rubrics.py          (needs T028)
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL — blocks everything)
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: `uv run pytest tests/integration/test_character_creation.py -v` passes; run quickstart.md M1 and M2 validations manually
5. Demo US1: create character → view sheet → converse with twin → out-of-character prompt handled gracefully

### Incremental Delivery

1. Phase 1 + Phase 2 → Foundation ready
2. Phase 3 (US1) → Test independently → **MVP demo**
3. Phase 4 (US2) + Phase 5 (US3) → Test independently → Core demo eligible
4. Phase 6 (US4) → Image generation demo
5. Phase 7 (US5) → Shared campaign demo
6. Phase 8 (US6) → Full feature demo
7. Phase 9 → Polish → Full M5 demo in both deployment modes

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup + Foundational together
2. Once Foundational is done:
   - Developer A: User Story 1
   - Developer B: User Story 2
   - Developer C: User Story 3
3. Stories complete and integrate independently

---

## Notes

- `[P]` tasks write to different files with no shared in-phase dependencies — safe to parallelize
- `[US#]` label maps task to a specific user story from spec.md for traceability (SC-005)
- Each user story phase is independently completable and testable
- Integration tests are included because quickstart.md and spec explicitly call out automated test assertions (SC-004, SC-008)
- Harness scenarios (T028, T029, T038, T039, T044, T053, T060) satisfy Constitution Principle V — every agent and tool must have eval coverage before milestone completion
- `ADR-005-agent-framework.md` (T007) must be written before any M2 work begins (plan.md open compliance item)
- `max_twin_turns` pruning (T027) prevents unbounded `DigitalTwin.conversation_history` from exceeding LLM context window limits
- Scene illustration wiring (T052) satisfies FR-005 and US4 acceptance scenario 2 — GM generates scene art from a text description via `gm/history.py`
- `PlayerNPCSchema` (T011) defines the Player-visible NPC field set, ensuring `gm_notes` is never leaked to Player-role responses
- Ollama `nomic-embed-text` is the local embedding provider for RAG (T063); `EMBEDDING_PROVIDER` env var enables cloud override per Constitution Principle IV
- Avoid: vague tasks, same-file conflicts between parallel tasks, cross-story dependencies that break story independence
- Stop at each phase checkpoint to validate before moving to the next priority