# ADR-006: FastAPI as Minimal ASGI Routing Adapter

**Date**: 2026-06-19
**Status**: Accepted
**Deciders**: StoryWeaver project (portfolio)

---

## Context

Adding persistent GM authentication (feature 002-auth-admin-ui) requires serving two
independent Gradio `Blocks` apps from the same process:

1. **Main app** (`/`) — the full StoryWeaver interface, protected by Gradio's built-in
   `auth=` callable. All campaign, character, and NPC views live here.
2. **Registration companion** (`/register`) — an unauthenticated sign-up form. Because
   Gradio's `auth=` parameter blocks the *entire* `Blocks` instance, there is no
   supported mechanism to exempt individual tabs or routes from authentication within a
   single `Blocks` app.

A single `demo.launch()` call can serve only one `Blocks` instance and cannot split
traffic between an authenticated and an unauthenticated app at different URL paths.
A solution is needed that serves both apps on a single port from a single process, with
a shared startup lifecycle (database initialisation, WAL mode).

## Decision

**Use FastAPI as a minimal ASGI routing host.**

A `FastAPI` app is created in `apps/web/main.py` and both Gradio sub-apps are mounted
using `gr.mount_gradio_app`:

```python
gr.mount_gradio_app(fastapi_app, main_blocks,         path="/")
gr.mount_gradio_app(fastapi_app, registration_blocks, path="/register")
```

FastAPI's `lifespan` context manager runs the shared startup logic (database
initialisation, WAL pragma). The `fastapi_app` is exposed as the `app` symbol for
Uvicorn:

```
uvicorn apps.web.main:app --port 7860
```

**Scope constraint (non-negotiable)**: FastAPI is used **only** as an ASGI routing
adapter. It defines **no REST endpoints, no dependency-injection graph, no serialisation
layer, and no middleware** beyond what Gradio requires. All business logic remains in
Gradio event handlers. This constraint is documented here and must be re-evaluated
before any REST endpoint is added (which would require a separate ADR).

## Rationale

| Option | Verdict | Reason |
|--------|---------|--------|
| Single `demo.launch(auth=...)` | ✗ Rejected | Can serve only one `Blocks` instance; no mechanism to exclude individual routes from `auth=` |
| Two separate ports (7860 + 7861) | ✗ Rejected | Breaks the single-container Docker assumption; players and GMs get different URLs; no shared startup lifecycle |
| Two separate `demo.launch()` processes | ✗ Rejected | Doubles infrastructure; no shared DB connection context; defeats single-port Docker compose setup |
| Registration tab inside main `Blocks` | ✗ Rejected | Gradio `auth=` blocks the entire `Blocks` instance with no supported per-tab exception |
| FastAPI as ASGI routing host | ✓ Accepted | Single process, single port, single container; `gr.mount_gradio_app` is the Gradio-documented pattern; adds only routing glue — no business logic |

`gr.mount_gradio_app` is the pattern Gradio's own documentation recommends for serving
multiple apps at different paths from a single server process. Using FastAPI here is
therefore the path of least resistance and aligns with Gradio's intended integration
model.

## Alternatives Considered

### WSGI dispatcher (Werkzeug `DispatcherMiddleware`)

Rejected. Gradio 4.x is an ASGI application; mounting it behind a WSGI dispatcher would
require an ASGI-to-WSGI bridge (e.g. `asgiref`), adding a non-obvious dependency and
an extra indirection layer. FastAPI is already ASGI-native.

### Starlette (without FastAPI)

Acceptable in principle — Starlette is FastAPI's underlying library and would be
slightly lighter. Rejected in favour of FastAPI because `gr.mount_gradio_app`'s
signature accepts a `FastAPI` instance in Gradio's documented examples. FastAPI is a
superset of Starlette and the overhead difference is negligible for a routing-only role.

### Custom ASGI application

Rejected. Writing a raw ASGI app to dispatch `/` vs `/register` is straightforward but
adds code the team must maintain. FastAPI handles this more readably and is already a
transitive dependency of Gradio in many environments.

## Consequences

- `apps/web/main.py` becomes the canonical entry point, replacing the
  `if __name__ == "__main__": demo.launch()` block in `app.py`.
- `fastapi` and `uvicorn` are added as explicit runtime dependencies of `apps/web`.
- The Docker compose `command:` is updated to `uvicorn apps.web.main:app --port 7860`.
- **Future REST API**: When a REST layer is introduced (planned for a future milestone),
  a new ADR must be written to extend FastAPI's role. The scope constraint above (no
  endpoints) must be explicitly lifted at that point.

## Compliance

- Constitution Principle III (Package Isolation): ✅ FastAPI is confined to
  `apps/web/main.py`; no other package imports or depends on it.
- Constitution Principle IV (Local-First): ✅ FastAPI + Uvicorn run entirely locally;
  no cloud dependency.
- Constitution § Technology Stack Constraints: ✅ This ADR satisfies the requirement
  to document any adoption of a new framework before implementation begins. FastAPI's
  role is explicitly bounded to ASGI routing.
