# Data Model: Authentication & Admin UI

**Feature**: 002-auth-admin-ui | **Date**: 2026-06-19

---

## New Entities

### User

Represents an authenticated GM account. Created at registration; owns zero or more campaigns.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | UUID | PK, default uuid4 | |
| `username` | String(100) | NOT NULL, UNIQUE | Display name and login identifier |
| `email` | String(255) | NOT NULL, UNIQUE | Contact address; also accepted at login |
| `hashed_password` | String(255) | NOT NULL | bcrypt hash via passlib |
| `is_active` | Boolean | NOT NULL, default True | Soft-disable without deletion |
| `created_at` | DateTime(tz=True) | NOT NULL, default now | |

**Indexes**: `ix_users_username` (unique), `ix_users_email` (unique)

**Validation Rules**:
- `username`: 3–50 characters, alphanumeric + underscores only
- `email`: valid email format, lowercased before storage
- `hashed_password`: never stored as plaintext; always bcrypt-hashed before insert

**State Transitions**: `is_active` defaults to `True`; set to `False` to revoke access without deleting the record. Password reset is out of scope for this phase.

---

### Player

A named identity within a specific campaign. Created the first time a person joins with a new player name; linked to a Character once one is created.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | UUID | PK, default uuid4 | |
| `campaign_id` | UUID | FK → campaigns.id CASCADE DELETE | |
| `player_name` | String(100) | NOT NULL | Display name used to rejoin |
| `character_id` | UUID | FK → characters.id SET NULL, nullable | Null until character created in-session |
| `created_at` | DateTime(tz=True) | NOT NULL, default now | |

**Indexes**: `ix_players_campaign_player_name_lower` — functional unique index on `(func.lower(player_name), campaign_id)`

**Validation Rules**:
- `player_name`: 1–100 characters, stripped of leading/trailing whitespace before lookup
- Uniqueness is case-insensitive within a campaign: "Alice" and "alice" resolve to the same Player
- Two players sharing the same name in the same campaign are treated as the same identity (per spec Assumptions — the GM ensures players use distinct names)

**Relationships**:
- Campaign 1 --- * Player (cascade delete-orphan)
- Player 0..1 --- 1 Character (nullable; Player exists before Character is created)

---

## Modified Entities

### Campaign (modified)

Adds `owner_id` FK to the authenticated GM user. Enforces case-insensitive name uniqueness per owner. Changes join code from 8-char to 6-char uppercase alphanumeric.

**New / changed columns**:

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `owner_id` | UUID | FK → users.id RESTRICT, NOT NULL (after migration) | Links campaign to its GM |
| `join_code` | String(6) | NOT NULL, UNIQUE | Changed from String(8); now 6-char UPPERCASE alphanumeric (e.g., `A3KP72`) |

**New indexes**:
- `ix_campaigns_owner_name_lower` — functional unique index on `(func.lower(name), owner_id)` — enforces case-insensitive campaign name uniqueness per user

**Retained columns**: `gm_display_name` is kept for backwards-compatible player join flow (player sees the GM's display name, not their account username). May be deprecated in a future phase.

**New relationship**:
- User 1 --- * Campaign (via `owner_id`)
- Campaign 1 --- * Player (new; cascade delete-orphan)

**Validation Rules**:
- Campaign name: unique case-insensitively within the same `owner_id` (FR-010, FR-011)
- Campaign name duplicate: reject with error, do NOT silently upsert (campaigns differ from characters/NPCs in this regard)
- Join code: auto-generated at creation as 6-char uppercase alphanumeric (`secrets.token_urlsafe` filtered to `[A-Z0-9]`, sliced to 6 chars); retry until globally unique

---

### Character (modified)

Adds a case-insensitive unique constraint per campaign and formalizes upsert semantics.

**New indexes**:
- `ix_characters_campaign_name_lower` — functional unique index on `(func.lower(name), campaign_id)` — prevents duplicate character names at DB layer

**No new columns** in this phase. The existing `player_display_name` field continues to record which player the character belongs to.

**Upsert Semantics** (service layer, FR-012):
1. Query: `SELECT * FROM characters WHERE campaign_id = ? AND lower(name) = lower(?)`
2. If found: `UPDATE` all provided fields (preserves `id`, `created_at`; updates `updated_at`)
3. If not found: `INSERT` new record

**Validation Rules**:
- Name uniqueness: case-insensitive per campaign
- "kira" and "KIRA" in the same campaign → same record (update, not insert)

---

### NPC (modified)

Adds a case-insensitive unique constraint per campaign and upsert semantics (mirrors Character).

**New indexes**:
- `ix_npcs_campaign_name_lower` — functional unique index on `(func.lower(name), campaign_id)`

**Upsert Semantics** (service layer, FR-013):
- Same pattern as Character above: lookup by `lower(name)` + `campaign_id`, then UPDATE or INSERT.

---

## Entity Relationship Diagram

```
User
 │  (owner_id)
 ├──── Campaign ──── Player ──── Character
 │         │                        │
 │         ├──── NPC                └──── DigitalTwin
 │         ├──── Session ──── StoryEvent
 │         └──── SessionPlan
 └── (no direct link to Character/NPC — always via Campaign)
```

---

## Migration Strategy

**Alembic revision**: `0002_auth_admin_ui`

### Up Steps (in order)

1. **Create `users` table** with all columns defined above.
2. **Create default system user** (`username="system"`, `email="system@storyweaver.local"`, random hashed password, `is_active=False`) — needed for the backfill step.
3. **Add `owner_id` column to `campaigns`** as nullable UUID FK → users.id.
4. **Backfill `owner_id`**: Set all existing campaigns to the system user's id.
5. **Alter `owner_id` to NOT NULL** (SQLite requires table recreation; use batch mode in Alembic).
6. **Alter `join_code` column length** from String(8) to String(6) (batch mode). Existing 8-char codes remain valid — the length change only affects generation of new codes.
7. **Add functional unique index** on `campaigns`: `ix_campaigns_owner_name_lower`.
8. **Add functional unique index** on `characters`: `ix_characters_campaign_name_lower`.
9. **Add functional unique index** on `npcs`: `ix_npcs_campaign_name_lower`.
10. **Create `players` table** with all columns defined above.

### Down Steps (reverse order, for rollback)
- Drop `players` table
- Drop functional indexes on `npcs`, `characters`, `campaigns`
- Revert `join_code` column to String(8) (batch mode)
- Drop `owner_id` column from `campaigns` (batch mode)
- Drop `users` table

### SQLite Batch Mode Note
SQLite does not support `ALTER COLUMN` directly. Alembic's `batch_alter_table` context manager handles this by recreating the table with the new schema — this is safe and idiomatic for SQLite migrations.

---

## Schema Summary (new tables only)

```sql
-- users
CREATE TABLE users (
    id          TEXT PRIMARY KEY,          -- UUID stored as text
    username    TEXT NOT NULL UNIQUE,
    email       TEXT NOT NULL UNIQUE,
    hashed_password TEXT NOT NULL,
    is_active   INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL              -- ISO-8601 UTC
);
CREATE INDEX ix_users_username ON users (username);
CREATE INDEX ix_users_email    ON users (email);

-- players
CREATE TABLE players (
    id           TEXT PRIMARY KEY,
    campaign_id  TEXT NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    player_name  TEXT NOT NULL,
    character_id TEXT REFERENCES characters(id) ON DELETE SET NULL,
    created_at   TEXT NOT NULL
);
CREATE UNIQUE INDEX ix_players_campaign_player_name_lower
    ON players (lower(player_name), campaign_id);
```