# Feature Specification: Authentication & Admin UI

**Feature Branch**: `002-auth-admin-ui`

**Created**: 2026-06-19

**Status**: Draft

**Input**: User description: "I want to add basic authentication and admin UI, so that i can access the campaings already created on other sesions. This way we can continue the story were it stoped. I'll also like to add some restrictions on campaing, characters and NPC creations, for example there should not have exactly the same name. If the create action is used over the same characters or NPC, then it should update the old one instead of creating a new one"

---

## Clarifications

### Session 2026-06-19

- Q: How does the system identify a returning player to restore their specific character when multiple players share the same campaign? → A: Player provides a player name (separate from character name) alongside the join code. This becomes their persistent identity within the campaign and is linked to their character.
- Q: What is the GM account registration model? → A: Open registration — any visitor can sign up and become a GM with their own independent account and campaigns.
- Q: Which session persistence mechanism should be used given Gradio's tab-local state limitation? → A: Gradio built-in auth (initial phase) — Gradio's `auth` parameter with a callable validating credentials against the application database. FastAPI deferred to a future phase. Registration is served via a companion unauthenticated Gradio interface at a separate path (e.g. `/register`).
- Q: What format and length should join codes use? → A: Short alphanumeric — 6 uppercase characters/digits (e.g., `A3KP72`), auto-generated at campaign creation.
- Q: Should players require an additional secret (PIN) beyond campaign name + join code + player name? → A: No player PIN — the join code is the shared campaign secret; per-player passwords are out of scope for this phase.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — GM Logs In and Resumes a Campaign (Priority: P1)

A GM opens StoryWeaver in a new browser session, authenticates with their credentials, sees all of their existing campaigns listed, and selects one to resume — picking up the story exactly where it stopped.

**Why this priority**: Without persistent session access, every browser restart orphans campaigns and story progress. This is the core pain this feature solves and a prerequisite for all other admin scenarios.

**Independent Test**: Create a campaign in one browser session, close the session, re-open the app, log in with the same credentials, and verify the campaign and its story content are retrievable and interactive.

**Acceptance Scenarios**:

1. **Given** a user has valid credentials, **When** they submit the login form, **Then** they are authenticated and redirected to their campaign dashboard showing all previously created campaigns.
5. **Given** a visitor with no existing account, **When** they complete the registration form with a unique username/email and password, **Then** a new GM account is created and they are immediately authenticated and redirected to their (empty) campaign dashboard.
6. **Given** a username or email address already registered, **When** another visitor attempts to register with the same value, **Then** registration is rejected with a clear error identifying the conflict.
2. **Given** an authenticated GM, **When** they select a campaign from the dashboard, **Then** the campaign loads with all previously stored story history, characters, and NPCs intact.
3. **Given** a user with invalid credentials, **When** they submit the login form, **Then** the system displays a clear error message and does not grant access.
4. **Given** an unauthenticated user, **When** they attempt to access any campaign or admin page directly, **Then** they are redirected to the login page.

---

### User Story 2 — GM Shares Campaign Access with Players (Priority: P1)

An authenticated GM can view their campaign's join code and campaign name from the admin UI, then share those credentials with players so players can return to their characters in future sessions without the GM needing to be present at that moment.

**Why this priority**: Player session continuity depends entirely on the GM being able to communicate the join credentials. Without this, players cannot independently resume their characters between sessions.

**Independent Test**: Create a campaign as GM, navigate to the campaign's admin detail page, copy the displayed join code and campaign name, open an incognito window, enter those values along with a player name, and verify the player's existing character and story context are accessible.

**Acceptance Scenarios**:

1. **Given** an authenticated GM viewing a campaign's admin page, **When** they view the campaign details, **Then** the campaign's join code and campaign name are clearly displayed and copyable.
2. **Given** a player who has the campaign name and join code, **When** they enter those values along with their player name on the player login/join screen, **Then** they are taken into the campaign and can access their previously created character and history.
3. **Given** a player with a valid join code but wrong campaign name, **When** they attempt to join, **Then** the system rejects the attempt with a clear error.
4. **Given** a player returning to a campaign they previously joined, **When** they enter the campaign name, join code, and their player name again, **Then** they are placed back in their character's session with all previous story context intact.

---

### User Story 3 — GM Manages Campaigns from the Admin UI (Priority: P2)

An authenticated GM can view, create, and navigate all of their campaigns from a dedicated admin interface — separate from the in-game experience.

**Why this priority**: The admin UI surfaces the value of persistent authentication. Without it, authenticated users still have no structured way to manage their content across sessions.

**Independent Test**: Log in, create two campaigns from the admin UI, verify both appear in the campaign list, and navigate into each to confirm they are independent.

**Acceptance Scenarios**:

1. **Given** an authenticated GM, **When** they visit the admin interface, **Then** they see a list of all campaigns they own with name, last-modified date, join code, and a quick-access link.
2. **Given** an authenticated GM on the admin interface, **When** they create a new campaign, **Then** it appears in their campaign list and is immediately accessible.
3. **Given** an authenticated GM, **When** they attempt to create a campaign with a name that already exists in their account, **Then** the system prevents the creation and displays a clear message informing them a campaign with that name already exists.

---

### User Story 4 — Upsert Behavior for Characters and NPCs (Priority: P2)

When a GM or Player uses a "create character" or "create NPC" action with a name that already exists in the campaign, the system updates the existing entity rather than creating a duplicate.

**Why this priority**: Duplicate characters and NPCs break campaign consistency and degrade AI twin quality. Upsert behavior eliminates this class of error without requiring the user to first check for duplicates manually.

**Independent Test**: Create a character named "Kira", then invoke the create action again for "Kira" with different attributes. Verify only one character named "Kira" exists and its attributes reflect the latest values.

**Acceptance Scenarios**:

1. **Given** a character named "Kira" exists in a campaign, **When** a create-character action is submitted with the name "Kira", **Then** the existing character record is updated with the new values and no duplicate is created.
2. **Given** an NPC named "Elder Varos" exists, **When** a create-NPC action is submitted with the name "Elder Varos", **Then** the existing NPC is updated and no duplicate is created.
3. **Given** no character named "Bram" exists, **When** a create-character action is submitted for "Bram", **Then** a new character is created normally.
4. **Given** a character named "kira" exists (different casing), **When** a create-character action is submitted with the name "KIRA", **Then** the system treats this as the same character and performs an update rather than creating a duplicate.

---

### User Story 5 — Campaign Name Uniqueness Enforcement (Priority: P3)

Within a user's account, campaign names are unique. Attempting to create a campaign with a duplicate name is rejected with a clear explanation.

**Why this priority**: Unlike characters and NPCs (which silently upsert), campaigns are top-level organizational units; silent upsert would be confusing. Explicit rejection with a clear error is safer here.

**Independent Test**: Create a campaign named "The Iron Crown", then attempt to create another campaign with the same name. Verify only one campaign exists and the second attempt returned an error.

**Acceptance Scenarios**:

1. **Given** a campaign named "The Iron Crown" exists, **When** the user attempts to create another campaign named "The Iron Crown", **Then** creation is blocked and the user sees: "A campaign named 'The Iron Crown' already exists."
2. **Given** a campaign name that differs only in casing (e.g., "the iron crown"), **When** the user attempts to create it, **Then** the system treats it as a duplicate and blocks creation.

---

### Edge Cases

- What happens when a user is idle for an extended period? Session expires and they are prompted to log in again.
- What if a player enters a join code for a campaign that has been deleted? The system displays a clear error: the campaign no longer exists.
- What if an NPC and a character have the same name within the same campaign? They are separate entity types; the name uniqueness constraint applies within each type independently.
- What if a user creates a campaign and another user creates a campaign with the same name? Campaign name uniqueness is scoped per user account; different users may have same-named campaigns.
- What if two players attempt to rejoin the same campaign simultaneously using the same join code? Both are admitted; join codes are not single-use.
- What if two different people join using the same player name in the same campaign? They are treated as the same Player identity and both access the same character record. This is acceptable for cross-device use by the same person; the GM is responsible for ensuring players use distinct names.
- What if a player joins with a player name that has never been used in this campaign before? A new Player record is created and no character is linked until one is created in-session.
- Should players need a PIN or password in addition to campaign name + join code + player name? No — per-player authentication secrets are out of scope for this phase. The join code is the campaign-level shared secret; the social trust model (GM controls who receives the join code) is sufficient.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST provide a login form that accepts credentials (username/email and password) and authenticates the user.
- **FR-016**: The system MUST provide an open registration form allowing any visitor to create a new GM account with a username/email and password. Registration MUST be accessible without prior authentication, served at a dedicated URL path separate from the main authenticated application.
- **FR-017**: Username and email address MUST each be unique across all registered accounts; duplicate registration attempts MUST be rejected with a descriptive error.
- **FR-002**: The system MUST maintain an authenticated session across page reloads and new tabs within the same browser. Session state is managed entirely by the application server via a cookie set at login, requiring no additional client-side configuration.
- **FR-003**: Authenticated users MUST be able to view a dashboard listing all campaigns associated with their account.
- **FR-004**: Authenticated users MUST be able to resume any of their campaigns from the dashboard and continue where they left off.
- **FR-005**: The system MUST block unauthenticated access to all campaign, character, and NPC data and redirect to the login page.
- **FR-006**: The system MUST provide an admin UI for creating, listing, and navigating campaigns.
- **FR-007**: Each campaign's admin detail view MUST prominently display the campaign's name and join code (6-character uppercase alphanumeric) in a copyable format so the GM can share them with players.
- **FR-018**: The system MUST auto-generate a unique 6-character uppercase alphanumeric join code at campaign creation time. Join code uniqueness MUST be enforced across all campaigns system-wide.
- **FR-008**: Players MUST be able to rejoin a campaign from a new browser session by providing the campaign name, join code, and player name — without needing GM credentials.
- **FR-009**: When a returning player provides a valid campaign name, join code, and player name, the system MUST restore their previous character and story context. The combination of campaign name + join code + player name uniquely identifies the player's identity within the campaign.
- **FR-010**: When a create-campaign action is submitted with a name already used by an existing campaign under the same user account, the system MUST reject the request and return a descriptive error — campaigns are NOT silently upserted.
- **FR-011**: Campaign name uniqueness MUST be enforced case-insensitively within a user account.
- **FR-012**: When a create-character action is submitted with a name that matches an existing character (case-insensitive) in the same campaign, the system MUST update the existing character record rather than creating a new one.
- **FR-013**: When a create-NPC action is submitted with a name that matches an existing NPC (case-insensitive) in the same campaign, the system MUST update the existing NPC record rather than creating a new one.
- **FR-014**: Character name uniqueness and NPC name uniqueness MUST be scoped per campaign, and the two namespaces are independent.
- **FR-015**: The system MUST provide a secure logout action that invalidates the current session.

### Key Entities *(include if feature involves data)*

- **User Account**: Represents an authenticated GM identity. Has credentials and owns zero or more campaigns.
- **Campaign**: Top-level story container owned by a user. Name is unique per user (case-insensitive). Has a join code that players use to access it.
- **Character**: Player-controlled entity scoped to a campaign. Name is unique per campaign (case-insensitive) among characters.
- **NPC**: GM-controlled entity scoped to a campaign. Name is unique per campaign (case-insensitive) among NPCs.
- **Session**: Authenticated session token that persists user identity across browser interactions.
- **Player**: A named identity within a campaign, created when a person first joins using their chosen player name alongside the campaign name and join code. A Player record is scoped to a single campaign and is linked to exactly one Character (or none until one is created). Player name is unique per campaign.
- **Join Code**: A 6-character uppercase alphanumeric code (e.g., `A3KP72`) auto-generated at campaign creation. Unique per campaign. Players combine the join code with the campaign name and a player name to establish or restore their campaign identity.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An authenticated GM can access any of their previously created campaigns within 3 clicks from the login page.
- **SC-002**: A GM can locate and copy the join code and campaign name for any campaign within 2 clicks from the campaign dashboard.
- **SC-003**: A player who has been given a campaign name and join code can rejoin the campaign and access their character within 60 seconds of opening the app.
- **SC-004**: 100% of attempts to create a duplicate campaign name (case-insensitive, per account) are rejected with a user-visible error message.
- **SC-005**: 100% of create-character or create-NPC actions on an existing name (case-insensitive, per campaign) result in an update rather than a duplicate record.
- **SC-006**: All campaign story history, characters, and NPCs created in a previous session are fully accessible after logging in or rejoining from a new session.
- **SC-007**: An unauthenticated direct URL request to any protected page redirects to the login page within one second.

---

## Assumptions

- The existing campaign join-code + display-name flow (defined in spec 001) is the mechanism players use to join. This feature makes that join code visible and shareable from the admin UI, and ensures it persists across sessions.
- "Basic authentication" means a username/email and password login with open self-registration, stored securely within the application — no external OAuth or SSO provider is required for this phase.
- Each registered account represents an independent GM with their own campaigns; there is no multi-owner or team-ownership model in scope. Multiple GM accounts are supported and fully isolated from each other.
- Session persistence is browser-level (cookie or local storage token); cross-device sync of active session state is out of scope.
- The admin UI is built with Gradio, consistent with the project-wide UI technology constraint. Authentication uses Gradio's built-in `auth` parameter with a callable that validates credentials against the application database. A companion unauthenticated Gradio interface handles new account registration. FastAPI is the planned upgrade path for a future phase when a richer auth flow is needed.
- Account registration (sign-up) is in scope as a minimal companion to login; social sign-up is out of scope.
- Password reset via email is out of scope for this feature.
- Join codes are permanent per campaign (not rotatable in this phase); sharing a join code gives ongoing access.
- Player identity within a campaign is established by the combination of campaign name + join code + player name. No password, PIN, or separate account is required for players. Player name uniqueness is enforced per campaign (case-insensitive). Per-player authentication secrets are explicitly out of scope for this phase.
- Mobile UI optimization is out of scope; the admin interface targets desktop/tablet browsers.