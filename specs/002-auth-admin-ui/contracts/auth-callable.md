# Contract: Gradio Auth Callable & User Identity

**Feature**: 002-auth-admin-ui | **Date**: 2026-06-19

> **Implementation Decision (2026-06-19)**: This contract was written assuming Gradio's built-in `auth=` callable. The final implementation does **not** use `auth=`. Authentication is handled by `pages/auth.py` embedded inside the single Gradio app. `user_state: gr.State(UserInfo | None)` replaces `gr.Request.username` as the identity source. `make_auth_callable` is implemented in `services/auth.py` but is not called at runtime — retained for future use. The sections below remain as reference for the original design intent; see plan.md "Implementation Decision — Auth Mechanism Change" for the rationale.

---

## Overview

Two distinct interface contracts govern authentication in this feature:

1. **Auth Callable** — the function Gradio calls to validate login credentials.
2. **Request Identity** — the mechanism for accessing the authenticated username inside event handlers.

---

## 1. Auth Callable Contract

### Signature

```python
def validate_credentials(username: str, password: str) -> bool:
    """Return True if username/password match a stored bcrypt hash; False otherwise."""
```

### Contract Rules

| Rule | Value |
|------|-------|
| Input `username` | Raw string from login form; may be username OR email |
| Input `password` | Plaintext; must NOT be stored or logged |
| Return type | `bool` — `True` = authenticated, `False` = rejected |
| Async | Must be synchronous (Gradio 4.x `auth=` does not support async callables) |
| Side effects | NONE — must not modify DB, must not update session state |
| Timing | Must complete in < 500 ms (bcrypt at default rounds ≈ 100–200 ms) |
| Error handling | Any exception must be caught internally and return `False`; never raise |

### Lookup Logic

1. Attempt lookup by `username` field (case-insensitive).
2. If not found, attempt lookup by `email` field (case-insensitive).
3. If still not found, return `False` (timing-safe: always call `verify_password` with a dummy hash to prevent username enumeration via timing).
4. If user found but `is_active = False`, return `False`.
5. Return `verify_password(password, user.hashed_password)`.

### Integration Point

```python
# apps/web/main.py
from services.auth import validate_credentials

main_app = create_main_app()
main_app.auth = validate_credentials          # injected via Gradio Blocks param
main_app.auth_message = "Sign in to StoryWeaver"
```

---

## 2. Request Identity Contract

### Mechanism

Gradio 4.x injects a `gr.Request` object into any event handler that declares it as a parameter. The handler must not call `request.username` before auth is confirmed (Gradio guarantees `auth=` is validated before any handler runs, so `request.username` is always populated in authenticated handlers).

### Handler Signature Pattern

```python
async def load_my_campaigns(request: gr.Request) -> list[list[str]]:
    username: str = request.username  # always non-empty in authenticated handlers
    # ... use username to scope DB queries
```

### Contract Rules

| Rule | Value |
|------|-------|
| `request.username` | The username string returned by the successful `validate_credentials` call |
| Guaranteed non-null | Yes — Gradio only routes to handlers after successful auth |
| Scope | Per-request (not stored in `gr.State`; re-derived from cookie each request) |
| Handlers that don't need it | Omit the `request` parameter entirely |

---

## 3. Auth Callable Factory

The callable must be constructed after the DB backend is initialized (startup). The factory pattern avoids a circular import and allows the backend to be injected:

```python
# apps/web/services/auth.py
from storage.interface import StorageBackend

def make_auth_callable(backend: StorageBackend):
    def validate_credentials(username: str, password: str) -> bool:
        import asyncio
        return asyncio.run(_async_validate(backend, username, password))
    return validate_credentials
```

The factory is called once during app startup and the result is passed to `gr.Blocks(auth=...)`.

---

## 4. Session Lifecycle

| Event | Behaviour |
|-------|-----------|
| Login form submit | Gradio calls `validate_credentials`; on `True`, sets HTTP-only session cookie |
| Subsequent requests | Gradio validates cookie internally; `validate_credentials` is NOT re-called |
| Logout | Gradio clears the cookie; user is redirected to login screen |
| Session expiry | Gradio default: browser session (cookie expires when browser closes) |
| Idle timeout | Out of scope for this phase (spec edge cases) |