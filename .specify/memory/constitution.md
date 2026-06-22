<!--
## Sync Impact Report

**Version Change**: 1.3.0 → 1.4.0
**Type of Bump**: MINOR — material update to Principle IV (image generation provider
clarified; HuggingFace API designated as current MVP provider; ComfyUI deferred);
TODO(LICENSE) resolved (LICENSE file confirmed present in repo).

### Principles Modified
- **IV. Local-First, Cloud-Optional**: Added explicit carve-out for image generation —
  HuggingFace Inference API (free tier) is the current image generation provider for
  the MVP; ComfyUI/SD (local) is deferred to a later milestone. All other local-first
  constraints (LLM, embeddings, vector store, DB) remain unchanged.

### Principles Added
- None.

### Sections Modified
- **Technology Stack Constraints**: Removed `TODO(LICENSE)` — LICENSE file confirmed
  present in the repository.

### Templates Reviewed
- `.specify/templates/plan-template.md` ✅ — Constitution Check gate is generic; no change required.
- `.specify/templates/spec-template.md` ✅ — No conflicts; no change required.
- `.specify/templates/tasks-template.md` ✅ — No structural change required.

### Deferred TODOs
- TODO(RATIFICATION_DATE): Carried from v1.0.0 — ratification date kept as 2026-06-18.
-->

# StoryWeaver Constitution

## Core Principles

### I. Spec-Driven Development (NON-NEGOTIABLE)

Every feature MUST begin with a written spec in `/specs` before any code is written.
Specs define problem statement, behaviour, interfaces, and acceptance criteria.
When code and spec disagree, **the spec wins**; code is updated to match.
Implementation and review MUST trace back to a spec.
The `README.md` is the top-level source of truth for architecture and intent; it MUST be
updated deliberately and kept consistent with `/specs`.
After every implementation milestone, `README.md` MUST be updated to reflect the **current
implemented state** of the project — including completed features, active limitations, and
changed setup or usage instructions. A README that describes planned or superseded
functionality is a defect.

**Rationale**: Non-deterministic AI components make "just try it" development expensive to
reverse. Specs provide a stable contract that lets the team iterate on prompts and agents
with confidence, not guesswork. An accurate README prevents the team from building on stale
assumptions about what the system actually does today.

### II. Provider Abstraction

All AI (LLM, embeddings, image generation) and storage (DB, vector store) backends MUST
sit behind thin abstraction layers (`packages/llm/`, `packages/imagegen/`,
`packages/rag/`, `packages/storage/`).
Switching providers MUST require only a config/environment-variable change — no code changes.
New provider implementations MUST conform to the existing abstraction interface before
being integrated.

**Rationale**: The AI provider landscape evolves rapidly. Coupling business logic to a
specific SDK or model means expensive rewrites every time the landscape shifts.
Abstraction layers also enable local-first development (Ollama) with a clear upgrade
path to cloud providers.

### III. Package Isolation

All functionality MUST live in clearly scoped packages under `packages/`.
Each package MUST be independently testable and expose a clean public interface.
Game-system rules (e.g., `packages/rules_earthdawn/`) MUST be isolated packages so
additional rule systems can be added without touching other packages.
No package may exist solely for organizational purposes; each MUST have a declared
domain responsibility.
Complexity (extra packages, cross-package dependencies) MUST be explicitly justified
in the relevant spec or plan.

**Rationale**: A monorepo with poorly bounded packages degrades into a distributed
monolith. Isolation keeps individual packages understandable, testable, and replaceable,
and it makes the "add a second rule system" path tractable.

### IV. Local-First, Cloud-Optional

Default operation MUST work entirely without cloud services for core features:
local LLM (Ollama), local embeddings (nomic-embed-text via Ollama),
local vector store (ChromaDB), local DB (SQLite).
Cloud providers are opt-in upgrades controlled via environment variables.
No code path may *require* a cloud service to function at runtime unless it is
explicitly gated behind a provider config that also has a local equivalent — or is
explicitly designated as a temporary MVP exception (see below).

**Image generation exception (MVP)**: The HuggingFace Inference API (free tier) is the
designated image generation provider for the current MVP stage. ComfyUI / Stable Diffusion
(local image generation) is planned but deferred to a later milestone. This is the one
intentional cloud dependency in the MVP; it MUST be gated by a provider config so that
swapping to a local provider requires only an environment-variable change (Principle II).
When HuggingFace is unavailable or unconfigured, the UI MUST show a clear placeholder
per Principle VII — never a crash or blank panel.

**Rationale**: Tabletop RPG sessions happen in varied environments (offline, low-bandwidth,
privacy-sensitive). Local-first ensures StoryWeaver is useful and private by default, with
cloud as an upgrade — not a dependency. The HuggingFace free tier removes the ComfyUI
setup burden at MVP stage while the abstraction layer keeps the local upgrade path open.

### V. Harness-Driven Agent Quality

Agent and tool behaviour is non-deterministic; subjective "looks good" review is
insufficient. Every agent and every tool MUST have eval coverage in `/harness` before a
milestone is considered complete.
Harness evals MUST be deterministic in their scoring (even when exercising non-deterministic
models) and MUST be re-runnable as regression tests.
A milestone's acceptance criteria MUST be expressed as harness scenarios or automated
assertions, not manual spot-checks alone.

**Rationale**: Without measurable evals, prompt changes and model upgrades silently
degrade behaviour. Harnesses make quality visible and regressions detectable.

### VI. Product-First Development

User-facing features that drive engagement and usage MUST take priority over infrastructure
complexity, security hardening, and technical polish.
Authentication MUST remain mocked using the existing SQLite database and the `User`,
`Player`, and `GameStar` SQLAlchemy models until product-market fit is established; no
production auth stack shall be introduced before that milestone.
Features MUST be evaluated primarily by whether they deliver observable value to users, not
by whether they satisfy non-functional requirements (performance benchmarks, audit logging,
security hardening) — those are explicitly deferred.
New scope MUST be rejected if it does not directly improve user experience or feature
breadth; technical debt that does not impede feature delivery SHOULD be tolerated.

**Rationale**: StoryWeaver is in a pre-product-market-fit phase. Over-engineering
infrastructure before validating that users want the product wastes the most scarce
resource: focus. Mock auth and a Gradio-only UI eliminate entire categories of complexity
(session tokens, CORS, state synchronisation) so the team ships features instead.

### VII. Placeholder-First & Explicit Failures

Every feature MUST be implemented in two passes: a visible placeholder stub first, then
real logic wired in on top.
A placeholder MUST render a clear, user-visible message such as
`"[Feature name] — not yet implemented"` so the app can be launched, navigated, and
demoed at any point in development regardless of backend completeness.
Placeholders MUST NOT be invisible (blank output, missing tab, hidden component) — the
user MUST always be able to see that a feature exists and is coming.
All exceptions and error conditions MUST be caught and surfaced to the user with a
descriptive message in the Gradio UI. Silent failure — where an exception is swallowed,
logged only to the console, or produces a blank/unchanged UI — is a defect.
Error messages displayed to the user MUST identify what failed and, where possible,
what the user can try next (e.g., "LLM unavailable — check that Ollama is running").
`except: pass`, bare `except Exception`, and any catch-and-discard pattern MUST NOT
appear in UI-facing code paths.

**Rationale**: The team demos and tests constantly. A stub that says "coming soon" lets
a demo proceed; a crash or blank panel kills it. Explicit, visible errors also shorten
the debugging loop — a console-only traceback is invisible during a live session and
silently misleads stakeholders into thinking something works when it does not.

## Technology Stack Constraints

The following technology choices are project-wide defaults. Deviations MUST be recorded
as an Architecture Decision Record (ADR) under `docs/adr/` before implementation begins.

- **Language**: Python 3.11+ is the primary language. Rust or C++ extensions are
  permitted only for performance-critical paths (e.g., heavy rules math, image pipelines)
  and MUST be optional to build (Python fallback or stub required).
- **UI**: Gradio is the exclusive UI framework. No separate backend API layer (FastAPI
  or otherwise) MUST be introduced; doing so reintroduces session and state management
  complexity that Principle VI explicitly defers. All UI state MUST be managed within
  Gradio's native session and state model.
- **Authentication**: Mock authentication backed by the existing SQLite database is
  mandatory. The `User`, `Player`, and `GameStar` SQLAlchemy models MUST be used as-is
  for identity and session context. No JWT, OAuth, or session-token infrastructure SHOULD
  be added until product-market fit is confirmed (see Principle VI).
- **Image generation**: HuggingFace Inference API (free tier) is the current MVP provider,
  configured via environment variable. ComfyUI / Stable Diffusion (local) is the planned
  future provider and MUST be wired through the same `packages/imagegen/` abstraction.
- **Dependency management**: `uv` (recommended). Workspace config lives in
  `pyproject.toml` at the repository root.
- **Containers**: Docker + Docker Compose (`deploy/compose/`). Both local and cloud
  compose files MUST be maintained.
- **Testing**: `pytest` for unit and integration tests; `/harness` for agent/tool evals.
  `ruff` for linting and `pyright` for type-checking on every CI push.
- **IP compliance**: StoryWeaver MUST NOT redistribute copyrighted rulebook text, art,
  or proprietary game content. Only distilled mechanics, tables, and structured facts
  derived from the user's own rulebooks may be bundled. Project is released under the
  license in the `LICENSE` file at the repository root.

## Development Workflow

1. **Spec first**: Open or update a spec in `/specs` describing the change or feature.
2. **ADR for major decisions**: Any adoption of a new framework, infrastructure component,
   or architectural pattern MUST be preceded by an ADR in `docs/adr/`.
   (e.g., the agent framework choice — see ADR-005 — MUST be resolved before M2 begins.)
3. **Harness coverage**: Add or extend harness evals for any agent or tool behaviour
   introduced or changed.
4. **Implement — placeholder first**: Wire up a visible placeholder stub for every new UI
   surface before implementing real logic. The app MUST remain launchable and demo-able
   after every commit. All error paths MUST display a user-visible message in the Gradio
   UI — never log-only. Replace the placeholder with real logic incrementally; keep
   packages isolated throughout.
5. **Verify**: `pytest` passes; harness evals pass; `ruff` and `pyright` report no errors.
6. **README currency**: Update `README.md` to reflect the current implemented state of
   the project. This MUST cover: newly completed features, changed setup/usage
   instructions, removed or renamed commands, and known limitations introduced by this
   change. Do not describe functionality that is planned but not yet implemented.
7. **Milestone gate**: A milestone is complete only when all its acceptance criteria
   are satisfied (verified by harness or automated assertion) **and** `README.md`
   accurately reflects the milestone's delivered scope. Milestones are sequential
   unless the roadmap explicitly permits parallelism.

## Governance

This constitution supersedes all other development practices and informal conventions.
When a practice not covered here is needed, amend the constitution rather than working
around it silently.

**Amendment procedure**:
1. Describe the proposed change and its motivation.
2. Determine the semver bump (MAJOR: breaking governance change; MINOR: new principle
   or material expansion; PATCH: clarification or wording fix).
3. Update `constitution.md`, increment the version, and set `Last Amended` to today.
4. Review `.specify/templates/` for any dependent templates that reference the changed
   principle and update them accordingly.
5. Record the change in the Sync Impact Report comment at the top of this file.

**Compliance**: All PRs and design reviews MUST verify compliance with the applicable
principles above. Non-compliance requires either a spec amendment or a constitution
amendment — not a quiet exception.

Runtime development guidance lives in `README.md` and the `/specs` directory.

**Version**: 1.4.0 | **Ratified**: 2026-06-18 | **Last Amended**: 2026-06-22
