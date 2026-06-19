# Feature Specification: Demo-Readiness QA & Incremental Polish

**Feature Branch**: `003-demo-readiness-polish`

**Created**: 2026-06-19

**Status**: Draft

**Input**: User description: "I want to check the work done so far, and make sure everything works as intended. And that the main major features are still demo-ready: Sign up and login, game master and player experience, image generation for characters and NPCs, session summary, scenery creation from session history. Use this time to make small incremental improvements to the experience. Pytest and harness runs should pass — if not, we should work on solving those problems to have more certainty of a working project."

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Sign Up and Login (Priority: P1)

A visitor opens StoryWeaver for the first time, creates a new GM account, and is immediately taken to their campaign dashboard without needing to sign in again. A returning GM opens the app and signs in to see all their campaigns.

**Why this priority**: Auth is the entry gate to every other feature. If the sign-up or sign-in flow is broken or confusing, no other feature is demo-able.

**Independent Test**: Open the app in a fresh browser tab, create an account via the "Create Account" tab, and verify immediate navigation to the campaign dashboard. Close the tab, reopen, sign in with the same credentials, and verify the same campaign list appears.

**Acceptance Scenarios**:

1. **Given** a visitor on the auth screen, **When** they fill in username, email, password, and confirm password then click "Create Account", **Then** they are immediately navigated to their (empty) campaign dashboard with a confirmation message visible.
2. **Given** a returning GM, **When** they enter their username/email and password on the Sign In tab and click "Sign In", **Then** they land on their campaign dashboard showing all previously created campaigns.
3. **Given** a visitor entering wrong credentials, **When** they submit the login form, **Then** a clear error message appears and they remain on the auth screen.
4. **Given** a visitor trying to register with an existing username or email, **When** they submit the registration form, **Then** a clear error identifies the conflict and no duplicate account is created.
5. **Given** a visitor entering mismatched passwords, **When** they submit registration, **Then** they see "Passwords do not match" and no account is created.

---

### User Story 2 — Game Master Experience (Priority: P1)

An authenticated GM can create and manage campaigns from the admin dashboard, enter a campaign to view characters, manage NPCs with digital twin chat, log story events, and access world notes and session planning tools.

**Why this priority**: The GM is the primary user. The end-to-end GM flow must work reliably for a demo; a broken GM dashboard means the demo cannot continue.

**Independent Test**: Log in, create a campaign, enter the campaign as GM, create an NPC with personality and background, send a message in the NPC twin chat, log two story events, and verify both appear in the event timeline.

**Acceptance Scenarios**:

1. **Given** an authenticated GM on the campaign dashboard, **When** they click "+ New Campaign", enter a name, and click "Create", **Then** the new campaign appears in the list immediately.
2. **Given** a campaign in the list, **When** the GM selects the row and clicks "Resume Campaign →", **Then** they enter the GM Dashboard with the campaign join code displayed at the top.
3. **Given** a GM in their campaign, **When** they go to the NPCs tab, fill in name, personality, and background, then click "Save NPC", **Then** the NPC appears in the selector dropdown and the sheet renders with all entered details.
4. **Given** an NPC exists and AI is available, **When** the GM types a message in the NPC twin chat and clicks "Send", **Then** the NPC responds in character.
5. **Given** a GM in the Story History tab, **When** they enter an event description, select an event type, and click "Log Event", **Then** the event appears in the timeline below immediately.
6. **Given** a GM on the Characters tab, **When** they click "↻ Refresh", **Then** the table shows all player characters that have been created in the campaign.

---

### User Story 3 — Player Experience (Priority: P1)

A player enters a campaign using a join code provided by their GM, creates their Earthdawn character with attributes and a physical description, views their character sheet, and interacts with the character twin chat.

**Why this priority**: The player flow demonstrates the core AI-assisted RPG experience and must work end-to-end for the demo.

**Independent Test**: As GM, copy the join code from the campaign detail page. Open an incognito tab, use the join form to enter the campaign as a player, create a character, and send one twin chat message.

**Acceptance Scenarios**:

1. **Given** a player on the admin/join screen, **When** they enter campaign name, join code, and player name then click "Join Campaign", **Then** they enter the Player Dashboard and see "Joined! Welcome, [name]."
2. **Given** a player in the Player Dashboard, **When** they fill in the character form (name, race, discipline, circle, attributes, background, personality) and click "Save Character", **Then** the character appears in the character selector dropdown.
3. **Given** a character selected in the dropdown, **When** the character sheet renders, **Then** all saved fields including race, discipline, circle, attributes, background, personality, goals, and physical description are displayed correctly.
4. **Given** a player in the Twin Chat tab with a character selected, **When** they type a message and click "Send" (AI available), **Then** the character responds in-character in the chatbot area.
5. **Given** a player who previously joined a campaign, **When** they rejoin the same campaign in a new browser tab with the same player name, **Then** their previously created character is already available in the selector without re-creation.

---

### User Story 4 — Image Generation for Characters and NPCs (Priority: P2)

A player or GM can generate a portrait for a character or NPC by clicking "Generate Portrait". The portrait is displayed inline and persisted so it is visible in future sessions.

**Why this priority**: Portrait generation is a high-impact visual demo moment. Both the happy path and the degraded-mode fallback must be clean and understandable.

**Independent Test**: In AI mode, save a character with a physical description, click "Generate Portrait", and verify a portrait image appears. Then test in degraded mode: verify the button is clearly disabled.

**Acceptance Scenarios**:

1. **Given** a character with a physical description saved and AI available, **When** the player clicks "Generate Portrait", **Then** a portrait image appears in the portrait area and is saved to the character record.
2. **Given** an NPC with a physical description saved and AI available, **When** the GM clicks "Generate Portrait" on the NPCs tab, **Then** a portrait appears and is saved to the NPC record.
3. **Given** a character with no physical description, **When** the player clicks "Generate Portrait", **Then** they see "Add a physical description to your character first" and no image request is made.
4. **Given** AI is unavailable, **When** the player or GM views the character/NPC tab, **Then** the "Generate Portrait" button is visually disabled and the AI-unavailable banner is shown.
5. **Given** a portrait was generated in a previous session, **When** the player selects the same character in a new session, **Then** the previously generated portrait is displayed automatically.

---

### User Story 5 — Session Summary (Priority: P2)

A GM can select a session from the Story History tab and generate a readable summary of what happened during that session, giving players a recap between game nights.

**Why this priority**: Session summaries are a key value proposition. The current implementation outputs a raw event list — the improvement is a coherent narrative summary in AI mode.

**Independent Test**: Log three or more events of different types in a session, click "Generate Session Summary", and verify the output is readable prose (AI mode) or a clean formatted list (degraded mode).

**Acceptance Scenarios**:

1. **Given** a session with logged events and AI available, **When** the GM clicks "Generate Session Summary", **Then** a narrative paragraph summarizing the session's key events appears.
2. **Given** AI is unavailable, **When** the GM generates a summary, **Then** a formatted event list appears — the output is never blank when events exist.
3. **Given** a session with no events, **When** the GM tries to generate a summary, **Then** they see "No events recorded for this session yet."
4. **Given** a session with a mix of public and GM-only events, **When** the GM generates a summary, **Then** the output includes all events (GM-only events are marked accordingly).

---

### User Story 6 — Scenery Creation from Session History (Priority: P2)

A GM can generate a scene illustration in the Story History tab. The scene description input provides context from recent session events as a starting point, and the generated image appears inline.

**Why this priority**: Scene illustration is the most visually dramatic demo feature. It needs to be easy to trigger and grounded in the actual story — not a blank field with no hints.

**Independent Test**: Log two story events in a session, select that session in the history filter, and verify the scene description input is pre-filled with event context. Click "Generate Scene Art" in AI mode and verify an image appears.

**Acceptance Scenarios**:

1. **Given** a GM in the Story History tab with AI available and a scene description entered, **When** they click "Generate Scene Art", **Then** a scene illustration appears below the input.
2. **Given** AI is unavailable, **When** the GM views the Story History tab, **Then** the "Generate Scene Art" button is disabled and a message explains AI is unavailable.
3. **Given** the GM leaves the scene description field empty, **When** they click "Generate Scene Art", **Then** they see "Enter a scene description first" — no image request is made.
4. **Given** a session is selected in the history filter and events exist for that session, **When** the GM opens the Scene Illustration section, **Then** the description input is pre-populated with a brief summary of those session events as contextual inspiration (new improvement).

---

### User Story 7 — Test Suite and Harness Pass (Priority: P1)

The full pytest test suite passes without errors or failures. Any failing tests are diagnosed and fixed during this cycle, and any uncovered critical paths gain new tests. All existing harness evals continue to pass.

**Why this priority**: Per the project constitution (Principle V: Harness-Driven Agent Quality), a milestone is only complete when all acceptance criteria are expressible and pass as automated assertions. Passing tests are the ground truth that features work as intended — they also protect future incremental changes from silently breaking the demo paths.

**Independent Test**: Run `pytest` from the repository root and verify all tests pass. Run any harness evals and verify they pass. Zero failures, zero errors.

**Acceptance Scenarios**:

1. **Given** the current codebase, **When** `pytest` is run, **Then** all tests pass with zero failures and zero errors.
2. **Given** any test currently failing or erroring, **When** the root cause is diagnosed, **Then** either the code is fixed to match the spec or (if the test is wrong) the test is corrected and the fix is documented.
3. **Given** a critical demo path that has no test coverage (e.g., auth happy path, player join flow), **When** this cycle is complete, **Then** at least one integration test covers that path.
4. **Given** existing harness evals for agent and tool behavior, **When** the evals are run, **Then** they pass at the same or better score as before this cycle.

---

### Edge Cases

- What if portrait generation takes more than a few seconds? The "Generate Portrait" button should be disabled or show a loading indicator during the request to prevent double-clicks.
- What if the image provider returns an error? The user sees a specific error message — no silent failure, no blank image.
- What if a player has no characters when they first enter the Player Dashboard? The character selector is empty and clear guidance directs them to the form below.
- What if the GM campaign list is empty after logging in? The "No campaigns yet — create one above" message is shown.
- What if a player tries to join with a wrong join code? They see "No campaign found with that name and join code." and remain on the join form.
- What if a pytest test fails due to a schema or migration mismatch (e.g., a column exists in the model but not in the test DB)? The fix MUST update the migration, not suppress the test.
- What if the LLM call for session summary times out? The summary falls back to the formatted event list with an inline message that AI generation failed.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: All six demo feature areas (auth, GM experience, player experience, character portrait, NPC portrait, session summary, scene illustration) MUST work end-to-end in a single demo session without manual DB or server restarts.
- **FR-002**: Degraded mode (`ai_available=False`) MUST be visually distinct: AI-dependent buttons are disabled, and the AI-unavailable banner or an inline message explains the state. No unhandled exceptions or blank screens may occur.
- **FR-003**: The "Generate Portrait" button for characters and NPCs MUST be disabled when AI is unavailable, and MUST return a user-visible message when clicked with a missing physical description.
- **FR-004**: Session summary output MUST use the LLM to produce a narrative paragraph in AI mode. In degraded mode, it falls back to the formatted event list — the output is never blank when events exist.
- **FR-005**: The Scene Illustration section MUST disable the "Generate Scene Art" button and show an explanatory message when `ai_available=False`.
- **FR-006**: When a session is selected in the history filter and that session has events, the scene description input SHOULD be pre-populated with a brief text summary of those events as context for the GM.
- **FR-007**: All primary form submission buttons (Save Character, Save NPC, Create Campaign, Log Event, Join Campaign) MUST display a success or error message within 3 seconds of clicking, with no silent failures.
- **FR-008**: Character and NPC portrait images MUST persist to the database on generation and be displayed automatically when the character/NPC is selected in the same or a future session.
- **FR-009**: The player join form MUST validate that campaign name, join code, and player name are all non-empty before submitting, showing an error if any are blank.
- **FR-010**: A player rejoining a campaign in a new browser tab with the same player name MUST see their existing characters in the selector without recreating them.
- **FR-011**: The full pytest test suite MUST pass with zero failures and zero errors. Any currently failing tests MUST be diagnosed and resolved — either by fixing the implementation or correcting the test if it misrepresents the spec.
- **FR-012**: Any critical demo path not currently covered by an automated test MUST gain at least one integration test during this cycle. Critical paths include: GM account registration, GM login, campaign creation, player campaign join, and character save/upsert.
- **FR-013**: All existing harness evals MUST continue to pass at the same or better score after any code changes made during this cycle.

### Key Entities

- **Demo Session**: A scripted end-to-end walkthrough covering all six feature areas; used as the primary acceptance frame for this spec.
- **Degraded Mode**: App state where `ai_available=False` because the Ollama health check fails at session start. All non-AI features must remain fully functional.
- **Test Suite**: The set of pytest tests in `apps/web/tests/` and any package-level tests in `packages/*/tests/`. All must pass cleanly.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A person unfamiliar with the codebase can complete a full demo walkthrough (auth → GM campaign → player join → character portrait → NPC portrait → session summary → scene art) in under 10 minutes without hitting an unhandled error.
- **SC-002**: In degraded mode (Ollama unavailable), zero unhandled exceptions or blank screens occur across all six demo paths.
- **SC-003**: Portrait generation (character or NPC) succeeds and the image is visible on re-selection within 60 seconds of clicking "Generate Portrait" in AI mode.
- **SC-004**: Session summary output is non-empty whenever events exist for the selected session — either an LLM-generated narrative or a formatted event list.
- **SC-005**: Every primary form button shows a success or error message within 3 seconds of clicking, with no silent failures.
- **SC-006**: `pytest` exits with code 0 (all tests pass) on the main branch at the end of this cycle.
- **SC-007**: Critical demo paths (auth, campaign creation, player join, character upsert) each have at least one passing integration test.

---

## Assumptions

- "AI mode" means Ollama is reachable and an image provider (`IMAGE_PROVIDER` env var) is configured. Local-first setup; no cloud key is required for the default configuration.
- "Degraded mode" means `ai_available=False` — either Ollama is not running or the health check times out. All non-AI features must continue to function normally.
- Small incremental improvements are scoped to existing pages and handlers in `apps/web/`. No new packages, database tables, or ADRs are introduced in this spec unless a failing test reveals a structural issue requiring a migration fix.
- LLM-based session summary is a targeted improvement on the current text-concatenation fallback, not a new feature — the event data already exists.
- Scene description pre-population reads from existing event records for the selected session — no new storage or model changes needed.
- If a test fails due to a missing migration column or schema mismatch, the fix MUST update the migration to match the model — suppressing the test is not acceptable.
- Mobile UI optimization is out of scope; the app targets desktop/tablet browsers.
- The `ruff` linter and `pyright` type-checker pass as part of CI checks — any new or modified code MUST comply.