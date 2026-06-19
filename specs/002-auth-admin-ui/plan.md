# Implementation Plan: Authentication & Admin UI

**Branch**: `002-auth-admin-ui` | **Date**: 2026-06-19 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/002-auth-admin-ui/spec.md`

## Summary

Add persistent GM account authentication (open registration + login via Gradio's built-in `auth` callable) and a campaign admin UI (dashboard listing all GM campaigns, campaign detail with copyable join code). Introduces `users` and `players` tables, adds an `owner_id` FK to `campaigns`, enforces case-insensitive name uniqueness for campaigns (per user), characters (per campaign), and NPCs (per campaign), and changes character/NPC creation to upsert-on-name semantics. FastAPI is introduced minimally as an ASGI routing adapter only (not as a REST API) to serve both the authenticated main app and the unauthenticated registration companion at separate URL paths.

## Technical Context

**Language/Version**: Python 3.11+

**Primary Dependencies**:
- Gradio 4.0+ — UI framework and built-in auth (`auth=` parameter, `gr.Request` for user identity)
- SQLAlchemy 2.0+ async + aiosqlite — existing ORM and storage abstraction
- passlib[bcrypt] — password hashing and verification
- FastAPI + uvicorn — minimal ASGI routing adapter only; used exclusively to mount two Gradio sub-apps at `/` and `/register`; no REST endpoints introduced
- Alembic 1.13+ — schema migrations (already in dev deps)

**Storage**: SQLite via `aiosqlite` (default); PostgreSQL-compatible schema via existing `StorageBackend` abstraction; Alembic manages migrations.

**Testing**: pytest + pytest-asyncio (async handlers); ruff (linting); pyright strict (type checking).

**Target Platform**: Local server (desktop/tablet browser); Docker-composable single port.

**Project Type**: Gradio web application with SQLAlchemy ORM backend.

**Performance Goals**: Sub-second login validation (single indexed SQLite lookup); sub-second admin page loads.

**Constraints**:
- No external OAuth/SSO in this phase (FR-016 clarification)
- FastAPI scoped to ASGI routing only — no REST endpoints, no serialisation layer (ADR required)
- Gradio manages session lifecycle (cookie-based); no custom session token
- Per-player passwords are explicitly out of scope (spec Assumptions)
- Join code uniqueness is global across all campaigns (FR-018)

**Scale/Scope**: Small group (5–20 concurrent users per campaign); SQLite WAL handles this load.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Spec-Driven Development | ✅ PASS | Spec at `specs/002-auth-admin-ui/spec.md`. README update is a mandatory delivery gate. |
| II. Provider Abstraction | ✅ PASS | Auth callable is a factory-injected dependency. Password hashing isolated in `apps/web/services/auth.py`. No AI provider involved. |
| III. Package Isolation | ⚠️ JUSTIFIED | Auth service lives in `apps/web/services/` (not a new package) because it is tightly coupled to Gradio's auth mechanism and consumed only by `apps/web`. User/Player models extend `packages/core`. Storage operations extend `packages/storage`. No new package introduced — complexity is explicitly minimal and documented here. |
| IV. Local-First, Cloud-Optional | ✅ PASS | All auth is SQLite-backed; bcrypt runs locally; no cloud dependency at runtime. |
| V. Harness-Driven Agent Quality | ✅ PASS | Feature introduces no new AI agents. Upsert logic and auth service covered by pytest integration tests. Existing harness evals unaffected. |

**ADR Required (gate)**: FastAPI is introduced as a new direct dependency of `apps/web`. Even though it is used only as an ASGI routing adapter, the constitution (§ Technology Stack Constraints) requires an ADR in `docs/adr/` before implementation begins. This ADR must clarify scope (routing only, no REST API), justify the choice over alternatives, and document the migration path when a full FastAPI API is introduced in a future milestone.

**Post-Phase-1 re-check**: ✅ All principles still satisfied. Data model and contracts introduce no new packages, cloud dependencies, or agent changes.

## Project Structure

### Documentation (this feature)

```text
specs/002-auth-admin-ui/
├── plan.md              # This file
├── research.md          # Phase 0 — Gradio auth API, multi-path routing, password hashing
├── data-model.md        # Phase 1 — entity changes, migration strategy
├── quickstart.md        # Phase 1 — validation scenarios
├── contracts/
│   ├── auth-callable.md    # Gradio auth callable + request identity contract
│   ├── admin-ui.md         # Admin campaign dashboard + detail UI screens
│   └── registration-ui.md  # Registration companion interface contract
└── tasks.md             # Phase 2 output (/speckit-tasks — not created here)
```

### Source Code (repository root)

```text
packages/core/core/
├── models.py         # + User, Player; Campaign.owner_id FK; case-insensitive indexes
└── schemas.py        # + UserSchema, PlayerSchema, RegisterRequest, LoginResult

packages/storage/storage/
└── users.py          # NEW: user + player repository functions (async, typed)

apps/web/
├── main.py           # NEW: FastAPI ASGI entry-point; mounts main app + /register
├── app.py            # Modified: auth= callable, request-scoped user identity passed to handlers
├── services/
│   └── auth.py       # NEW: hash_password, verify_password, validate_credentials, register_user
├── pages/
│   ├── landing.py    # Modified: player join flow wired to Player model
│   ├── registration.py  # NEW: unauthenticated Gradio registration companion
│   └── admin/
│       ├── __init__.py
│       └── campaigns.py # NEW: campaign dashboard + campaign detail UI
└── tests/
    ├── test_auth_service.py   # NEW: unit tests for auth.py
    ├── test_admin_campaigns.py # NEW: integration tests for campaign CRUD + uniqueness
    └── test_upsert.py         # NEW: character/NPC upsert integration tests

docs/adr/
└── ADR-006-fastapi-minimal-router.md  # NEW: ADR for FastAPI as ASGI routing adapter
```

**Structure Decision**: Single-project extension of the existing Gradio monorepo. No new `packages/*` member is introduced. Auth service is co-located in `apps/web/services/` (Gradio-specific; not reusable by other packages). Model and schema changes extend existing `packages/core` files. Storage operations extend `packages/storage`. `apps/web/main.py` replaces the `if __name__ == "__main__"` block in `app.py` as the canonical entry point.

## Complexity Tracking

| Concern | Why Needed | Simpler Alternative Rejected Because |
|---------|-----------|-------------------------------------|
| FastAPI ASGI adapter | Gradio `auth=` blocks the entire main app; registration must be unauthenticated at a separate URL in the same process | Two separate ports (e.g., 7860 + 7861) breaks single-container Docker assumption and gives players two different URLs to manage. Two separate processes doubles infra and loses shared DB connection context. Running both from a single FastAPI ASGI host is the Gradio-recommended pattern and adds only routing glue — no business logic in FastAPI. |
