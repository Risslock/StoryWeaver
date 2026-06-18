# Feature Specification: StoryWeaver — Project Scope & Vision

**Feature Branch**: `001-project-scope`

**Created**: 2026-06-18

**Status**: Draft

---

> StoryWeaver is an AI-assisted **narrative companion** for tabletop RPGs — starting with Earthdawn 4E — that brings characters and NPCs to life, generates evocative imagery, and remembers the story, so the table can stay focused on playing.

This document is the **master scope spec**. Every feature spec under `/specs` should trace back to a goal or capability defined here.

**Primary purpose**: Learning and portfolio project — demonstrating spec-driven, harness-evaluated, multi-agent AI system design on a meaningful real-world domain.

---

## Clarifications

### Session 2026-06-18

- Q: What is the simplest viable authentication mechanism for FR-012 (campaign code + display name, lightweight email/password, or managed auth provider)? → A: Campaign join code + display name — no persistent accounts; users pick a display name and enter a campaign join code to join as Player or GM.
- Q: What is the granularity of NPC visibility control for Players (FR-007)? → A: Hidden by default; GM reveals per NPC — each NPC has a visibility toggle (default hidden); the GM flips it to make an NPC visible to Players.
- Q: When the local AI provider is unavailable at startup, does the system start in degraded mode or refuse to launch? → A: Degraded mode — the app starts, surfaces a clear banner indicating AI is unavailable, and blocks only AI-dependent actions.
- Q: Can a Player own multiple Characters in the same Campaign? → A: Yes — a Player may own multiple characters in the same campaign and interact with each via its own digital twin.
- Q: What is the measurable load-time target for SC-008 (story history with 5+ sessions and 20+ events)? → A: Under 5 seconds from request to fully navigable history.

---

## Goals

### Builder Goals (the real "why")

Demonstrate, on a substantial real-world domain, the ability to:

- Practice spec-driven development end-to-end — specs as source of truth, traceable to code.
- Apply harness engineering to non-deterministic AI agents — measurable, regression-tested behaviour.
- Design a multi-agent system with role- and entity-scoped agents and tools.
- Build a provider-agnostic AI layer and pluggable image generation.
- Run a clean monorepo that deploys locally or in the cloud, fully containerized.

Success here is measured by **engineering quality and demonstrability**, not user growth or revenue.

### Product Goals (value at the table)

For the people actually playing, StoryWeaver should:

- **Reduce GM prep and improvisation load** — instant, in-character NPC dialogue and behaviour.
- **Deepen immersion** — portraits and scene art that make the world tangible.
- **Preserve campaign memory** — a living story history nobody has to maintain by hand.
- **Augment, never replace** — the humans stay the authors; the AI is a creative assistant.

---

## User Scenarios & Testing

### User Story 1 — Player Character Companion (Priority: P1)

A player creates their character and uses its digital twin to explore what the character would say or do in situations that arise during play.

**Why this priority**: The character digital twin is the core product differentiator. All other features derive value from it, and it must be independently usable before anything else is built.

**Independent Test**: Create a character profile and have the digital twin respond to three distinct in-game scenarios; verify each response is in-character and consistent with the profile without requiring image generation or multi-user features.

**Acceptance Scenarios**:

1. **Given** a player has no character in the system, **When** they complete the guided character creation flow, **Then** a character profile is saved with identity, discipline, key attributes, talents, background, personality, goals, and relationships.
2. **Given** a complete character profile exists, **When** a player asks the twin "What would my character do in this situation?", **Then** the twin responds in character, grounded in the character's personality, background, and current story context.
3. **Given** a character profile exists, **When** the player views their character sheet, **Then** all captured data is displayed accurately and completely.
4. **Given** a player submits an out-of-character or nonsensical prompt, **When** the twin processes it, **Then** the system handles it gracefully without producing a confusing or harmful response.

---

### User Story 2 — GM NPC Management (Priority: P2)

A GM creates and manages multiple NPCs with digital twins, generating consistent in-character dialogue and behaviour on demand during and between sessions.

**Why this priority**: NPC twins directly address the "running a vivid world under time pressure" pain point and multiply GM effectiveness across complex scenes.

**Independent Test**: Create two NPC profiles with distinct personalities; request in-character dialogue for the same scene from each twin; verify responses are clearly distinct and consistent with each NPC's profile.

**Acceptance Scenarios**:

1. **Given** a GM has created an NPC profile, **When** they request dialogue for a specific scene, **Then** the system generates a contextually appropriate, in-character response grounded in the campaign's story context.
2. **Given** multiple NPC profiles exist, **When** the GM switches between twins, **Then** each NPC responds distinctly according to its own profile and history.
3. **Given** a GM account, **When** they access GM-only views, **Then** private world and lore notes are visible and not accessible to Players.
4. **Given** an NPC with minimal profile data, **When** dialogue is requested, **Then** the system either generates a reasonable response or clearly indicates which profile gaps are limiting quality.

---

### User Story 3 — Campaign Story History (Priority: P2)

Players and the GM can review a persistent, shared timeline of the campaign's events, sessions, and decisions — without anyone having to maintain it by hand.

**Why this priority**: Story history is the shared context that makes digital twin responses accurate and keeps the campaign coherent over time. It is a dependency for both twin quality and session planning.

**Independent Test**: Log five events across two sessions; verify all events appear in the correct order in the story history and are accessible to both GM and the relevant players after a refresh.

**Acceptance Scenarios**:

1. **Given** a GM logs a story event, **When** a player refreshes their campaign view, **Then** the new event appears correctly in the shared story history.
2. **Given** a campaign with multiple sessions, **When** a user queries the story history, **Then** events are retrievable in chronological order with their session context.
3. **Given** a digital twin is asked about a recent campaign event, **When** it generates a response, **Then** the response reflects awareness of that event from the story history.

---

### User Story 4 — Character and Scene Image Generation (Priority: P3)

Players and the GM generate portraits for characters and illustrations for scenes to make the world tangible.

**Why this priority**: Significantly enhances immersion but is not required for the core twin or history experience; it comes after the foundation is in place.

**Independent Test**: Generate a character portrait from a profile and a scene illustration from a description; a human reviewer judges each image as meaningfully reflecting its request.

**Acceptance Scenarios**:

1. **Given** a character profile with physical description traits, **When** a portrait is requested, **Then** an image is generated that visually reflects those described traits.
2. **Given** a GM describes a location and mood, **When** a scene illustration is requested, **Then** an appropriate image is produced.
3. **Given** the image provider is unavailable, **When** a user requests an image, **Then** the system shows a clear error message and the rest of the campaign continues without interruption.

---

### User Story 5 — Shared Campaign Session (Priority: P3)

A GM and one or more players join the same campaign, each with role-appropriate access, and see shared updates after refreshing.

**Why this priority**: Enables the "at the table together" experience; requires characters, twins, and story history to be functional first.

**Independent Test**: A GM and one player join the same campaign; the GM logs an event and creates a private NPC note; the player refreshes and verifies they see the shared event but not the private GM note.

**Acceptance Scenarios**:

1. **Given** a campaign exists, **When** a new user joins using the campaign identifier, **Then** they are assigned the correct role (Player or GM) and see only role-appropriate content.
2. **Given** a GM has logged an event, **When** a player refreshes their view, **Then** the event appears in their shared story history.
3. **Given** two users access the same campaign simultaneously, **When** both perform actions within their role scope, **Then** no data corruption or conflicting state results.

---

### User Story 6 — GM Session Planning (Priority: P4)

A GM uses a dedicated planning tool to prepare for the next session, drawing on the campaign's story history and conversing with a planning agent.

**Why this priority**: High value for GMs but depends on a mature story history; it is the last capability to be built.

**Independent Test**: With at least one completed session in the story history, request a session plan and verify it references specific past events and open plot threads from that history.

**Acceptance Scenarios**:

1. **Given** a GM has at least one session logged, **When** they use the session planning tool, **Then** the system generates a plan referencing relevant past events, open plot threads, and available NPCs.
2. **Given** a session plan is generated, **When** the GM edits or annotates it, **Then** changes persist and are available the next time the GM opens the planning tool.
3. **Given** the story history is empty (first session), **When** the GM uses the planning tool, **Then** the system produces a usable starting-point plan and surfaces that history is minimal.

---

### Edge Cases

- What happens when a player asks the twin something entirely outside the character's experience or knowledge?
- How does the system behave when image generation produces content that is inappropriate or clearly low quality?
- **[Resolved]** When the local AI provider is unavailable at startup, the system starts in degraded mode: a persistent banner informs all users that AI features are unavailable, and actions that require the AI provider (twin dialogue, image generation, session planning) are disabled until the provider becomes reachable. Non-AI features (story history browsing, character sheet viewing, campaign navigation) remain fully functional.
- How does the story history behave when a session has no logged events?
- What happens if a GM removes a player from a campaign mid-session?
- How does a twin respond when the story history contains contradictory information about the same event?
- How does the system behave during a mid-campaign provider swap (LLM or image)?

---

## Requirements

### Functional Requirements

- **FR-001**: System MUST provide a narrative-first character creation flow that captures identity, discipline, key attributes, talents, background, personality, goals, and relationships for an Earthdawn 4E character, with sanity-check validation (required fields, basic consistency) but without enforcing every legal build rule. A Player may create multiple Characters within the same Campaign.
- **FR-002**: System MUST create a persistent digital twin agent for each Character and NPC that generates in-character dialogue, behaviour, and suggested actions grounded in the entity's profile and story context.
- **FR-003**: System MUST feed relevant story history into digital twin context so that responses reflect campaign events.
- **FR-004**: System MUST generate portrait images for characters based on their physical description and traits.
- **FR-005**: System MUST generate scene illustrations for locations and key moments as described by the GM.
- **FR-006**: System MUST maintain a persistent, queryable campaign story history recording sessions, events, decisions, NPC and world-state changes, and open plot threads.
- **FR-007**: System MUST enforce role-scoped access: Players access only their own character and shared campaign content; GMs access all campaign content including private world and lore notes. NPC profiles are hidden from Players by default; the GM may reveal individual NPCs to Players via a per-NPC visibility toggle.
- **FR-008**: System MUST support a shared campaign where a GM and multiple players participate, with shared content visible to appropriate roles after a refresh cycle. Real-time conflict resolution is not required in v1.
- **FR-009**: System MUST provide a GM-only session planning tool that uses story history as context and supports interaction with a planning agent.
- **FR-010**: System MUST be deployable in two modes — local-only (no cloud services required) and cloud-hosted — using the same codebase and the same demo scenario.
- **FR-011**: System MUST allow AI providers (LLM and image generation) to be swapped via configuration only, with no code changes required.
- **FR-012**: System MUST associate users with a role (Player or GM) within a campaign via a campaign join code and a user-chosen display name. No persistent accounts or credentials are required. A user joins a campaign by entering its join code and selecting their display name; the GM role is assigned to the campaign creator.
- **FR-013**: System MUST NOT store, redistribute, or bundle copyrighted rulebook text, official art, or proprietary game content. Users supply their own reference material.

### Explicit Non-Goals

The following are out of scope. Any graduation into scope requires a deliberate spec amendment.

- Dice rolling, combat resolution, talent/skill test adjudication, or XP/Karma math enforcement.
- Virtual tabletop features: maps, grids, tokens, fog of war, or line-of-sight.
- Full rules-validated character building (guaranteeing a legal Earthdawn 4E build).
- Real-time collaborative editing or CRDT conflict resolution (v1 uses refresh-based sync).
- Native mobile applications.
- Billing, large-scale multi-tenant operations, or marketing infrastructure.

### Key Entities

- **Campaign**: The shared container for a group's game. Holds one GM, zero or more Players, all sessions, NPCs, and world notes.
- **Character**: A Player-owned entity with structured profile data powering a digital twin. Scoped to a Campaign. A Player may own multiple Characters within the same Campaign, each with its own independent digital twin.
- **NPC**: A GM-owned entity with a profile powering a GM-accessible digital twin. Hidden from Players by default; the GM controls a per-NPC visibility toggle to reveal an NPC to all Players in the campaign.
- **Digital Twin**: A persistent, scoped agent tied to a Character or NPC. Generates in-character responses using the entity's profile and story context.
- **Story History**: An ordered log of sessions, events, decisions, and world-state changes for a Campaign. Queryable by digital twins and the session planning tool.
- **Session**: A discrete play session within a Campaign containing logged events and outcomes.
- **User**: An authenticated person with a role (Player or GM) in one or more Campaigns.

---

## Success Criteria

### Measurable Outcomes

- **SC-001**: A GM and at least one player can complete the full end-to-end demo — create a character, converse with its digital twin, generate a portrait and a scene illustration, and view the result in shared story history — without any step failing or requiring a workaround.
- **SC-002**: The system runs the same end-to-end demo correctly in local-only mode (no internet required) and in cloud-hosted mode using the same codebase.
- **SC-003**: Swapping the LLM provider or image generation provider requires only configuration or environment-variable changes — verified by running the demo with at least two different provider configurations.
- **SC-004**: All agent and tool behaviours have automated harness evaluations that can be re-run as regression tests; no milestone is considered complete until all its harness scenarios pass.
- **SC-005**: Any feature in the system can be traced from its written specification through its harness evaluation to its implementation code.
- **SC-006**: Character digital twin responses are judged in-character and contextually appropriate by a human reviewer for at least 8 out of 10 distinct test interactions.
- **SC-007**: Scene and portrait images are judged to meaningfully reflect the requested subject by a human reviewer for at least 7 out of 10 generation requests.
- **SC-008**: The story history for a campaign with at least 5 sessions and 20 logged events loads and is fully navigable within 5 seconds of the request — verified by an automated timing assertion in the harness.

---

## Assumptions

- **Solo developer**: This is a single-developer learning and portfolio project; decisions prioritize clarity, demonstrability, and engineering quality over team-scale abstractions or operational scale.
- **Earthdawn 4E first**: The initial game system is Earthdawn 4E; the architecture must remain system-agnostic so a second RPG system can be added as an isolated package without structural changes to shared components.
- **Users own their rulebooks**: StoryWeaver does not supply copyrighted content; users provide their own Earthdawn 4E reference material.
- **Refresh-based sync is sufficient for v1**: Polling/refresh delivers an acceptable "at the table together" experience at a fraction of the cost of true real-time collaboration, which is deferred.
- **Character creation is narrative-first, not rules-enforced**: Sanity checks (required fields, basic consistency) replace full rules validation, which is explicitly out of scope.
- **Local AI is available for development**: Development and regression testing use a local LLM; cloud providers are integration-tested separately behind the provider abstraction.
- **Authentication approach resolved**: Campaign join code + display name. Users join by entering the campaign join code and choosing a display name; the campaign creator holds the GM role. No persistent accounts or credentials required. (Resolved 2026-06-18, see Clarifications.)
- **Agent framework is an open decision**: The orchestration framework must be selected via Architecture Decision Record (ADR) before milestone 2 begins.
- **Sheet import format is deferred**: Whether and which external character sheet formats can be imported is an open question, deferred to a dedicated spec.
- **Project license is pending**: A code license (MIT or Apache-2.0 recommended) must be added before any public release.

---

## Scope by Milestone

| Phase | In Scope | Explicitly Deferred |
|-------|----------|---------------------|
| **MVP** | Guided character builder (FR-001), one character digital twin with local AI (FR-002, FR-003), basic story history (FR-006), single shared campaign (FR-007, FR-008) | Image generation, cloud providers, multi-user polish |
| **Core Demo** | Character + scene image generation (FR-004, FR-005), GM NPC twins (FR-002), role-scoped UI (FR-007), session planning (FR-009) | Real-time sync, second rule system |
| **Cloud** | Cloud AI/image providers (FR-011), cloud-hosted multiplayer (FR-010), cloud storage | True real-time collaboration |
| **Beyond** | System-agnostic core, a second RPG system | Mechanics automation, VTT (remain non-goals) |
