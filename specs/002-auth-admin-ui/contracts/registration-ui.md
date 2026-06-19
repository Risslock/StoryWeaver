# Contract: Registration Companion Interface

**Feature**: 002-auth-admin-ui | **Date**: 2026-06-19

> **Implementation Decision (2026-06-19)**: The registration form is **not** served at `/register` in the current implementation. Instead it is embedded as a **Create Account** tab inside `pages/auth.py`, which renders within the main app's `auth_col` when `user_state` is `None`. The standalone `create_registration_app()` factory in `pages/registration.py` was implemented per this contract but is not mounted in `main.py`. It is kept as a future opt-in standalone endpoint. The behaviour (validation, error messages, `register_user` call) is identical. See plan.md "Implementation Decision — Auth Mechanism Change".

This contract defines the unauthenticated registration Gradio app served at `/register` (original design intent).

---

## Overview

The main Gradio app (`/`) uses `auth=` which blocks all access until credentials are validated. To allow new users to sign up, a separate unauthenticated Gradio `Blocks` instance is mounted at `/register`. This app has no `auth=` parameter and is accessible without login. It exposes only the registration form; it has no access to any campaign or character data.

---

## Screen: Registration Form

**URL path**: `/register`

**Access**: Unauthenticated (no `auth=` on this Gradio instance).

### Layout

```
╔══════════════════════════════════════════════╗
║  StoryWeaver — Create Account                ║
╠══════════════════════════════════════════════╣
║                                              ║
║  Username:  [________________________]       ║
║  Email:     [________________________]       ║
║  Password:  [________________________]       ║
║  Confirm:   [________________________]       ║
║                                              ║
║  [Create Account]                            ║
║                                              ║
║  Already have an account? → /               ║
║                                              ║
╚══════════════════════════════════════════════╝
```

### Components

| Component | Gradio Type | Notes |
|-----------|-------------|-------|
| Username input | `gr.Textbox(label="Username", max_lines=1)` | 3–50 chars, alphanumeric + underscore |
| Email input | `gr.Textbox(label="Email", type="email")` | Must be valid email format |
| Password input | `gr.Textbox(label="Password", type="password")` | Min 8 chars |
| Confirm password | `gr.Textbox(label="Confirm Password", type="password")` | Must match password |
| Submit button | `gr.Button("Create Account", variant="primary")` | |
| Status message | `gr.Markdown("")` | Shows success or error after submit |
| Login link | `gr.Markdown("Already have an account? [Sign in](/).")` | Static text |

---

## Registration Interaction Contract

### Input

```python
@dataclass
class RegisterRequest:
    username: str
    email: str
    password: str
    confirm_password: str
```

### Validation (client-side, enforced in handler before DB write)

| Rule | Error Message |
|------|---------------|
| `username` non-empty, 3–50 chars | "Username must be 3–50 characters." |
| `username` matches `^[a-zA-Z0-9_]+$` | "Username may only contain letters, numbers, and underscores." |
| `email` valid format | "Enter a valid email address." |
| `password` min 8 chars | "Password must be at least 8 characters." |
| `confirm_password == password` | "Passwords do not match." |

### DB Operation

```python
async def register_user(backend, username, email, password) -> tuple[bool, str]:
    """
    Returns (True, "") on success.
    Returns (False, error_message) on failure.
    """
    # 1. Normalize: username.strip(), email.lower().strip()
    # 2. Check username uniqueness (case-insensitive)
    # 3. Check email uniqueness (case-insensitive)
    # 4. Hash password with passlib bcrypt
    # 5. INSERT into users
```

### Output (status message shown in `gr.Markdown`)

| Outcome | Message |
|---------|---------|
| Success | "✓ Account created! [Sign in here](/) to get started." |
| Username taken | "Username '{username}' is already registered. Choose a different one." |
| Email taken | "An account with that email address already exists." |
| Unexpected error | "Something went wrong. Please try again." |

---

## Security Rules

| Rule | Implementation |
|------|----------------|
| Password never stored plaintext | Always bcrypt-hashed before DB write |
| Email normalized to lowercase | `.lower().strip()` before storage and lookup |
| Username preserved as entered | Stored as-is; lookups use `lower()` comparison |
| No enumeration via timing | Username and email checks run in constant time (always verify even on miss) |
| No CSRF protection required | Gradio handles form submission via WebSocket/internal protocol; not a plain HTML POST |
| Rate limiting | Out of scope for this phase |

---

## FastAPI Mount Point

```python
# apps/web/main.py
from pages.registration import create_registration_app

registration_blocks = create_registration_app()
gr.mount_gradio_app(fastapi_app, registration_blocks, path="/register")
```

The registration app is mounted without `auth=`. It shares the same FastAPI instance (and therefore the same DB backend) as the main app.