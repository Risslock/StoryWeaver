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

## Decision: Auth Required for All Users Including Players
- Decision: All users — GMs and players — must create an account before accessing any campaign feature. Anonymous join (join code + player name without an account) is removed.
- Rationale: Requiring accounts gives every player a persistent, recoverable identity across sessions without relying on them correctly remembering a player name. It also removes the edge case where two anonymous users share the same player name and therefore the same Player record.
- Alternatives considered: keep anonymous join for players (join code + player name only); rejected because account-based identity eliminates the shared-record ambiguity and enables future player-owned persistence without architectural change.

## Decision: Post-Login Hub Screen
- Decision: After authentication, display a hub screen with two distinct navigation actions: "My Campaigns (GM)" and "Join a Campaign (Player)". Any account can access either path.
- Rationale: The hub makes the two usage modes (owning vs. joining campaigns) discoverable without committing the user to a role at registration. Any user may be both a GM and a player.
- Alternatives considered: role selection at account creation; rejected because it adds friction and prevents a single user from playing both roles. Showing GM campaign list by default with a secondary "join" button; rejected because it implicitly prioritizes GM usage, whereas the spec treats both paths as equal entry points.

## Decision: Module Consolidation — Delete landing.py and admin/campaigns.py
- Decision: Delete `pages/landing.py` and `pages/admin/campaigns.py`. Move player join logic to `pages/player/join.py`. Move GM campaign management logic to `pages/gm/campaigns.py`. Hub routing lives inline in `app.py`.
- Rationale: The user explicitly requested this consolidation (2026-06-20 clarification). The two modules had no distinct domain responsibility separable from their respective dashboard contexts — campaigns belong under `gm/` and player join belongs under `player/`. A hub that knows where to route belongs in the app factory.
- Alternatives considered: rename files in place (landing.py → player_join.py, admin/campaigns.py → gm_campaigns.py); rejected because the old paths leave stale imports and do not communicate the new structure clearly.

## Decision: Player Identity via User Account (player_name = username)
- Decision: `Player.player_name` is populated automatically from `User.username` at campaign join time. No separate player name input field is shown. `Player` gains a `user_id` FK column; uniqueness changes from `(player_name, campaign_id)` to `(user_id, campaign_id)`.
- Rationale: With mandatory accounts, `User.username` is already the user's chosen display identity. Adding a second "player name" field is redundant and adds friction. Per-campaign identity is determined by the authenticated user, eliminating the ambiguity of anonymous name collisions.
- Alternatives considered: keep a separate player name field that defaults to username but can be overridden per campaign; rejected because no explicit use case for per-campaign display name override was identified, and the additional complexity is not justified at this stage.
- Migration: `0004_player_user_link` — adds `user_id UUID REFERENCES users(id)`, drops `ix_players_campaign_player_name_lower`, adds `ix_players_campaign_user` unique on `(campaign_id, user_id)`.

## Decision: Visible AI Degradation
- Decision: Use the existing `CampaignSession.ai_available` flag and preserve visible placeholders when Ollama or ComfyUI are unavailable.
- Rationale: The spec mandates that AI-dependent tabs must show clear "unavailable" states rather than blank screens or crashes.
- Alternatives considered: hide AI-dependent controls until services are healthy; rejected because the feature explicitly requires visible placeholders and explicit failure messaging.
