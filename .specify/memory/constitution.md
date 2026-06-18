<!--
## Sync Impact Report

**Version Change**: [unversioned template] → 1.0.0
**Type of Bump**: MINOR — initial population of all placeholders; no prior versioned state existed.

### Principles Defined (new)
- I. Spec-Driven Development (NON-NEGOTIABLE)
- II. Provider Abstraction
- III. Package Isolation
- IV. Local-First, Cloud-Optional
- V. Harness-Driven Agent Quality

### Sections Added
- Technology Stack Constraints (Section 2)
- Development Workflow & IP Compliance (Section 3)
- Governance

### Templates Reviewed
- `.specify/templates/plan-template.md` ✅ — Constitution Check gate references constitution generically; no change required.
- `.specify/templates/spec-template.md` ✅ — FR/acceptance-criteria pattern compatible with spec-driven principle; no change required.
- `.specify/templates/tasks-template.md` ✅ — Test-before-implement note aligns with Spec-Driven principle; no change required.
- `.specify/templates/commands/` ✅ — No command files found; nothing to update.

### Deferred TODOs
- TODO(LICENSE): Project license is TBD (README says "recommend MIT or Apache-2.0"). Governance references this for IP compliance.
- TODO(RATIFICATION_DATE): Using first-commit / README creation date (2026-06-18) as ratification date; adjust if the project predates this session.
-->

# StoryWeaver Constitution

## Core Principles

### I. Spec-Driven Development (NON-NEGOTIABLE)

Every feature MUST begin with a written spec in `/specs` before any code is written.
Specs define problem statement, behaviour, interfaces, and acceptance criteria.
When code and spec disagree, **the spec wins**; code is updated to match.
Implementation and review MUST trace back to a spec.
The `README.md` is the top-level source of truth for architecture and intent; it MUST be updated deliberately and kept consistent with `/specs`.

**Rationale**: Non-deterministic AI components make "just try it" development expensive to reverse.
Specs provide a stable contract that lets the team iterate on prompts and agents with
confidence, not guesswork.

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

Default operation MUST work entirely without cloud services:
local LLM (Ollama), local embeddings (nomic-embed-text via Ollama),
local vector store (ChromaDB), local DB (SQLite), local image generation (ComfyUI/SD).
Cloud providers are opt-in upgrades controlled via environment variables.
No code path may *require* a cloud service to function at runtime unless it is
explicitly gated behind a provider config that also has a local equivalent.

**Rationale**: Tabletop RPG sessions happen in varied environments (offline, low-bandwidth,
privacy-sensitive). Local-first ensures StoryWeaver is useful and private by default, with
cloud as an upgrade — not a dependency.

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

## Technology Stack Constraints

The following technology choices are project-wide defaults. Deviations MUST be recorded
as an Architecture Decision Record (ADR) under `docs/adr/` before implementation begins.

- **Language**: Python 3.11+ is the primary language. Rust or C++ extensions are
  permitted only for performance-critical paths (e.g., heavy rules math, image pipelines)
  and MUST be optional to build (Python fallback or stub required).
- **UI**: Gradio. FastAPI is optional and introduced only when a separate backend API
  is needed (M5+).
- **Dependency management**: `uv` (recommended). Workspace config lives in
  `pyproject.toml` at the repository root.
- **Containers**: Docker + Docker Compose (`deploy/compose/`). Both local and cloud
  compose files MUST be maintained.
- **Testing**: `pytest` for unit and integration tests; `/harness` for agent/tool evals.
  `ruff` for linting and `pyright` for type-checking on every CI push.
- **IP compliance**: StoryWeaver MUST NOT redistribute copyrighted rulebook text, art,
  or proprietary game content. Only distilled mechanics, tables, and structured facts
  derived from the user's own rulebooks may be bundled.
  TODO(LICENSE): A project license (MIT or Apache-2.0 recommended) MUST be added as
  `LICENSE` before any public release.

## Development Workflow

1. **Spec first**: Open or update a spec in `/specs` describing the change or feature.
2. **ADR for major decisions**: Any adoption of a new framework, infrastructure component,
   or architectural pattern MUST be preceded by an ADR in `docs/adr/`.
   (e.g., the agent framework choice — see ADR-005 — MUST be resolved before M2 begins.)
3. **Harness coverage**: Add or extend harness evals for any agent or tool behaviour
   introduced or changed.
4. **Implement**: Write code against the spec. Keep packages isolated.
5. **Verify**: `pytest` passes; harness evals pass; `ruff` and `pyright` report no errors.
6. **Milestone gate**: A milestone is complete only when all its acceptance criteria
   are satisfied (verified by harness or automated assertion). Milestones are sequential
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

**Version**: 1.0.0 | **Ratified**: 2026-06-18 | **Last Amended**: 2026-06-18