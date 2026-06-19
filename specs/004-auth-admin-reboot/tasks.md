# Tasks: Auth & Admin Reboot

**Input**: Design documents from `/specs/004-auth-admin-reboot/`

**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ui-contract.md ✅, quickstart.md ✅

**Tests**: No test tasks included — none explicitly requested in the feature specification.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

**Constitution**: Principle VII (Placeholder-First & Explicit Failures) applies throughout — every new UI surface MUST render a visible stub before real logic is wired in.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Confirm the foundational files are in the right shape before any user story work begins.

- [ ] T001 Audit `apps/web/app.py` and ensure it can be launched as a pure Gradio app with `gr.Blocks().launch()` — document anything blocking a clean launch
- [ ] T002 Verify `packages/core/core/schemas.py` defines `UserInfo` (user_id, username) and `CampaignSession` (campaign_id, display_name, role, join_code, ai_available) dataclasses; add or correct them if missing
- [ ] T003 [P] Verify `packages/storage/storage/users.py` has stub functions for `get_user_by_username()`, `create_user()`, `get_campaign_by_join_code()`, and `get_or_create_player()`; add missing stubs with `raise NotImplementedError` bodies

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [ ] T004 Implement `apps/web/services/auth.py` with two functions: `sign_in(username, password) -> UserInfo | str` (returns `UserInfo` on success, error string on failure) and `register(username, email, password, confirm_password) -> UserInfo | str`; both functions MUST return visible error strings — never raise exceptions to the UI layer
- [ ] T005 [P] Implement repository helpers in `packages/storage/storage/users.py`: `get_user_by_username(username) -> User | None`, `create_user(username, email, hashed_password) -> User`, `get_campaign_by_join_code(join_code) -> Campaign | None`, `get_or_create_player(campaign_id, player_name) -> Player`; use SQLAlchemy 2.x session patterns and SQLite-compatible upsert semantics
- [ ] T006 [P] Implement campaign repository helpers in `packages/storage/storage/users.py`: `get_campaigns_for_user(user_id) -> list[Campaign]`, `create_campaign(owner_id, name, game_system) -> Campaign | str` (returns error string on duplicate name)
- [ ] T007 Rewrite `apps/web/app.py` to use `gr.Blocks().launch()` as the sole app entry point with three top-level panels: auth screen, player join screen, GM campaign dashboard — each panel rendered as a visible placeholder stub per Principle VII (e.g., `gr.Markdown("Sign In — not yet implemented")`)
- [ ] T008 Add `gr.State()` objects to `apps/web/app.py` for `user_state` (holds `UserInfo | None`) and `session_state` (holds `CampaignSession | None`); wire tab visibility so auth screen is shown when `user_state` is None and campaign dashboard is shown when `user_state` is set

**Checkpoint**: App launches with `uv run python apps/web/app.py`, shows placeholder panels, and `gr.State` objects are in place.

---

## Phase 3: User Story 1 — GM Signs In and Reaches Their Campaign Dashboard (Priority: P1) 🎯 MVP

**Goal**: A GM can create an account and sign in from the auth screen, then immediately see their campaign dashboard. All errors appear in the UI.

**Independent Test**: Open the app in a fresh browser, use Create Account to register, verify the campaign dashboard appears immediately. Close and reopen, sign in with the same credentials, confirm the campaign list is shown. Test wrong password and duplicate username — both must show visible errors, not console-only messages.

### Implementation for User Story 1

- [ ] T009 [US1] Implement `apps/web/pages/auth.py` Sign In tab: `gr.Textbox` for username and password (password type), Sign In button, and a `gr.Markdown` for `login_status` error output; wire sign-in button to call `sign_in()` from `apps/web/services/auth.py` and update `user_state` on success
- [ ] T010 [US1] Implement `apps/web/pages/auth.py` Create Account tab: `gr.Textbox` components for username, email, password, confirm_password, a Register button, and a `gr.Markdown` for `reg_status` output; wire register button to `register()` and on success populate `user_state` and transition directly to campaign dashboard (no additional sign-in step)
- [ ] T011 [US1] Implement sign-out handler in `apps/web/app.py`: clear `user_state` and `session_state` to `None` and return the UI to the auth screen
- [ ] T012 [P] [US1] Implement `apps/web/pages/admin/campaigns.py` campaign list view: `gr.DataFrame` showing `[Name, Join Code, Created]` columns populated from `get_campaigns_for_user(user_id)`, a `gr.Textbox` for campaign name, a `gr.Dropdown` for game system, and a Create Campaign button
- [ ] T013 [US1] Add create campaign handler in `apps/web/pages/admin/campaigns.py`: call `create_campaign()`, display a visible `gr.Markdown` error when the name is a duplicate (case-insensitive per owner), and refresh the campaign table on success
- [ ] T014 [US1] Add row selection and Resume Campaign button in `apps/web/pages/admin/campaigns.py`: on click, call `get_campaigns_for_user()` to resolve the selected campaign, populate `session_state` with `CampaignSession(role="gm")`, and transition the UI to the GM dashboard placeholder

**Checkpoint**: GM can create account → see (empty) campaign table → create a campaign → resume it. Sign-out returns to auth screen. Wrong password or duplicate username shows visible UI error.

---

## Phase 4: User Story 2 — Player Joins a Campaign with Just a Join Code (Priority: P1)

**Goal**: A player enters only a join code and their player name to reach their player dashboard. Returning players get the same record back.

**Independent Test**: As GM, copy the 6-character join code from the campaign detail. In a separate browser tab, enter the join code and a player name — player dashboard appears. Close and reopen, enter the same two values — same player state is restored. Test invalid join code and empty fields — both show visible inline errors.

### Implementation for User Story 2

- [ ] T015 [US2] Rewrite `apps/web/pages/landing.py` to show exactly two inputs — `gr.Textbox` for `join_code` and `gr.Textbox` for `player_name` — removing any campaign name field; add a Join Campaign button and a `gr.Markdown` for `join_status` output
- [ ] T016 [US2] Implement player join handler in `apps/web/pages/landing.py`: validate both fields are non-empty (show field-specific inline error if either is empty), call `get_campaign_by_join_code()`, return `"No campaign found with that join code."` as a visible `join_status` message on failure
- [ ] T017 [US2] On successful join code lookup, call `get_or_create_player(campaign_id, player_name)` from `packages/storage/storage/users.py`, populate `session_state` with `CampaignSession(role="player")`, and transition the UI to the player dashboard placeholder

**Checkpoint**: Player can enter join code + player name → reach player dashboard. Returning with same two values restores the same record. Invalid code and empty fields each show a distinct visible error.

---

## Phase 5: User Story 3 — GM Runs a Campaign Session with All Tools Accessible (Priority: P1)

**Goal**: An authenticated GM can navigate all campaign tools from the GM dashboard — Characters, NPCs, Story History, World Notes, Session Plan — and each tab either works or shows a clear placeholder.

**Independent Test**: Enter a campaign as GM. Navigate each tab. Create one NPC, log one story event, write one world note. If Ollama is running, send a twin chat message; if not, verify "AI service unavailable" appears. If any tab fails to load, verify an inline error message appears (no silent blank or crash).

### Implementation for User Story 3

- [ ] T018 [US3] Implement `apps/web/pages/gm/` layout in a new `apps/web/pages/gm/__init__.py` or `dashboard.py`: `gr.TabbedInterface` with tabs for Characters, NPCs, Story History, World Notes, Session Plan — each tab renders a visible `gr.Markdown` placeholder stub per Principle VII
- [ ] T019 [P] [US3] Add join code display at the top of the GM dashboard in `apps/web/pages/gm/dashboard.py`: a read-only `gr.Textbox` pre-populated from `CampaignSession.join_code` with a label "Campaign Join Code (share with players)"
- [ ] T020 [P] [US3] Implement NPCs tab in `apps/web/pages/gm/`: `gr.Textbox` inputs for name, role, personality; a Save NPC button; a `gr.DataFrame` listing current NPCs; save handler must call upsert logic (case-insensitive name per campaign) and show success or error in a `gr.Markdown` status output
- [ ] T021 [P] [US3] Implement Story History tab in `apps/web/pages/gm/`: `gr.Textbox` for event content, a Log Event button, and a `gr.DataFrame` or `gr.Markdown` list showing events in order; handler adds a `StoryEvent` row and refreshes the list immediately
- [ ] T022 [US3] Implement NPC Twin Chat tab in `apps/web/pages/gm/`: when `CampaignSession.ai_available` is `False`, display `gr.Markdown("AI service unavailable — check that Ollama is running")` and disable the chat input; when `True`, wire the `gr.Chatbot` to the Ollama provider and surface any provider errors visibly
- [ ] T023 [US3] Implement Session Plan tab in `apps/web/pages/gm/`: when the AI planner is unavailable, display `gr.Markdown("Session planning assistant unavailable — check that Ollama is running")` as the tab body; when available, provide a text area for manual notes and a Generate Plan button
- [ ] T024 [US3] Add a centralized error display pattern across all GM dashboard tab handlers in `apps/web/pages/gm/`: wrap each event handler in a try/except that catches all exceptions and returns a human-readable `gr.Markdown` error (never `except: pass`, never log-only)

**Checkpoint**: All five GM tabs render without crashing. Join code visible at top. NPC and story event saves work. AI-dependent tabs show placeholders when Ollama is unavailable. Any tab error shows in-page message.

---

## Phase 6: User Story 4 — Player Uses the Player Dashboard Tools (Priority: P1)

**Goal**: A player in an active session can view/edit their character, read story history, and chat with their twin — or see a clear unavailable state for AI features.

**Independent Test**: Join a campaign as a player. Navigate Character, Twin Chat, and History tabs. Fill in and save character details. View history. If Ollama is available, send a twin chat message and verify a response. If not, verify the "AI unavailable" message appears. Rejoin with same join code and player name — character edits must be persisted.

### Implementation for User Story 4

- [ ] T025 [US4] Implement `apps/web/pages/player/` layout in `apps/web/pages/player/__init__.py` or `dashboard.py`: `gr.TabbedInterface` with Character, Twin Chat, and Story History tabs — each tab renders a visible `gr.Markdown` placeholder stub per Principle VII
- [ ] T026 [P] [US4] Implement Character tab in `apps/web/pages/player/`: `gr.Textbox` inputs for name, race, discipline, background, personality; a Save Character button; handler calls upsert logic (case-insensitive name per campaign) and displays success or error in a `gr.Markdown` status output; character data is pre-loaded from the existing `Player.character_id` record on tab render
- [ ] T027 [P] [US4] Implement Story History tab in `apps/web/pages/player/`: a read-only `gr.DataFrame` or `gr.Markdown` listing all public `StoryEvent` rows for the campaign in chronological order by `event_order`
- [ ] T028 [US4] Implement Twin Chat tab in `apps/web/pages/player/`: when `CampaignSession.ai_available` is `False`, display `gr.Markdown("AI service unavailable — check that Ollama is running")` and disable the chat input; when `True`, wire the `gr.Chatbot` to the Ollama provider using the player's `DigitalTwin` conversation history; surface any provider errors visibly

**Checkpoint**: All three player tabs render without crashing. Character save is persisted. Story history lists campaign events. Twin chat shows AI-unavailable placeholder when Ollama is down. Rejoining with same credentials restores saved character.

---

## Phase 7: User Story 5 — Image Generation is Accessible as a Named Feature (Priority: P2)

**Goal**: GMs and players can see and trigger portrait generation for NPCs and characters. When ComfyUI is unavailable, a clear placeholder is shown — the control is never hidden.

**Independent Test**: Navigate to an NPC with a physical description and click Generate Portrait. If ComfyUI is running, a portrait appears and is saved. If not, `"Image generation unavailable — check that ComfyUI is running"` is visible and the existing portrait (or a placeholder icon) is retained. Any image generation error shows visibly in the UI.

### Implementation for User Story 5

- [ ] T029 [P] [US5] Add a "Generate Portrait" button and `gr.Image` display to the NPC tab in `apps/web/pages/gm/` and to the Character tab in `apps/web/pages/player/`; when the ComfyUI service is unavailable, the button is visible but disabled and a `gr.Markdown` reads `"Image generation unavailable — check that ComfyUI is running"`
- [ ] T030 [US5] Implement portrait generation handler for both NPC and Character tabs: call the ComfyUI/image generation provider when available, display the returned image in the `gr.Image` component and persist `portrait_url` on the entity; catch and display all provider errors visibly in a `gr.Markdown` status output — never swallow exceptions

**Checkpoint**: Generate Portrait button is visible on NPC and Character tabs regardless of service availability. When ComfyUI is down, a clear placeholder message appears. When up, a portrait is generated and saved.

---

## Phase 8: User Story 6 — Stale Spec Artifacts are Cleaned Up (Priority: P3)

**Goal**: No open tasks in `/specs` reference the old FastAPI entrypoint, bcrypt threading, or the three-field player join form. The README reflects the current Gradio-only, simplified auth architecture.

**Independent Test**: Read all open `tasks.md` files in `/specs`. Confirm none reference `uvicorn`, `main:app`, or a three-field player join. Read `README.md` — confirm it describes `uv run python apps/web/app.py` as the launch command and a two-field player join.

### Implementation for User Story 6

- [ ] T031 [US6] Scan all `tasks.md` files under `/specs` (002 and 003) and mark any open task referencing FastAPI-based launching (`uvicorn`, `main:app`), bcrypt threading, or the three-field player join form as `[SUPERSEDED]` with a one-line note explaining the superseding feature
- [ ] T032 [US6] Update `README.md` to accurately describe: Gradio-only launch (`uv run python apps/web/app.py` from `apps/web/`), simplified mock auth backed by SQLite, two-field player join (join code + player name), and current known limitations (no OAuth, no mobile optimization, AI services are optional)

**Checkpoint**: No open tasks in `/specs` reference the old entrypoints. README launch command and join flow description are accurate.

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Verification and cross-cutting quality checks that span all user stories.

- [ ] T033 [P] Run quickstart.md validation scenarios against the running app: GM auth flow, campaign creation and join code display, player join flow, player rejoin persistence, AI degradation (all five scenarios must pass)
- [ ] T034 Verify all GM and player dashboard tabs render without crashing when both Ollama and ComfyUI are unavailable — every AI-dependent component must show a visible placeholder, not a blank panel or Python traceback
- [ ] T035 [P] Run `ruff check apps/web/ packages/core/ packages/storage/` and `pyright apps/web/ packages/core/ packages/storage/` and resolve all reported errors

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion — BLOCKS all user stories
- **User Stories (Phases 3–8)**: All depend on Foundational phase completion
  - US1–US4 (P1) can proceed in priority order or in parallel if capacity allows
  - US5 (P2) depends on US3 and US4 completing their portrait-capable tabs
  - US6 (P3) is independent and can be done after any P1 story is complete
- **Polish (Phase 9)**: Depends on all desired user stories being complete

### User Story Dependencies

- **US1 (P1)**: Can start after Phase 2 — auth screen and campaign dashboard are independent of all other stories
- **US2 (P1)**: Can start after Phase 2 — player join is independent of US1
- **US3 (P1)**: Depends on US1 (GM must be authenticated to enter a campaign)
- **US4 (P1)**: Depends on US2 (player must have joined to use the dashboard)
- **US5 (P2)**: Depends on US3 and US4 (portrait button lives inside GM and Player dashboard tabs)
- **US6 (P3)**: Independent of code changes — can be done any time after US1 is complete

### Within Each User Story

- Models/schemas before services
- Services/repository helpers before UI handlers
- Placeholder stubs before real logic (Principle VII — mandatory)
- Story complete and checkpoint validated before moving to next priority

### Parallel Opportunities

- T003, T005, T006 can run in parallel (different files in Phase 2)
- T012 can run in parallel with T009–T011 (different files in US1)
- T019, T020, T021 can run in parallel (different tabs in US3)
- T026, T027 can run in parallel (different tabs in US4)
- T029 can run in parallel across NPC and Character tabs (US5)
- T033, T035 can run in parallel (Phase 9)

---

## Parallel Example: User Story 3 (GM Dashboard Tabs)

```
# Once T018 (GM dashboard layout) is done, these can run in parallel:
T019 — Join code display at top of dashboard
T020 — NPCs tab implementation
T021 — Story History tab implementation
# T022 (Twin Chat) and T023 (Session Plan) depend on ai_available pattern from T018
```

---

## Implementation Strategy

### MVP First (User Stories 1 + 2 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL — blocks all stories)
3. Complete Phase 3: User Story 1 (GM Sign In + Campaign Dashboard)
4. Complete Phase 4: User Story 2 (Player Join)
5. **STOP and VALIDATE**: Auth screen works, player join works, campaign creates with join code
6. Demo if ready — core loop is now functional

### Incremental Delivery

1. Setup + Foundational → app launches with placeholder stubs
2. US1 → GM can sign in and manage campaigns → demo-able for GMs
3. US2 → Players can join → end-to-end loop demo-able
4. US3 + US4 → all dashboard tools accessible → full feature demo
5. US5 → portrait generation visible → AI feature showcase
6. US6 → spec hygiene → dev team quality

---

## Notes

- [P] tasks = different files, no shared state dependencies
- [Story] label maps task to specific user story for traceability
- Principle VII requires visible placeholder stubs BEFORE real logic — T007 and T018/T025 enforce this
- Upsert semantics apply to Character, NPC, and Player saves (case-insensitive name per campaign)
- `gr.State` is the only session mechanism — no JWT, no cookies, no server-side session store
- App entry point is `apps/web/app.py` via `uv run python app.py` — `apps/web/main.py` is retained for compatibility but is not the standard runtime
