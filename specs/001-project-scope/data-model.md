# Data Model: StoryWeaver — Project Scope & Vision

**Branch**: `001-project-scope` | **Date**: 2026-06-18

All persisted entities are implemented as SQLAlchemy 2.x ORM models in `packages/core/models.py`. The local default is SQLite; cloud uses Postgres with the same model definitions. JSON fields use `sqlalchemy.JSON` (native for both backends). UUIDs are stored as `sqlalchemy.Uuid`.

---

## Entity Relationship Overview

```
Campaign ─────┬─── Character ──── DigitalTwin
              ├─── NPC ────────── DigitalTwin
              ├─── Session ────── StoryEvent
              └─── SessionPlan
```

A `CampaignSession` (transient Gradio state, not persisted) ties a browser session to a Campaign + role.

---

## Campaign

The shared container for a group's game.

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID PK | Generated at creation |
| `name` | str (255) | Campaign display name; required |
| `join_code` | str (8) UNIQUE INDEX | Alphanumeric; used by Players to join |
| `gm_display_name` | str (100) | Display name of the creator (GM role) |
| `game_system` | str (50) | Default: `"earthdawn_4e"` |
| `settings` | JSON | Extensibility (image style prefs, etc.); default `{}` |
| `created_at` | datetime (UTC) | Set at insert |

**Validation rules**: `name`, `join_code`, `gm_display_name` required. `join_code` must be unique across all campaigns.

---

## Character

A Player-owned entity within a Campaign. A Player may own multiple Characters in the same Campaign (FR-001).

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID PK | |
| `campaign_id` | UUID FK → Campaign | ON DELETE CASCADE |
| `player_display_name` | str (100) | Owner's display name; matches the joining session |
| `name` | str (255) | Character name; required |
| `race` | str (100) | Earthdawn race; required |
| `discipline` | str (100) | Earthdawn Discipline; required |
| `circle` | int | Current Circle 0–15; default 0 |
| `attributes` | JSON | `{dex, str, tou, per, wil, cha}` — step values as integers |
| `derived_stats` | JSON | `{initiative, physical_defense, spell_defense, social_defense, ...}` — computed from attributes |
| `talents` | JSON | List of `{name, circle, rank, action, strain}` |
| `skills` | JSON | List of `{name, rank}` |
| `equipment` | JSON | List of `{name, type, notes}` |
| `background` | str TEXT | Backstory; required for twin grounding |
| `personality` | str TEXT | Personality traits and quirks; required for twin |
| `goals` | str TEXT | Goals and motivations |
| `relationships` | JSON | List of `{name, nature, notes}` |
| `physical_description` | str TEXT | Used for portrait image generation |
| `portrait_url` | str | Null until portrait generated; overwritten on regeneration |
| `created_at` | datetime (UTC) | |
| `updated_at` | datetime (UTC) | Updated on any field change |

**Validation rules**: `name`, `race`, `discipline`, `background`, `personality` required. `circle` must be 1–15. Multiple Characters per `(campaign_id, player_display_name)` pair are allowed.

**State transitions**: Character sheet may be updated at any time in v1 (no locked workflow states). Portrait generation is idempotent; new `portrait_url` overwrites the old value.

---

## NPC

A GM-owned entity within a Campaign.

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID PK | |
| `campaign_id` | UUID FK → Campaign | ON DELETE CASCADE |
| `name` | str (255) | Required |
| `role` | str (100) | E.g., "merchant", "villain", "ally" |
| `race` | str (100) | Optional; may be unknown to Players |
| `is_visible_to_players` | bool | Default `False`; GM toggles to reveal (FR-007) |
| `discipline` | str (100) | Earthdawn Discipline; could be none |
| `circle` | int | Current Circle 0–15; default 0 |
| `attributes` | JSON | `{dex, str, tou, per, wil, cha}` — step values as integers |
| `derived_stats` | JSON | `{initiative, physical_defense, spell_defense, social_defense, ...}` — computed from attributes |
| `talents` | JSON | List of `{name, circle, rank, action, strain}` |
| `skills` | JSON | List of `{name, rank}` |
| `personality` | str TEXT | Personality traits and quirks; required for twin |
| `background` | str TEXT | Backstory; required for twin grounding |
| `physical_description` | str TEXT | For portrait generation |
| `portrait_url` | str | Null until generated |
| `gm_notes` | str TEXT | Private GM-only notes; MUST NEVER appear in Player-role responses |
| `created_at` | datetime (UTC) | |
| `updated_at` | datetime (UTC) | |

**Validation rules**: `name` required. `gm_notes` is access-controlled at the service layer — filtered out of all Player-role query results.

**State transitions**: `is_visible_to_players` toggled by GM only (per-NPC toggle, FR-007). No other workflow states in v1.

---

## DigitalTwin

A persistent agent record tied to one Character or one NPC.

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID PK | |
| `entity_type` | str enum `{"character", "npc"}` | Discriminator |
| `entity_id` | UUID | References Character.id or NPC.id (polymorphic; enforced at service layer) |
| `campaign_id` | UUID FK → Campaign | Denormalized for efficient campaign-scoped queries |
| `conversation_history` | JSON | List of `{role: "user"/"assistant", content: str, timestamp: str}` |
| `last_active` | datetime (UTC) | Updated on each twin interaction |
| `created_at` | datetime (UTC) | |

**Validation rules**: One DigitalTwin per entity (`entity_type`, `entity_id`) pair — enforced by unique constraint.

**State transitions**: `conversation_history` is appended on each twin interaction. Oldest entries are pruned (service layer) when the list exceeds a configurable max-turns threshold, to manage LLM context window size.

---

## Session

A discrete play session within a Campaign.

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID PK | |
| `campaign_id` | UUID FK → Campaign | ON DELETE CASCADE |
| `session_number` | int | Sequential per Campaign; unique within Campaign |
| `title` | str (255) | E.g., "Session 3: The Ork Warband"; required |
| `date_played` | date | Real-world date; required |
| `summary` | str TEXT | GM-authored or LLM-generated recap; nullable |
| `created_at` | datetime (UTC) | |

**Validation rules**: `(campaign_id, session_number)` unique constraint. `title` and `date_played` required.

---

## StoryEvent

An individual event recorded in the campaign timeline.

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID PK | |
| `campaign_id` | UUID FK → Campaign | ON DELETE CASCADE |
| `session_id` | UUID FK → Session | Nullable (some events are campaign-wide, between sessions) |
| `event_type` | str enum | `{dialogue, decision, discovery, combat_outcome, npc_state_change, world_change, plot_thread_opened, plot_thread_closed}` |
| `content` | str TEXT | Event description; required |
| `participants` | JSON | List of `{entity_type: "character"/"npc", entity_id: UUID, name: str}` |
| `is_public` | bool | `True` = all roles; `False` = GM-only (FR-007) |
| `event_order` | int | Ordering within the session for chronological display |
| `created_at` | datetime (UTC) | |

**Validation rules**: `content` required. `is_public=False` events MUST be filtered from all Player-role query responses — enforced at the service layer, not the ORM layer.

**Index**: Composite index on `(campaign_id, session_id, event_order)` to support the story history load-time requirement (SC-008).

---

## SessionPlan

A GM-authored plan for an upcoming or current session (M4 — GM planning tool, FR-009).

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID PK | |
| `campaign_id` | UUID FK → Campaign | ON DELETE CASCADE |
| `session_id` | UUID FK → Session | Nullable (plan may exist before the Session record is created) |
| `content` | str TEXT | Markdown plan content; required |
| `annotations` | JSON | List of `{position: int, note: str, created_at: str}` — GM inline annotations |
| `created_at` | datetime (UTC) | |
| `updated_at` | datetime (UTC) | |

**Validation rules**: At most one SessionPlan per Campaign per Session (enforced by unique constraint on `(campaign_id, session_id)` when `session_id` is not null). `content` required.

---

## Transient: CampaignSession (Gradio State — not persisted)

Held in `gr.State()` for the lifetime of a browser session. Never written to the database.

| Field | Type | Notes |
|-------|------|-------|
| `campaign_id` | UUID | Resolved from join code at login |
| `display_name` | str | User-chosen display name |
| `role` | `Literal["player", "gm"]` | Resolved from `Campaign.gm_display_name` at join |
| `ai_available` | bool | Checked at join time; drives the degraded-mode banner |