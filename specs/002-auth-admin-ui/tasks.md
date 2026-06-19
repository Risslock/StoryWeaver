# Tasks: Authentication & Admin UI

**Feature**: 002-auth-admin-ui
**Input**: Design documents from `specs/002-auth-admin-ui/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅, quickstart.md ✅

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no dependencies between them)
- **[Story]**: Which user story this task belongs to (US1–US5)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Write the required ADR and add new runtime dependencies before any code changes.
FastAPI must be documented via ADR (constitution § Technology Stack Constraints) before implementation begins.

- [X] T001 Write docs/adr/ADR-006-fastapi-minimal-router.md — document FastAPI-as-ASGI-routing-adapter decision (scope, rationale, alternatives rejected, migration path); required by constitution before any implementation
- [ ] T002 [P] Add passlib[bcrypt], fastapi, uvicorn to apps/web/pyproject.toml dependencies

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: SQLAlchemy models, schemas, storage layer, auth service, and Alembic migration.
No user story work can begin until this phase is complete.

**⚠️ CRITICAL**: All user stories depend on these tasks.

- [ ] T003 Update packages/core/core/models.py — add User model (id UUID PK, username String(100) UNIQUE, email String(255) UNIQUE, hashed_password String(255), is_active Boolean default True, created_at DateTime tz); add Player model (id UUID PK, campaign_id FK→campaigns CASCADE, player_name String(100), character_id FK→characters SET NULL nullable, created_at DateTime tz); add Campaign.owner_id column (UUID FK→users RESTRICT); change Campaign.join_code to String(6); add functional unique indexes: ix_campaigns_owner_name_lower on (func.lower(name), owner_id), ix_characters_campaign_name_lower on (func.lower(name), campaign_id), ix_npcs_campaign_name_lower on (func.lower(name), campaign_id), ix_players_campaign_player_name_lower on (func.lower(player_name), campaign_id)
- [ ] T004 [P] Add UserSchema, PlayerSchema, RegisterRequest dataclasses to packages/core/core/schemas.py — UserSchema (id, username, email, is_active, created_at), PlayerSchema (id, campaign_id, player_name, character_id, created_at), RegisterRequest (username, email, password, confirm_password)
- [ ] T005 Create packages/storage/storage/users.py — async functions: get_user_by_username_or_email(session, identifier) → User | None (tries username lookup then email, both case-insensitive), create_user(session, username, email, hashed_password) → User, get_or_create_player(session, campaign_id, player_name) → Player (case-insensitive lookup on lower(player_name)), link_player_character(session, player_id, character_id) → Player
- [ ] T006 [P] Create Alembic migration 0002_auth_admin_ui — implement all 10 up-steps from data-model.md migration strategy in order: create users table, insert system user backfill record, add owner_id nullable column to campaigns, UPDATE campaigns SET owner_id=system_user_id, batch-alter owner_id to NOT NULL, batch-alter join_code to String(6), add ix_campaigns_owner_name_lower index, add ix_characters_campaign_name_lower index, add ix_npcs_campaign_name_lower index, create players table; implement full downgrade() reversing all steps
- [ ] T007 Create apps/web/services/auth.py — hash_password(plain: str) → str using passlib CryptContext bcrypt, verify_password(plain: str, hashed: str) → bool, make_auth_callable(backend: StorageBackend) → Callable[[str, str], bool] factory that returns a synchronous validate_credentials function (runs asyncio.run on async lookup, catches all exceptions and returns False, never raises, timing-safe dummy hash on miss per auth-callable.md), register_user(backend, username, email, password) → tuple[bool, str] async per registration-ui.md DB operation contract

**Checkpoint**: Foundation ready — all user story phases can begin

---

## Phase 3: User Story 1 — GM Logs In and Resumes a Campaign (Priority: P1) 🎯 MVP

**Goal**: A GM can register a new account, log in from any browser session, see all their campaigns listed, and resume a campaign picking up the story exactly where it stopped.

**Independent Test**: Create a campaign in one browser session, close the session, re-open the app, log in with the same credentials, and verify the campaign and its story content are retrievable and interactive.

### Tests for User Story 1

- [ ] T008 [US1] Create apps/web/tests/test_auth_service.py — unit tests for: hash_password produces bcrypt hash; verify_password returns True for correct password and False for wrong; make_auth_callable returns True for valid active user, False for wrong password, False for inactive user (is_active=False), False for unknown username, False on DB exception; register_user creates user on success, returns (False, error) for duplicate username, returns (False, error) for duplicate email

### Implementation for User Story 1

- [ ] T009 [P] [US1] Create apps/web/pages/registration.py — unauthenticated Gradio Blocks (no auth= param) with registration form per registration-ui.md contract: gr.Textbox for username/email/password/confirm, gr.Button "Create Account", gr.Markdown status output, static login link; submit handler calls services.auth.register_user, displays success "✓ Account created! Sign in here." or specific error message; app factory function create_registration_app() → gr.Blocks
- [ ] T010 [P] [US1] Create apps/web/pages/admin/__init__.py — empty package init file
- [ ] T011 [P] [US1] Create apps/web/pages/admin/campaigns.py — Campaign Dashboard Gradio component (to be embedded in main app): load_campaigns handler uses request: gr.Request to get username, queries campaigns WHERE owner_id matches username ordered by created_at DESC, populates gr.Dataframe with columns [Name, Join Code, Created]; empty-state helper text "No campaigns yet — create one above."; Open → button per row that stores selected campaign_id in gr.State for navigation; returns build_campaigns_page(session_state, request) builder function
- [ ] T012 [US1] Modify apps/web/app.py — add auth=make_auth_callable(backend) to main gr.Blocks instantiation; add request: gr.Request parameter to the load/navigate handlers that need username identity; wire session_state.change to show Campaign Dashboard (admin/campaigns) as the post-login landing view when no active campaign session is loaded; import and embed build_campaigns_page from pages/admin/campaigns
- [ ] T013 [US1] Create apps/web/main.py — FastAPI app with lifespan context manager (initialize_db, WAL pragma, log startup); create main authenticated Blocks from app.py create_app() with auth=make_auth_callable(backend) and auth_message="Sign in to StoryWeaver"; create registration_blocks from create_registration_app(); mount both via gr.mount_gradio_app(fastapi_app, main_blocks, path="/") and gr.mount_gradio_app(fastapi_app, registration_blocks, path="/register"); expose as app = fastapi_app for uvicorn

**Checkpoint**: GM can register at /register, log in at /, see campaign list, and resume any campaign. US1 fully functional.

---

## Phase 4: User Story 2 — GM Shares Campaign Access with Players (Priority: P1)

**Goal**: An authenticated GM can view and copy a campaign's join code from the Campaign Detail screen, and players can use campaign name + join code + player name to rejoin from any new session, restoring their character and story context.

**Independent Test**: Create a campaign as GM, navigate to campaign detail, copy join code, open an incognito window, enter campaign name + join code + player name, verify the player session loads and any previously created character is accessible.

### Tests for User Story 2

- [ ] T014 [US2] Create apps/web/tests/test_player_join.py — integration tests for: Player record created on first join with new player name; Player record retrieved (not duplicated) on rejoin with same player name; case-insensitive player name match ("Kira" and "kira" → same Player record); Player.character_id is restored when player rejoins; invalid join code returns error; invalid campaign name returns error; wrong campaign name + correct join code returns error

### Implementation for User Story 2

- [ ] T015 [US2] Add Campaign Detail screen to apps/web/pages/admin/campaigns.py — Screen 2 per admin-ui.md: gr.Markdown for campaign name and metadata, gr.Textbox(interactive=False, show_copy_button=True) for join code display, gr.Markdown for game system and created date, Back button (returns to Campaign Dashboard), Resume Campaign button (loads CampaignSession into session_state triggering existing _navigate() GM dashboard flow); implement navigation state machine between Dashboard and Detail screens using gr.Column visibility toggling
- [ ] T016 [US2] Modify apps/web/pages/landing.py — update player join handler to call storage.users.get_or_create_player(session, campaign_id, player_name) creating or restoring the Player record; if Player.character_id is set, pre-populate the returned CampaignSession with the linked character so it is immediately accessible; validate join by campaign name + join code combination (case-insensitive campaign name lookup, exact join code match)

**Checkpoint**: GM can display and copy join code; players can rejoin and restore their character. US2 fully functional.

---

## Phase 5: User Story 3 — GM Manages Campaigns from the Admin UI (Priority: P2)

**Goal**: An authenticated GM can create new campaigns from the admin dashboard and navigate to any campaign.

**Independent Test**: Log in, create two campaigns from the admin UI, verify both appear in the campaign list, and navigate into each to confirm they are independent.

### Tests for User Story 3

- [ ] T017 [US3] Create apps/web/tests/test_admin_campaigns.py — integration tests for: campaign creation succeeds with valid name and sets owner_id to requesting user; join code is 6-char uppercase alphanumeric and globally unique; campaign list for a user returns only their campaigns ordered by created_at DESC; second user creating a campaign with the same name as first user's campaign succeeds (name uniqueness is per-owner)

### Implementation for User Story 3

- [ ] T018 [US3] Add campaign creation form and handler to apps/web/pages/admin/campaigns.py — "New Campaign" button toggles a collapsible gr.Group with campaign name gr.Textbox and game system gr.Dropdown (default "earthdawn_4e"); create handler uses request.username to look up owner User.id, generates join code via secrets.token_urlsafe filtered to [A-Z0-9] sliced to 6 chars with retry-on-global-collision, INSERTs new Campaign; on success collapses form and refreshes campaign list Dataframe; on error displays inline gr.Warning

**Checkpoint**: GM can create and navigate campaigns from the admin UI. US3 fully functional.

---

## Phase 6: User Story 4 — Upsert Behavior for Characters and NPCs (Priority: P2)

**Goal**: Submitting a create-character or create-NPC action with a name that matches an existing entity (case-insensitive) in the same campaign updates the existing record rather than creating a duplicate.

**Independent Test**: Create a character named "Kira" with race Elf, then submit create-character again for "KIRA" with race Human. Verify exactly one character exists, its race is Human, and its id and created_at are unchanged.

### Tests for User Story 4

- [ ] T019 [US4] Create apps/web/tests/test_upsert.py — integration tests for: character create with new name → INSERT (one record); character create with same name (exact) → UPDATE (still one record, attributes updated, id unchanged); character create with same name different case ("Kira"/"KIRA") → UPDATE same record; NPC create with new name → INSERT; NPC create with same name → UPDATE; NPC create with same name different case → UPDATE same record

### Implementation for User Story 4

- [ ] T020 [P] [US4] Modify _save_character in apps/web/pages/player/character.py — replace direct INSERT with upsert: SELECT WHERE lower(name)=lower(input_name) AND campaign_id=campaign_id; if found: UPDATE all provided fields (preserve id, created_at, update updated_at if column exists); if not found: INSERT new record; return character in both cases
- [ ] T021 [P] [US4] Modify _save_npc in apps/web/pages/gm/npcs.py — replace direct INSERT with upsert: SELECT WHERE lower(name)=lower(input_name) AND campaign_id=campaign_id; if found: UPDATE all provided fields (preserve id, created_at, update updated_at if column exists); if not found: INSERT new record; return NPC in both cases

**Checkpoint**: Character and NPC create actions are idempotent on name — duplicates replaced with updates. US4 fully functional.

---

## Phase 7: User Story 5 — Campaign Name Uniqueness Enforcement (Priority: P3)

**Goal**: Attempting to create a campaign with a name that already exists for the same user account (case-insensitive) is rejected with a clear, specific error message.

**Independent Test**: Create a campaign named "The Iron Crown", then attempt to create another with the same name (and again with "the iron crown" differing only in case). Verify only one campaign exists and each duplicate attempt returned "A campaign named '...' already exists."

### Implementation for User Story 5

- [ ] T022 [US5] Add IntegrityError handling to campaign creation handler in apps/web/pages/admin/campaigns.py — catch sqlalchemy.exc.IntegrityError from the INSERT; inspect error string for "ix_campaigns_owner_name_lower" to identify duplicate-name violations; display gr.Warning "A campaign named '{name}' already exists." per admin-ui.md error states; also validate empty name with gr.Warning "Campaign name cannot be empty." before DB write

**Checkpoint**: Campaign name uniqueness is enforced case-insensitively with a specific error message. US5 fully functional.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Mandatory quality gates required by the constitution (Principles I and V) and project-wide code health.

- [ ] T023 Update README.md to reflect current implemented state — add completed feature: GM authentication (registration at /register, login via Gradio built-in auth), campaign admin dashboard, join code sharing, player rejoin flow, character/NPC upsert semantics; update entry point from app.py to uvicorn apps.web.main:app --port 7860; note known limitations (no password reset, no join code rotation, player passwords out of scope); remove or correct any description of superseded functionality per constitution Principle I
- [ ] T024 [P] Run ruff check across apps/web/, packages/core/core/, packages/storage/storage/ and fix all reported linting and formatting issues
- [ ] T025 [P] Run pyright --strict across all new and modified files (services/auth.py, pages/registration.py, pages/admin/campaigns.py, pages/landing.py, storage/users.py, main.py) and resolve all type errors
- [ ] T026 Run full pytest suite — apps/web/tests/test_auth_service.py, test_admin_campaigns.py, test_upsert.py, test_player_join.py — ensure all tests pass with no errors or warnings
- [ ] T027 Run quickstart.md validation scenarios 1–11 against a live app instance (uvicorn apps.web.main:app --port 7860) and verify all expected outcomes match

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately; T001 and T002 can run in parallel
- **Phase 2 (Foundational)**: Requires Phase 1 complete — BLOCKS all user stories
- **Phase 3 (US1)**: Requires Phase 2 complete — 🎯 first MVP milestone
- **Phase 4 (US2)**: Requires Phase 2 complete + Phase 3 complete (player join needs auth wired in app.py)
- **Phase 5 (US3)**: Requires Phase 3 complete (extends campaign dashboard built in T011/T012)
- **Phase 6 (US4)**: Requires Phase 2 complete only (storage-layer change, no UI dependency on US1–US3)
- **Phase 7 (US5)**: Requires Phase 5 complete (extends campaign creation handler from T018)
- **Phase 8 (Polish)**: Requires all prior phases complete

### Within Phase 2 (Foundational)

```
T003 (models.py — shared file, must be first)
  └─► T004 [P] (schemas.py — parallel with T005, T006)
  └─► T005     (storage/users.py — needs models)
  └─► T006 [P] (alembic migration — needs models to write SQL)
T005 ──► T007  (auth.py — needs storage functions)
```

### Within Phase 3 (US1)

```
T008           (tests — write first, verify they fail)
T009 [P]       (registration page — independent file)
T010 [P]       (admin/__init__.py — independent file)
T011 [P]       (admin/campaigns.py — independent file)
T009+T011 ──► T012  (app.py — integrates all pages)
T012 ──► T013  (main.py — wraps final app)
```

### Parallel Opportunities Summary

| Tasks | Why parallel |
|-------|-------------|
| T001, T002 | Different files; no dependency |
| T004, T006 | Different files; both depend only on T003 |
| T009, T010, T011 | Different new files; no dependencies between them |
| T020, T021 | Different files (character.py vs npcs.py); identical pattern |
| T024, T025 | Different tools (ruff vs pyright); no shared state |

---

## Parallel Execution Examples

### Phase 2 Foundational — Parallel Window After T003

```bash
# Sequential first:
Task T003: Update packages/core/core/models.py

# Parallel after T003:
Task T004: Add schemas to packages/core/core/schemas.py
Task T006: Create Alembic migration 0002_auth_admin_ui

# Sequential after T004 + T003:
Task T005: Create packages/storage/storage/users.py

# Sequential after T005:
Task T007: Create apps/web/services/auth.py
```

### Phase 3 US1 — Parallel Window After T008

```bash
# Sequential first (write failing tests):
Task T008: Create apps/web/tests/test_auth_service.py

# Parallel after T008:
Task T009: Create apps/web/pages/registration.py
Task T010: Create apps/web/pages/admin/__init__.py
Task T011: Create apps/web/pages/admin/campaigns.py

# Sequential after T009 + T011:
Task T012: Modify apps/web/app.py
Task T013: Create apps/web/main.py
```

### Phase 6 US4 — Full Parallel

```bash
# Both in parallel (different files):
Task T020: Modify apps/web/pages/player/character.py (_save_character upsert)
Task T021: Modify apps/web/pages/gm/npcs.py (_save_npc upsert)
```

---

## Implementation Strategy

### MVP First (User Stories 1 Only)

1. Complete Phase 1: Setup (ADR + dependencies) — ~30 min
2. Complete Phase 2: Foundational (models, migration, storage, auth service) — blocking gate
3. Complete Phase 3: User Story 1 (registration, login, campaign list, resume) — MVP deliverable
4. **STOP and VALIDATE**: Run quickstart.md Scenarios 1, 2, 5, 7 end-to-end
5. Demo: GMs can now persist and resume campaigns across sessions

### Incremental Delivery

- Foundation complete → deliver US1 (P1) → demo
- US1 complete → deliver US2 (P1: join code + player rejoin) → demo
- US2 complete → deliver US3 (P2: campaign creation) + US4 (P2: upsert) in parallel (different files)
- US3 complete → deliver US5 (P3: name uniqueness error handling)
- All stories complete → Polish (README, linting, type check, full test run)

### Parallel Team Strategy

After Phase 2 completes:
- Developer A: US1 → US2 (sequential, share auth wiring)
- Developer B: US4 (independent storage changes — no UI dependency)
- Once US1 done: Developer A → US3; Developer B → US5 (after US3)

---

## Notes

- **[P] tasks** require different files and no direct dependency between them — safe for concurrent execution
- **[Story] labels** map tasks back to user story acceptance scenarios in spec.md for traceability
- **ADR-006 (T001)** MUST exist before any code is committed — constitution Technology Stack Constraints gate
- **Alembic migration (T006)** MUST implement a complete `downgrade()` function for rollback safety
- **make_auth_callable (T007)** MUST be synchronous (Gradio 4.x `auth=` does not accept async callables — see research.md § 1)
- **README update (T023)** is a mandatory constitution Principle I gate — the milestone is not complete without it
- **ruff + pyright strict (T024, T025)** are mandatory per constitution § Development Workflow step 5
- Character and NPC upsert (T020, T021) preserve `id` and `created_at` — only update mutable fields
- Campaign name uniqueness (T022) is enforced at DB layer by T003/T006 indexes; T022 adds the user-facing error message layer