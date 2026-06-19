# Research: Auth & Admin Reboot

## Decision: Pure Gradio Launch
- Decision: Use `apps/web/app.py` with `gr.Blocks().launch()` as the standard app entrypoint.
- Rationale: The feature spec explicitly requires a pure Gradio app launch with no FastAPI wrapper or uvicorn-only runtime for standard usage.
- Alternatives considered: Keep the existing `apps/web/main.py` FastAPI wrapper and launch with `uvicorn main:app`; rejected because it violates the new auth/admin user experience and the project constitution's Gradio-only UI constraint.

## Decision: Single Auth Screen with Tabs
- Decision: Keep one auth surface containing both "Sign In" and "Create Account" tabs and surface all errors inside the Gradio UI.
- Rationale: This minimizes friction, matches the feature spec's single-screen auth requirement, and eliminates a separate registration page.
- Alternatives considered: split login and registration into separate pages or routes; rejected because the spec requires a unified auth experience.

## Decision: Player Join Uses Join Code + Player Name Only
- Decision: Remove campaign name from the player join flow and instead use the globally unique campaign join code plus player name.
- Rationale: The spec emphasizes join code uniqueness and a simpler two-field join flow for players.
- Alternatives considered: retain campaign name as part of the join form; rejected because it increases friction and duplicates an identifier already provided by the join code.

## Decision: SHA-256 Password Hashing (replaces bcrypt)
- Decision: Store `hashlib.sha256(password.encode()).hexdigest()` in the existing `hashed_password` column; remove bcrypt dependency entirely.
- Rationale: The project constitution (Principle VI) permits a simplified auth approach pre-PMF. SHA-256 via stdlib `hashlib` requires no external package, no threading workaround (bcrypt's blocking call was causing the current breakage), and keeps the `hashed_password` column semantically correct. Explicitly chosen by the product owner during clarification.
- Alternatives considered: retain bcrypt with a threading fix; rejected because the threading complexity was the root cause of the current breakage and adds no user-facing value at this stage. Plain-text; rejected as too risky even for a local app.

## Decision: Keep Existing SQLite/Auth Models
- Decision: Retain the existing `User`, `Campaign`, `Player`, `Character`, `NPC`, `DigitalTwin`, `StoryEvent`, and `SessionPlan` models in `packages/core/core/models.py`.
- Rationale: The spec and constitution require mock auth backed by SQLite and reuse of existing models for compatibility.
- Alternatives considered: introduce a new auth schema or external session store; rejected because it delays the demo-ready auth/admin reboot and violates Principle VI.

## Decision: Visible AI Degradation
- Decision: Use the existing `CampaignSession.ai_available` flag and preserve visible placeholders when Ollama or ComfyUI are unavailable.
- Rationale: The spec mandates that AI-dependent tabs must show clear "unavailable" states rather than blank screens or crashes.
- Alternatives considered: hide AI-dependent controls until services are healthy; rejected because the feature explicitly requires visible placeholders and explicit failure messaging.
