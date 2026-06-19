# Research: Authentication & Admin UI

**Feature**: 002-auth-admin-ui | **Date**: 2026-06-19

This document resolves all NEEDS CLARIFICATION items identified during Technical Context analysis.

---

## 1. Gradio Built-in Auth API

### Decision
Use `gr.mount_gradio_app` with a FastAPI ASGI host. The main Gradio `Blocks` app receives `auth=_validate_credentials` where `_validate_credentials(username, password) -> bool` performs a synchronous bcrypt check against the `users` table. Inside event handlers, authenticated user identity is accessed via `request: gr.Request` (Gradio injects this automatically when the handler declares it as a parameter).

### How it Works (Gradio 4.x)
- `demo.launch(auth=callable)` — Gradio shows a login screen before rendering the app. The callable receives `(username: str, password: str)` and returns `bool`.
- `demo.launch(auth=callable, auth_message="...")` — optional custom message on login screen.
- Inside any event handler: `def my_handler(..., request: gr.Request)` — Gradio injects `request` automatically. `request.username` returns the authenticated username string.
- Cookie-based session: Gradio sets an HTTP-only session cookie after successful auth. Cookie lifetime is Gradio-managed (default: browser session).
- The `auth=` callable is called on every login form submit, not on every request. After the cookie is established, subsequent requests are validated by Gradio's internal cookie check; the callable is not invoked again until the next login.

### Rationale
Matches spec clarification (FR-002, Assumptions) — Gradio built-in auth is the chosen mechanism for this phase. FastAPI is deferred from providing a REST auth layer, but its presence as an ASGI host is independent of that concern.

### Alternatives Considered
- **FastAPI JWT + custom Gradio login page**: Fully custom auth flow. Rejected — more complexity, deferred to a future milestone.
- **`demo.launch()` with built-in auth, single process**: Would only work for a single Gradio app (no separate `/register`). Rejected because registration must be unauthenticated (FR-016).

---

## 2. Multi-Path Routing: Main App + Registration Companion

### Decision
Use a minimal FastAPI application as the ASGI host, mounting two Gradio sub-apps:
- `gr.mount_gradio_app(fastapi_app, main_blocks, path="/")` — authenticated main app
- `gr.mount_gradio_app(fastapi_app, registration_blocks, path="/register")` — unauthenticated registration

The FastAPI app defines **no REST endpoints** — it is purely an ASGI routing adapter.

Entry point: `apps/web/main.py` creates the FastAPI app and mounts both Gradio sub-apps. Startup logic (`initialize_db`, WAL verification) runs via FastAPI's `lifespan` context.

### Rationale
- Single process, single port, single Docker container.
- `gr.mount_gradio_app` is the Gradio-documented pattern for serving multiple apps at different paths.
- FastAPI is used only as a routing layer — no serialization, no dependency injection, no REST endpoints.

### Alternatives Considered
- **Two separate ports**: Rejected — breaks single-container assumption; players and GMs need different URLs.
- **Two separate `demo.launch()` processes**: Rejected — doubles infra; no shared startup lifecycle.
- **Registration tab inside main app**: Rejected — Gradio `auth=` blocks the entire `Blocks` instance; no Gradio mechanism exists to exclude individual tabs from auth.

---

## 3. Password Hashing Library

### Decision
`passlib[bcrypt]` version 1.7+ using the `bcrypt` scheme.

```python
from passlib.context import CryptContext
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)
```

Work factor: bcrypt default (12 rounds), acceptable for login latency on local hardware.

### Rationale
- `passlib` is the established Python standard for password hashing.
- `bcrypt` is battle-tested and resistant to GPU-based brute force.
- `CryptContext` handles scheme migration automatically (future-proof for argon2 upgrade).
- Runs entirely locally — no cloud dependency.

### Alternatives Considered
- **`bcrypt` directly**: Works but lacks scheme migration support.
- **`argon2-cffi`**: More modern, but requires a C extension; passlib wraps argon2 as well and we can migrate later via `deprecated="auto"`.
- **`hashlib` (PBKDF2)**: Simpler but inferior to bcrypt for password storage.

---

## 4. Case-Insensitive Unique Constraints (SQLAlchemy + SQLite)

### Decision
Use functional indexes on `func.lower(column)` for case-insensitive uniqueness. SQLAlchemy + SQLite support this natively.

**Campaign name unique per owner (case-insensitive)**:
```python
Index(
    "ix_campaigns_owner_name_lower",
    func.lower(Campaign.name), Campaign.owner_id,
    unique=True
)
```

**Character name unique per campaign (case-insensitive)**:
```python
Index(
    "ix_characters_campaign_name_lower",
    func.lower(Character.name), Character.campaign_id,
    unique=True
)
```

**NPC name unique per campaign (case-insensitive)**:
```python
Index(
    "ix_npcs_campaign_name_lower",
    func.lower(NPC.name), NPC.campaign_id,
    unique=True
)
```

**Player name unique per campaign (case-insensitive)**:
```python
Index(
    "ix_players_campaign_player_name_lower",
    func.lower(Player.player_name), Player.campaign_id,
    unique=True
)
```

These indexes enforce uniqueness at the DB layer and also accelerate case-insensitive lookups during upsert operations.

Service-layer upsert pattern (character example):
```python
result = await session.execute(
    select(Character).where(
        Character.campaign_id == campaign_id,
        func.lower(Character.name) == name.lower()
    )
)
existing = result.scalar_one_or_none()
if existing:
    # update fields
else:
    # insert new
```

### Rationale
Functional indexes are natively supported in SQLite and PostgreSQL. Storing a separate `name_normalized` column adds redundancy and migration risk. SQLAlchemy's `func.lower` in `Index` definitions is idiomatic and portable.

### Alternatives Considered
- **`COLLATE NOCASE` column**: SQLite-specific; not portable to PostgreSQL.
- **`name_normalized` computed column**: Redundant data, more complex ORM mapping.
- **Application-layer enforcement only**: Vulnerable to race conditions; DB constraint is the authoritative guard.

---

## 5. User Identity Propagation in Gradio Handlers

### Decision
All Gradio event handlers that require the authenticated user's identity declare `request: gr.Request` as a parameter. Gradio 4.x automatically injects the request object when the handler signature includes it.

```python
async def load_campaigns(request: gr.Request) -> list[list[str]]:
    username: str = request.username
    # ... query campaigns by owner username
```

For handlers that do not need the username, the parameter is omitted.

### Rationale
This is the official Gradio 4.x mechanism for accessing authenticated user identity within event handlers. No custom middleware or session management is required.

### Alternatives Considered
- **`gr.State` carrying username**: Would require passing it through every handler chain — fragile and redundant given `gr.Request` already provides it.
- **Module-level dict mapping session → username**: Not thread-safe and violates Gradio's per-tab isolation model.

---

## 6. Alembic Migration Strategy

### Decision
Generate a single Alembic migration script for this feature's schema changes:
1. Create `users` table
2. Create `players` table
3. Add `owner_id` column to `campaigns` (nullable initially for existing data, then backfill, then NOT NULL)
4. Add functional unique indexes on `characters.name`, `npcs.name`, `campaigns.name`
5. Remove or relax the `join_code` column length constraint (currently `String(8)`, change to `String(6)`)

**Backfill strategy** for existing campaigns without an owner: Create a default system user (`system@storyweaver.local`) during migration and assign all orphaned campaigns to it. This avoids a NOT NULL violation during migration while preserving existing data.

### Rationale
Alembic is already in dev dependencies. A single migration script keeps the schema change atomic and reversible (`downgrade()` drops the new columns/tables).

### Alternatives Considered
- **Drop and recreate DB**: Acceptable for development but not for any production or shared SQLite file with existing data. Rejected as default strategy.
- **Multiple migration scripts**: Over-engineered for a single feature; one script is simpler to review and roll back.