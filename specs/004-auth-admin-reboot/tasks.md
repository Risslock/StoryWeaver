# Tasks: Auth & Admin Reboot

**Input**: Design documents from `/specs/004-auth-admin-reboot/`

**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ui-contract.md ✅, quickstart.md ✅

**Tests**: No test tasks included — none explicitly requested in the feature specification.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

**Constitution**: Principle VII (Placeholder-First & Explicit Failures) applies throughout — every new UI surface MUST render a visible stub before real logic is wired in.

**Note (2026-06-20 clarification)**: Decisions reached in the clarification session on 2026-06-20 require reworking the player join flow and the post-login navigation. Prior tasks that implemented the old anonymous join flow (T016–T018) and the old direct-to-admin routing (T007–T008) are marked with ⚠️ SUPERSEDED where their implementation conflicts with the new design. New tasks T039+ address all 2026-06-20 changes.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Confirm the foundational files are in the right shape before any user story work begins.

- [x] T001 Audit `apps/web/app.py` and ensure it can be launched as a pure Gradio app with `gr.Blocks().launch()` — document anything blocking a clean launch
- [x] T002 Verify `packages/core/core/schemas.py` defines `UserInfo` (user_id, username) and `CampaignSession` (campaign_id, display_name, role, join_code, ai_available) dataclasses; add or correct them if missing ⚠️ SUPERSEDED by T039 — `CampaignSession` also needs `user_id: UUID`
- [x] T003 [P] Verify `packages/storage/storage/users.py` has stub functions for `get_user_by_username()`, `create_user()`, `get_campaign_by_join_code()`, and `get_or_create_player()`; add missing stubs with `raise NotImplementedError` bodies

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [x] T004 Implement `apps/web/services/auth.py` with `hash_password()` and `verify_password()` using `hashlib.sha256`; `validate_user(backend, identifier, password) -> bool`; `register_user(backend, username, email, password) -> tuple[bool, str]`; no bcrypt dependency; errors returned as strings, never raised to UI
- [x] T005 [P] Implement repository helpers in `packages/storage/storage/users.py`: `get_user_by_username_or_email(session, identifier) -> User | None`, `create_user(session, username, email, hashed_password) -> User`, `get_campaign_by_join_code(session, join_code) -> Campaign | None`; use SQLAlchemy 2.x async session patterns ⚠️ SUPERSEDED for `get_or_create_player` — see T041
- [x] T006 [P] Implement campaign repository helpers in `packages/storage/storage/users.py`: `get_campaigns_for_user(session, user_id) -> list[Campaign]` (excludes archived), `archive_campaign(session, campaign_id) -> None`; all campaign list queries MUST filter out archived campaigns by default
- [x] T007 Rewrite `apps/web/app.py` to use `gr.Blocks().launch()` as the sole app entry point ⚠️ SUPERSEDED by T044–T046 — app.py needs a hub_col between auth and campaign screens
- [x] T008 Add `gr.State()` objects to `apps/web/app.py` for `user_state` and `session_state`; wire tab visibility so auth screen is shown when `user_state` is None ⚠️ SUPERSEDED by T044 — `_navigate()` needs a hub state between auth and the GM/Player panels
- [x] T039 [P] Add `user_id: UUID` field to `CampaignSession` dataclass in `packages/core/core/schemas.py` — player dashboard pages will use this to query Player records by `(campaign_id, user_id)` instead of display name
- [x] T040 Write Alembic migration `packages/core/core/migrations/versions/0004_player_user_link.py`: add `user_id UUID REFERENCES users(id) ON DELETE RESTRICT` column to `players` table (nullable for migration safety); drop `ix_players_campaign_player_name_lower` unique index; add `ix_players_campaign_user` unique index on `(campaign_id, user_id)`; run `uv run alembic upgrade head` to apply
- [x] T041 Update `get_or_create_player()` in `packages/storage/storage/users.py` to signature `(session, campaign_id, user_id, username) -> Player`: match on `(campaign_id, user_id)` instead of player_name; populate `player_name = username` on creation; existing callers in `apps/web/pages/landing.py` and `apps/web/pages/player/join.py` must be updated
- [x] T042 [P] Add `get_campaigns_for_player(session, user_id) -> list[Campaign]` to `packages/storage/storage/users.py`: join `Player` on `Campaign` where `Player.user_id == user_id` and `Campaign.archived == False`; return newest first — used by the player join screen's previously-joined campaigns list
- [x] T043 Move `get_backend()` SQLiteBackend singleton from `apps/web/pages/landing.py` to `apps/web/services/db.py`; update all existing import references in `apps/web/pages/auth.py` and `apps/web/pages/admin/campaigns.py`

**Checkpoint**: Migration applied, `get_or_create_player()` uses `user_id`, `CampaignSession` carries `user_id`, `get_backend()` lives in `services/db.py`. App still launches with `uv run python apps/web/app.py`.

---

## Phase 3: User Story 1 — GM Signs In and Reaches Their Campaign Dashboard (Priority: P1) 🎯 MVP

**Goal**: A GM can create an account and sign in from the auth screen, then see the post-login hub, navigate to "My Campaigns (GM)", and immediately see their campaign dashboard. All errors appear in the UI. GMs can create, resume, and archive campaigns.

**Independent Test**: Open the app, use Create Account to register, verify the hub screen appears, click "My Campaigns (GM)", verify the campaign dashboard appears. Sign out and sign in — hub appears again. Test wrong password and duplicate username — both must show visible UI errors.

### Implementation for User Story 1

- [x] T009 [US1] Implement `apps/web/pages/auth.py` Sign In tab: `gr.Textbox` for username and password, Sign In button, `gr.Markdown` for `login_status`; wire to `validate_user()` and populate `user_state` on success
- [x] T010 [US1] Implement `apps/web/pages/auth.py` Create Account tab: `gr.Textbox` for username, email, password, confirm_password; wire to `register_user()` and populate `user_state` on success — no additional sign-in step after registration
- [x] T011 [US1] Implement sign-out handler in `apps/web/app.py`: clear `user_state` and `session_state` to `None` and return the UI to the auth screen
- [x] T044 [US1] Add `hub_col` to `apps/web/app.py` navigation state machine: update `_navigate()` so when `user_state` is set and `session_state` is None the hub screen is shown (replacing the current direct transition to `admin_col`); `hub_col` is a new `gr.Column` containing only the hub navigation content (built inline or via `pages/hub.py`)
- [x] T045 [P] [US1] Build hub screen content inside `hub_col` in `apps/web/app.py`: a "My Campaigns (GM)" `gr.Button` (wired to show `gm_campaigns_col`), a "Join a Campaign (Player)" `gr.Button` (wired to show `player_join_col`), and a "Sign Out" button; all transitions must update both `session_state` and the visible panel without a page reload
- [x] T046 [US1] Create `apps/web/pages/gm/campaigns.py` by moving all code from `apps/web/pages/admin/campaigns.py`, updating the import of `get_backend` to `from services.db import get_backend`; update `apps/web/app.py` to import `CampaignPageRefs`, `build_campaigns_page`, `load_campaigns_for_user`, and `resume_campaign` from `pages.gm.campaigns`; delete `apps/web/pages/admin/campaigns.py`
- [x] T012 [P] [US1] Campaign list view in `apps/web/pages/admin/campaigns.py` (now `pages/gm/campaigns.py` after T046): `gr.Dataframe` showing `[Name, Join Code, Created]` columns; campaign name textbox; game system dropdown; Create Campaign button ⚠️ Completed in old path — T046 moves this to the canonical path
- [x] T013 [US1] Create campaign handler: calls `create_campaign()`, shows visible `gr.Markdown` error on duplicate name, refreshes table on success
- [x] T014 [US1] Archive campaign handler: calls `archive_campaign(campaign_id)`, shows visible confirmation, refreshes table; no data deleted
- [x] T015 [US1] Row selection and Resume Campaign button: resolves selected campaign, populates `session_state` with `CampaignSession(role="gm", user_id=user_state.user_id)`, navigates to GM dashboard

**Checkpoint**: GM can register → see hub → click "My Campaigns" → see campaign list → create a campaign → resume it → archive it (disappears). Sign-out returns to auth screen. Wrong password and duplicate username show visible UI errors.

---

## Phase 4: User Story 2 — Player Creates an Account Then Joins a Campaign (Priority: P1)

**Goal**: All users must authenticate before joining a campaign. After auth, the hub offers "Join a Campaign (Player)". A new player enters only the join code — player name is set from their username. A returning player sees their previously joined campaigns and can re-enter with one click.

**Independent Test**: Create a player account. From the hub, click "Join a Campaign (Player)". Enter a valid join code (no player name field visible). Verify player dashboard appears with display name matching account username. Sign out and sign in; verify the campaign appears in the joined-campaigns list. Click it — player dashboard loads without re-entering the join code. Test invalid join code and empty join code — both show distinct visible errors.

### Implementation for User Story 2

- [x] T016 [US2] Rewrite `apps/web/pages/landing.py` to show `join_code` and `player_name` inputs ⚠️ SUPERSEDED by T047–T050 — anonymous join is removed; new flow in `pages/player/join.py`
- [x] T017 [US2] Player join handler in `landing.py` ⚠️ SUPERSEDED by T048 — handler now uses `user_state.user_id` as identity
- [x] T018 [US2] Populate `CampaignSession(role="player")` on join ⚠️ SUPERSEDED by T048 — `CampaignSession` now also carries `user_id`
- [x] T047 [P] [US2] Create `apps/web/pages/player/join.py` with two sections: (1) a `gr.DataFrame` listing campaigns the user has already joined (columns: Name, Join Code; populated from `get_campaigns_for_player(user_id)` when the join screen is entered); (2) a `gr.Textbox` for join code only — NO player_name input — with a "Join Campaign" `gr.Button` and `gr.Markdown` for `join_status`; stub all event handlers per Principle VII before wiring real logic
- [x] T048 [US2] Implement new-campaign join handler in `apps/web/pages/player/join.py`: validate join code is non-empty (show field-specific error if empty); call `get_campaign_by_join_code(session, join_code)`; on not found show visible "No campaign found with that join code."; on success call `get_or_create_player(session, campaign_id, user_id=user_state.user_id, username=user_state.username)` and populate `CampaignSession(role="player", user_id=user_state.user_id, campaign_id=..., display_name=user_state.username, join_code=...)`
- [x] T049 [US2] Implement previously-joined campaign click handler in `apps/web/pages/player/join.py`: clicking a row in the joined-campaigns `gr.DataFrame` loads the campaign and populates `CampaignSession(role="player", user_id=user_state.user_id, ...)` without requiring join code re-entry; mirrors the GM's resume flow
- [x] T050 [US2] Delete `apps/web/pages/landing.py`; update `apps/web/app.py` to import the player join screen builder from `pages.player.join`; verify no remaining import references to `pages.landing` exist in any file

**Checkpoint**: No player name input exists in the join form. Player display name matches account username. New join via join code creates a Player record linked to the authenticated user. Returning player sees their joined campaigns list and can re-enter with one click. Invalid or empty join code shows distinct visible errors. No anonymous join path exists.

---

## Phase 5: User Story 3 — GM Runs a Campaign Session with All Tools Accessible (Priority: P1)

**Goal**: An authenticated GM can navigate all campaign tools from the GM dashboard — Characters, NPCs, Story History, World Notes, Session Plan, Players — and each tab either works or shows a clear placeholder.

**Independent Test**: Enter a campaign as GM. Navigate each tab. Create one NPC, create a session, log one story event under it, write one world note, check the Players list. If Ollama is running, send a twin chat message; if not, verify "AI service unavailable" appears. If any tab fails to load, verify an inline error message appears (no silent blank or crash).

### Implementation for User Story 3

- [x] T019 [US3] Implement GM dashboard layout: `gr.TabbedInterface` with visible stub tabs for Characters, NPCs, Story History, World Notes, Session Plan, and Players per Principle VII
- [x] T020 [P] [US3] Join code display at top of GM dashboard: read-only `gr.Textbox` pre-populated from `CampaignSession.join_code` with label "Campaign Join Code — share with players"
- [x] T021 [P] [US3] NPCs tab in `apps/web/pages/gm/npcs.py`: name/role/personality inputs, Save NPC button, `gr.DataFrame` NPC list; upsert on case-insensitive name per campaign; visible status output
- [x] T022 [US3] Story History tab in `apps/web/pages/gm/history.py`: session creation form (title, date); session dropdown for event logging; event description textbox with Log Event button; history view grouped by session header chronologically; all handlers show visible status messages
- [x] T023 [US3] World Notes tab in `apps/web/pages/gm/world_notes.py`: `gr.Textbox` (lines=20) for Markdown input, Save Notes button, `gr.Markdown` live preview; handler writes to `Campaign.world_notes` and shows visible save confirmation or error
- [x] T024 [US3] NPC Twin Chat tab in `apps/web/pages/gm/`: shows "AI service unavailable — check that Ollama is running" when `CampaignSession.ai_available` is False; wired to Ollama provider when True; all provider errors displayed visibly
- [x] T025 [US3] Session Plan tab in `apps/web/pages/gm/session_plan.py`: "Session planning assistant unavailable — check that Ollama is running" when AI is down; manual notes area and Generate Plan button when available
- [x] T026 [US3] Players tab in `apps/web/pages/gm/players.py`: read-only `gr.DataFrame` with `[Player Name, Character Name]` columns; character name shows "—" if none; no edit or remove actions
- [x] T027 [US3] Centralized error pattern across all GM dashboard handlers: every event handler wrapped in try/except returning human-readable `gr.Markdown` error; no `except: pass`, no log-only patterns

**Checkpoint**: All six GM tabs render without crashing. Join code visible at top. NPC and story event saves work. Session creation groups events under session headers. World Notes saves and renders Markdown. Players tab lists joined players. AI-dependent tabs show placeholders when Ollama is unavailable.

---

## Phase 6: User Story 4 — Player Uses the Player Dashboard Tools (Priority: P1)

**Goal**: A player in an active session can view/edit their character, read story history grouped by session, and chat with their twin — or see a clear unavailable state for AI features.

**Independent Test**: Join a campaign as a player (auth-first). Navigate Character, Twin Chat, and History tabs. Fill in and save character details. View history (events grouped by session). If Ollama is available, send a twin chat message. If not, verify the "AI unavailable" message appears. Rejoin via joined-campaigns list — character edits must be persisted.

### Implementation for User Story 4

- [x] T028 [US4] Player dashboard layout: `gr.TabbedInterface` with Character, Twin Chat, and Story History stubs per Principle VII
- [x] T029 [P] [US4] Character tab in `apps/web/pages/player/character.py`: name/race/discipline/background/personality inputs, Save Character button, upsert on case-insensitive name per campaign; character pre-loaded on tab render
- [x] T030 [P] [US4] Story History tab in `apps/web/pages/player/history.py`: read-only `gr.Markdown` listing all public story events for the campaign grouped by session header chronologically; events without a session shown under "Unsorted"
- [x] T031 [US4] Twin Chat tab in `apps/web/pages/player/twin_chat.py`: shows "AI service unavailable — check that Ollama is running" when `CampaignSession.ai_available` is False; wired to Ollama using player's `DigitalTwin` conversation history when available; all provider errors displayed visibly
- [x] T051 [US4] Update character pre-load logic in `apps/web/pages/player/character.py`: query the player's Character record using `CampaignSession.user_id` + `CampaignSession.campaign_id` via `Player.user_id` join (instead of display name match) to ensure the correct player record is loaded for the authenticated user

**Checkpoint**: All three player tabs render without crashing. Character save is persisted. Story history shows events grouped by session. Twin chat shows AI-unavailable placeholder when Ollama is down. Rejoining via joined-campaigns list restores saved character.

---

## Phase 7: User Story 5 — Image Generation is Accessible as a Named Feature (Priority: P2)

**Goal**: GMs and players can see and trigger portrait generation for NPCs and characters. When ComfyUI is unavailable, a clear placeholder is shown — the control is never hidden.

**Independent Test**: Navigate to an NPC with a physical description and click Generate Portrait. If ComfyUI is running, a portrait appears and is saved. If not, "Image generation unavailable — check that ComfyUI is running" is visible and the existing portrait (or placeholder icon) is retained. Any image generation error shows visibly in the UI.

### Implementation for User Story 5

- [ ] T032 [P] [US5] Add "Generate Portrait" button and `gr.Image` display to the NPC tab in `apps/web/pages/gm/npcs.py` and to the Character tab in `apps/web/pages/player/character.py`; when ComfyUI is unavailable, button is visible but disabled and a `gr.Markdown` reads "Image generation unavailable — check that ComfyUI is running"
- [ ] T033 [US5] Implement portrait generation handler for both NPC and Character tabs: call the ComfyUI/image generation provider when available, display returned image and persist `portrait_url` on the entity; catch and display all provider errors visibly in `gr.Markdown` — never swallow exceptions

**Checkpoint**: Generate Portrait button visible on NPC and Character tabs regardless of service availability. When ComfyUI is down, visible placeholder message appears. When up, portrait is generated and saved.

---

## Phase 8: User Story 6 — Stale Spec Artifacts are Cleaned Up (Priority: P3)

**Goal**: No open tasks in `/specs` reference the old FastAPI entrypoint, bcrypt threading, old anonymous player join flow, or `landing.py`. README reflects the current Gradio-only, auth-first architecture.

**Independent Test**: Read all open `tasks.md` files in `/specs`. Confirm none reference `uvicorn`, `main:app`, bcrypt threading, or `landing.py`. Read `README.md` — confirm it describes auth-first player flow, hub screen, and `uv run python apps/web/app.py` as the launch command.

### Implementation for User Story 6

- [x] T034 [US6] Scan all `tasks.md` files under `/specs` (002 and 003) and mark any open task referencing FastAPI-based launching, bcrypt threading, or the three-field player join form as `[SUPERSEDED]`
- [x] T035 [US6] Update `README.md` to accurately describe: Gradio-only launch, simplified auth, campaign management ⚠️ SUPERSEDED by T052 — README needs updating for hub screen and auth-first player flow
- [x] T052 [US6] Update `README.md` to reflect 2026-06-20 architectural changes: auth-first flow for all users (players must create accounts), hub screen (post-login navigation with GM and Player paths), player join no longer accepts a player name (username used automatically), module consolidation (`landing.py` and `admin/campaigns.py` deleted), current known limitations (no OAuth, no mobile, AI services optional)

**Checkpoint**: No open tasks in `/specs` reference old entrypoints, anonymous join, or `landing.py`. README launch command, player join flow, and feature descriptions are accurate.

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Verification and cross-cutting quality checks that span all user stories.

- [x] T053 [P] Update `specs/004-auth-admin-reboot/contracts/ui-contract.md` to reflect new Player Join Screen contract (auth-required; join_code only; no player_name field); add Hub Screen contract (two buttons: "My Campaigns (GM)" and "Join a Campaign (Player)"); add `user_id: UUID` to Transient State Contract for `CampaignSession`
- [ ] T036 [P] Run all 9 quickstart.md validation scenarios against the running app: GM auth flow, campaign creation and join code display, hub navigation, player join flow (auth-first, no player name), player rejoin persistence (joined-campaigns list), AI degradation, session creation and event logging, players tab, campaign archive — all scenarios must pass [MANUAL — requires running app]
- [ ] T037 Verify all GM and player dashboard tabs render without crashing when both Ollama and ComfyUI are unavailable — every AI-dependent component must show a visible placeholder, not a blank panel or Python traceback [MANUAL — requires running app]
- [x] T038 [P] Run `ruff check apps/web/ packages/core/ packages/storage/` and `pyright apps/web/ packages/core/ packages/storage/` and resolve all reported errors
- [x] T054 [P] Re-run ruff and pyright after all T039–T052 changes are complete to catch any new type or lint errors introduced by the `user_id` additions and module moves

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS all user stories; T039–T043 must complete before US2 work (T047–T050)
- **User Stories (Phases 3–8)**: All depend on Foundational phase completion
  - US1 and US2 can proceed in parallel after Phase 2
  - US3 depends on US1 (GM must be authenticated to enter a campaign)
  - US4 depends on US2 (player must have joined to use the dashboard); T051 depends on T039 (`user_id` in CampaignSession)
  - US5 depends on US3 and US4 (portrait button lives inside dashboard tabs)
  - US6 is independent and can be done any time after US1 is complete
- **Polish (Phase 9)**: Depends on all desired user stories being complete

### User Story Dependencies

- **US1 (P1)**: After Phase 2 — T044 (hub) depends on T039 (`CampaignSession.user_id`); T046 (module move) depends on T043 (`services/db.py`)
- **US2 (P1)**: After Phase 2 — T047 depends on T043 and T042; T048 depends on T041; T050 depends on T043 and T047
- **US3 (P1)**: After US1 — all GM tab tasks are independent of each other after T019
- **US4 (P1)**: After US2 — T051 depends on T039 (`CampaignSession.user_id`)
- **US5 (P2)**: After US3 and US4
- **US6 (P3)**: Independent; T052 should run after US2 is complete so README is accurate

### Within Each User Story

- Schema/model changes before service layer (`CampaignSession.user_id` before `get_or_create_player` changes)
- Migration before any code that references the new `user_id` column
- `services/db.py` singleton move before any module moves (T043 before T046 and T047)
- Placeholder stubs before real logic (Principle VII — mandatory)
- Story complete and checkpoint validated before moving to next priority

### Parallel Opportunities

- T039, T042, T043 can run in parallel (different files in Phase 2)
- T040 and T041 are sequential (migration before the updated `get_or_create_player` runs against it)
- T044, T045 can run in parallel (different sections of `app.py` hub wiring)
- T047 can run in parallel with T046 (different files: `pages/player/join.py` vs `pages/gm/campaigns.py`)
- T020, T021 can run in parallel after T019 (different GM tabs)
- T029, T030 can run in parallel after T028 (different player tabs)
- T032 can be parallelized across NPC and Character tabs
- T036, T053, T054 can run in parallel (Phase 9)

---

## Parallel Example: Phase 2 New Tasks

```
# All can start immediately after T004-T008 are confirmed complete:
T039 — Add user_id to CampaignSession in packages/core/core/schemas.py
T042 — Add get_campaigns_for_player() to packages/storage/storage/users.py
T043 — Move get_backend() to apps/web/services/db.py

# Then sequentially:
T040 — Write migration 0004_player_user_link (needs schema knowledge)
T041 — Update get_or_create_player() (needs migration to be written first)
```

## Parallel Example: User Story 2 (Auth-First Player Join)

```
# After T039, T041, T042, T043 complete:
T046 — Create pages/gm/campaigns.py (parallel with T047)
T047 — Create pages/player/join.py stub

# Then sequentially:
T048 — Wire new-campaign join handler (depends on T047)
T049 — Wire rejoining handler (depends on T047)
T050 — Delete landing.py (last — depends on T047 being complete)
```

---

## Implementation Strategy

### MVP First (User Stories 1 + 2)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational including T039–T043 (migration, schema, storage helpers)
3. Complete Phase 3: US1 — GM auth + hub screen + campaign dashboard
4. Complete Phase 4: US2 — Auth-first player join + joined campaigns list
5. **STOP and VALIDATE**: Hub navigates correctly; players must authenticate; join code creates player linked to user; returning player sees their campaigns
6. Demo if ready — end-to-end loop is functional

### Incremental Delivery

1. Phase 1 + Phase 2 (including T039–T043) → app launches, migration applied
2. US1 (T044–T046) → GM can authenticate, see hub, manage campaigns → GM demo-able
3. US2 (T047–T050) → Players can authenticate, join via hub, return via list → full auth-first loop
4. US3 + US4 → all dashboard tools accessible → full feature demo
5. US5 → portrait generation → AI showcase
6. US6 + Phase 9 → spec hygiene and validation

---

## Notes

- [P] tasks = different files, no shared state dependencies
- [Story] label maps task to specific user story for traceability
- Principle VII requires visible placeholder stubs BEFORE real logic — T007/T019/T028/T047 enforce this
- **2026-06-20 change**: All users (including players) must have a User account — anonymous join removed
- **2026-06-20 change**: Post-login hub screen required before routing to GM or Player paths
- **2026-06-20 change**: `Player.user_id` FK required — migration T040 is a hard prerequisite for T041, T048
- **2026-06-20 change**: `pages/landing.py` and `pages/admin/campaigns.py` are deleted — T043 and T050 handle this
- Upsert semantics apply to Character and NPC saves (case-insensitive name per campaign); Player upsert is now on `(campaign_id, user_id)` not player_name
- Password hashing: `hashlib.sha256(password.encode()).hexdigest()` — no bcrypt, no external dependency
- `gr.State` is the only session mechanism — no JWT, no cookies, no server-side session store
- Campaign archive is soft-delete only — `Campaign.archived = True`, data is never deleted
- Sessions act as grouping headers for StoryEvents; events without a session appear under "Unsorted"
- App entry point is `apps/web/app.py` via `uv run python app.py` — `apps/web/main.py` is retained for compatibility but is not the standard runtime
