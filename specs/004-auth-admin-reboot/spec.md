# Feature Specification: Auth & Admin Reboot

**Feature Branch**: `004-auth-admin-reboot`

**Created**: 2026-06-19

**Status**: Draft

**Input**: User description: "reimplement and clean the auth and admin features, since current state is broken even if tests pass. Simplify authentication and sessions with SQL storage and Gradio-integrated features. At the end of this we should have features for: manage users, campaigns and sessions; use the already-built features for twins, image generation, session planning; clear usage flow for both players and GMs; remove unused tasks, specs, plans to really be on track with what is ready. Player join simplified to: join code + player name only (join code is globally unique and identifies the campaign on its own)."

---

## Clarifications

### Session 2026-06-19

- Q: What fields does a player need to join a campaign? → A: Join code and player name only. The join code is globally unique and identifies the campaign on its own. No campaign name input is required on the player join form.
- Q: What does "simplified (lighter) password check" mean for sign-in implementation? → A: SHA-256 hash — store `sha256(password)` in the existing `hashed_password` column; no bcrypt dependency, no threading workaround required.
- Q: What is a "World Note" — what data model and rendering does it require? → A: A single freeform Markdown document stored per campaign and rendered as Markdown in the UI. No separate entity table; stored as a text field on the Campaign record.
- Q: Can GMs delete or remove campaigns? → A: Soft-delete / archive only — an "Archive" button hides the campaign from the GM's default list; all campaign data (players, characters, history) is retained.
- Q: Is "Session" a separate entity from StoryEvent, or just an alias for the event log? → A: Session is a lightweight header (name + date) per campaign; story events are linked to a session. GMs create a new session before logging events under it.
- Q: Can GMs see who has joined their campaign ("manage users")? → A: Yes — a read-only "Players" tab in the GM dashboard lists all players who have joined (player name + character name). No remove action required.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — GM Signs In and Reaches Their Campaign Dashboard (Priority: P1)

A GM opens StoryWeaver, enters their username and password, and immediately sees their list of campaigns. If they have no account yet, they fill in a short "Create Account" form and are taken to the dashboard right after — no separate registration page, no page reload.

**Why this priority**: The login screen is the first thing every user sees. If it is broken or confusing, nothing else in the app is reachable. A working, simple sign-in flow is the prerequisite for every other user story.

**Independent Test**: Open the app in a fresh browser, create an account, verify the campaign dashboard appears immediately. Close and reopen, sign in with the same credentials, and confirm the same campaigns are listed.

**Acceptance Scenarios**:

1. **Given** a visitor on the auth screen, **When** they enter a username and password and click "Sign In", **Then** they are taken to their campaign dashboard within one screen transition.
2. **Given** a visitor with no existing account, **When** they fill in the "Create Account" form and submit, **Then** an account is created and they are immediately taken to their (empty) campaign dashboard — no separate page load required.
3. **Given** a user who enters an incorrect password, **When** they submit the login form, **Then** a clear, visible error message appears inside the UI (not only in the server console) and they remain on the auth screen.
4. **Given** an already-used username, **When** another visitor attempts to register with the same username, **Then** a clear UI error identifies the conflict and no duplicate account is created.
5. **Given** a signed-in user, **When** they click "Sign Out", **Then** the UI returns to the auth screen and their session data is cleared from the tab.

---

### User Story 2 — Player Joins a Campaign with Just a Join Code (Priority: P1)

A player opens StoryWeaver, enters the 6-character join code they received from their GM and their player name, and is taken to their player dashboard — with their previously created character and story history immediately accessible. No campaign name is required.

**Why this priority**: Players are the most frequent users. A simpler join flow (two fields instead of three) reduces friction and join errors. The join code is globally unique so it unambiguously identifies the campaign without any additional identifier.

**Independent Test**: As GM, copy the 6-character join code from the campaign detail view. Open an incognito window, enter the join code and a player name. Verify the player dashboard appears. Close the incognito window, reopen it, enter the same two values, and confirm the same player dashboard (with the same character, if one was created) appears again.

**Acceptance Scenarios**:

1. **Given** a valid join code and a new player name, **When** the player submits the join form, **Then** they are taken to their player dashboard and a new Player record is created for them in the correct campaign.
2. **Given** a returning player who provides the same join code and player name as a previous session, **When** they submit the join form, **Then** their existing character, twin conversation history, and story events are all present.
3. **Given** an invalid or unknown join code, **When** the player submits the form, **Then** a visible UI error states "No campaign found with that join code" — no crash, no blank screen.
4. **Given** an empty player name field, **When** the player submits the form, **Then** a visible UI error prompts them to enter their name before proceeding.
5. **Given** an empty join code field, **When** the player submits the form, **Then** a visible UI error prompts them to enter the join code.

---

### User Story 3 — GM Runs a Campaign Session with All Tools Accessible (Priority: P1)

An authenticated GM enters one of their campaigns and can use all available campaign tools from the GM dashboard: viewing and editing characters and NPCs, logging story events, reading world notes, using the session planning assistant, and chatting with NPC digital twins (when AI is available).

**Why this priority**: This is the core GM gameplay loop. All existing tools must be navigable and functional — or must show a clear placeholder explaining their status — before this spec is considered complete.

**Independent Test**: Enter a campaign as GM. Navigate each tab (Characters, NPCs, Story History, World Notes, Session Plan). Create one NPC, log one story event, write one world note. If Ollama is running, send one message in the NPC twin chat and verify a response. If Ollama is not running, verify a clear "AI unavailable" message appears in the twin chat tab rather than an error crash.

**Acceptance Scenarios**:

1. **Given** an authenticated GM who enters a campaign, **When** the GM dashboard loads, **Then** the join code for that campaign is prominently displayed at the top so it can be shared with players.
2. **Given** the GM on the NPCs tab, **When** they save a new NPC with a name, role, and personality, **Then** the NPC appears in the NPC list immediately and no duplicate is created if saved again with the same name.
3. **Given** the GM on the Story History tab, **When** they log a story event, **Then** the event appears in the event list immediately.
4. **Given** the GM on the NPC twin chat and Ollama is not running, **When** the GM sends a message, **Then** the UI displays "AI service unavailable — check that Ollama is running" and does not crash or show a blank response.
5. **Given** the GM on the Session Plan tab and the AI planner is unavailable, **When** the GM views the tab, **Then** a visible placeholder message states the service status rather than showing a blank or broken panel.
6. **Given** the GM on any tab, **When** any backend operation fails, **Then** the error is displayed in-page with a human-readable description — the tab does not silently reload or go blank.

---

### User Story 4 — Player Uses the Player Dashboard Tools (Priority: P1)

A player in an active session can view and update their character sheet, read the shared story history for their campaign, and chat with their character's digital twin (when AI is available).

**Why this priority**: The player dashboard represents the player-side value proposition. All three core player tools must be reachable and usable (or gracefully degraded) for the product to be demo-able for players.

**Independent Test**: Join a campaign as a player. Navigate each tab (Character, Twin Chat, History). Fill in and save character details. View the history. If Ollama is available, send a twin chat message and verify a response. If not, verify the tab shows a clear "AI unavailable" message.

**Acceptance Scenarios**:

1. **Given** a player in the player dashboard, **When** they navigate to the Character tab, **Then** they can view and edit their character's name, race, discipline, background, and personality.
2. **Given** a player who edits and saves their character, **When** they rejoin the campaign using the same join code and player name, **Then** their character edits are persisted and visible immediately.
3. **Given** a player on the Twin Chat tab and Ollama is not running, **When** the player views the tab, **Then** a clear message states "AI service unavailable" rather than crashing or showing an empty input.
4. **Given** a player on the History tab, **When** the tab loads, **Then** all public story events for the campaign are listed in chronological order.

---

### User Story 5 — Image Generation is Accessible as a Named Feature (Priority: P2)

GMs and players can request AI-generated portrait images for characters and NPCs from within the app. When the image generation service is unavailable, the UI clearly states this with a placeholder — the tab or button is never hidden or silently broken.

**Why this priority**: Image generation is an already-built differentiating feature. It must be accessible in the UI with proper placeholder handling, even if the backend service is down during a demo.

**Independent Test**: Navigate to an NPC or Character record that has a physical description. Click "Generate Portrait". If ComfyUI is running, a portrait image appears. If not, a visible message states "Image generation unavailable — ComfyUI is not running" and a placeholder image or icon is displayed.

**Acceptance Scenarios**:

1. **Given** an NPC with a physical description, **When** the GM requests a portrait generation and the image service is available, **Then** a generated image is displayed and saved as the NPC's portrait.
2. **Given** a character with a physical description, **When** portrait generation is requested and the image service is unavailable, **Then** the UI displays "Image generation unavailable — check that ComfyUI is running" and the existing portrait (or a placeholder icon) is retained.
3. **Given** any image generation error, **When** it occurs, **Then** the error is displayed visibly in the UI — not swallowed or shown only in the server log.

---

### User Story 6 — Stale Spec Artifacts are Cleaned Up (Priority: P3)

Specs, plans, and task lists from prior phases that are now superseded by this reimplementation are clearly marked as obsolete, so the `/specs` directory accurately reflects what is currently being built.

**Why this priority**: Stale artifacts mislead future planning. The team should only track work that is current. This is lower priority than shipping working features but is required before this spec is considered complete.

**Independent Test**: Read all open `tasks.md` files in `/specs`. Confirm that no open task references the old FastAPI entry point or the old bcrypt/threading auth implementation. The README accurately describes the current Gradio-only, simplified auth architecture.

**Acceptance Scenarios**:

1. **Given** the spec directory, **When** a developer scans all `tasks.md` files, **Then** no open tasks reference FastAPI-based launching, bcrypt threading, or the old three-field player join form.
2. **Given** this feature is implemented, **When** the README is read, **Then** it accurately describes: Gradio-only launch, simplified auth, and the two-field player join (join code + player name).

---

### Edge Cases

- What if the database file is locked or unavailable at startup? The auth screen displays "Database unavailable — cannot sign in right now." The app does not crash.
- What if two players join the same campaign with the same player name? They share the same Player record and character — per-player passwords are out of scope.
- What if an NPC and a character share the same name in the same campaign? They are different entity types; name uniqueness applies independently per entity type.
- What if a player's join code was created by a campaign that is later deleted? The join form returns "No campaign found with that join code" — no crash.
- What if any tab component fails to load its data on render? The tab shows an inline error message with a description of what failed.
- What if the user navigates to the GM dashboard while offline from all AI services? Every AI-dependent component shows a placeholder state; the non-AI tabs remain fully functional.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST provide a single Gradio auth screen with two panels: "Sign In" and "Create Account". No separate registration URL or page is required.
- **FR-002**: Sign-in MUST validate the username and password against the existing `User` SQLite table by comparing `sha256(entered_password)` against the stored `hashed_password` value. On success, the user's identity is stored in a `gr.State` object for the active browser tab.
- **FR-003**: Account creation MUST insert a new row into the `User` table and immediately transition the UI to the authenticated campaign dashboard — no additional sign-in step after registration.
- **FR-004**: All sign-in and registration errors MUST be displayed as visible text inside the Gradio UI. Errors MUST NOT be logged to the server console only.
- **FR-005**: The application MUST launch as a pure Gradio app (`gr.Blocks().launch()`). No FastAPI ASGI wrapper or uvicorn entrypoint is required for standard use.
- **FR-006**: An authenticated GM MUST see a campaign dashboard listing all their campaigns, with each campaign's name, join code, and creation date visible.
- **FR-007**: GMs MUST be able to create a new campaign. Campaign names MUST be unique per account (case-insensitive); duplicates MUST be rejected with a visible UI error.
- **FR-008**: GMs MUST be able to enter a campaign and access a GM dashboard with these tabs: Characters, NPCs, Story History, World Notes, Session Plan, Players.
- **FR-009**: Players MUST join a campaign by entering only their **join code** and **player name** — no campaign name field. The join code is globally unique and identifies the campaign on its own.
- **FR-010**: Players MUST be able to access these tabs from their dashboard: Character (view/edit), Twin Chat, Story History.
- **FR-011**: All tabs that depend on an external AI service (Ollama, ComfyUI) MUST display a visible placeholder message when that service is unavailable, instead of crashing or showing a blank panel.
- **FR-012**: Every backend operation that can fail MUST surface its error as a visible message in the Gradio UI component nearest to the triggering action.
- **FR-013**: Character and NPC save operations MUST use upsert semantics: a matching name (case-insensitive) within the same campaign results in an update, not a duplicate record.
- **FR-014**: The image generation action MUST be present and visible in the UI even when the image backend is unavailable, with a clear placeholder state rather than a hidden or missing control.
- **FR-015**: The digital twin (twin chat) feature MUST be accessible from both the GM dashboard (for NPCs) and the Player dashboard (for the player's character), with a visible "AI unavailable" placeholder when Ollama is not running.
- **FR-016**: Sign-out MUST clear the user's `gr.State` and return the UI to the auth screen.
- **FR-017**: The join code for a campaign MUST be prominently displayed at the top of the GM dashboard when the GM is inside a campaign, making it easy to share with players at the table.
- **FR-018**: The World Notes tab MUST present a single Markdown text area per campaign. The GM can edit and save the content; the saved text is rendered as Markdown in the same tab. No separate note records or titles are required.
- **FR-019**: The campaign list MUST include an "Archive" button per campaign. Clicking it sets the campaign's `archived` flag to true and removes it from the default list view. Archived campaigns are not permanently deleted; all associated player, character, and history data is retained.
- **FR-020**: The GM MUST be able to create a new Session (with a name and optional date) from the Story History tab before logging events. Story events are linked to a session; events MUST be grouped and displayed under their parent session in the history view.
- **FR-021**: The Story History tab for players (FR-010) MUST display all public story events grouped by session in chronological order.
- **FR-022**: The Players tab in the GM dashboard MUST display a read-only list of all players who have joined the campaign, showing each player's name and their associated character name (if a character has been created). No remove or edit action is required.

### Key Entities *(include if feature involves data)*

- **User**: Authenticated GM identity. Stored in the `users` SQLite table with username and password fields.
- **Campaign**: Story container owned by a User. Identified globally by a unique 6-character join code. Name is unique per owner (case-insensitive). Carries a `world_notes` text field (Markdown) and an `archived` boolean flag. Archived campaigns are hidden from the GM's default campaign list but their data is retained.
- **Player**: Named identity within a campaign, linked to a Character. Created when a player first joins with a join code + player name pair.
- **Character**: Player-controlled entity in a campaign. Upserted on name match (case-insensitive, per campaign).
- **NPC**: GM-controlled entity in a campaign. Upserted on name match (case-insensitive, per campaign).
- **DigitalTwin**: Stores AI conversation history for character/NPC twin chats. One DigitalTwin per Character or NPC entity.
- **Session**: A named, dated game-night record belonging to a campaign. Created by the GM before logging events. Has a `name` and `date` (defaults to creation date). Acts as a grouping header for StoryEvents.
- **StoryEvent**: A single narrative event logged by the GM, linked to a Session. Has a `description` field.
- **SessionPlan**: AI-assisted or manually authored plan for an upcoming campaign session.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An existing GM can sign in and reach their campaign dashboard within 2 clicks and 10 seconds on a local machine.
- **SC-002**: A new visitor can create an account and reach their campaign dashboard in a single form submission — no page reload or additional login step.
- **SC-003**: A player with a valid join code can reach their player dashboard by entering 2 fields (join code + player name) and clicking one button.
- **SC-004**: Every UI tab (GM and Player) must render without crashing when the app is started locally, regardless of whether Ollama or ComfyUI is running.
- **SC-005**: 100% of backend failures that would previously cause a silent blank or crash in the UI now display a visible, human-readable error message.
- **SC-006**: The app launches with a single standard Gradio command — no uvicorn, no FastAPI wrapper required.
- **SC-007**: No open tasks in `/specs` reference the old FastAPI entrypoint or three-field player join flow after this feature is implemented.

---

## Assumptions

- The existing `User` SQLite model schema (including `hashed_password`) is retained as-is for DB compatibility. Auth simplification removes the bcrypt+threading complexity from the runtime code path, not the database column.
- Password authentication uses SHA-256 hashing (`sha256(password)` stored in `hashed_password`). No bcrypt dependency or threading workaround is required. This is acceptable for the pre-product-market-fit phase per the project constitution (Principle VI).
- Gradio's `gr.State` per-tab isolation is relied upon for session management — no server-side session cookie or token store is needed.
- The `DigitalTwin` model is the implementation of what the team colloquially calls "twins" or "digital twins". There is no separate `GameStar` model in the codebase.
- Ollama and ComfyUI are optional local services. Their absence must not prevent the app from launching or any UI tab from rendering.
- Stale task artifacts in specs 002 and 003 will be marked `[SUPERSEDED]` rather than deleted, to preserve audit history.
- Password reset, email verification, and OAuth are out of scope for this phase.
- Mobile UI optimization is out of scope; the app targets desktop/tablet browsers.