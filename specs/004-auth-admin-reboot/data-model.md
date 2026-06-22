# Data Model: Auth & Admin Reboot

## User
- `id: UUID` — primary key
- `username: str` — unique, 3–50 chars, case-insensitive uniqueness enforced by app logic and DB index
- `email: str` — unique, normalized to lowercase
- `hashed_password: str` — SHA-256 hex digest (`hashlib.sha256(password.encode()).hexdigest()`); stored in the existing column; no bcrypt dependency
- `is_active: bool`
- `created_at: datetime`
- Relationships:
  - `campaigns: list[Campaign]`

## Campaign
- `id: UUID` — primary key
- `name: str` — owner-scoped unique campaign name, case-insensitive unique per `owner_id`
- `join_code: str` — globally unique 6-character code
- `gm_display_name: str` — display name for the GM
- `game_system: str` — e.g. `earthdawn_4e`
- `settings: JSON` — persisted campaign settings
- `world_notes: str | None` — single freeform Markdown document for the campaign; edited and rendered in the World Notes tab
- `archived: bool` — defaults to `False`; when `True` the campaign is hidden from the GM's default campaign list but all data is retained
- `created_at: datetime`
- `owner_id: UUID` — foreign key to `User`
- Relationships:
  - `characters: list[Character]`
  - `npcs: list[NPC]`
  - `players: list[Player]`
  - `sessions: list[Session]`
  - `session_plans: list[SessionPlan]`

## Player
- `id: UUID`
- `campaign_id: UUID` — links to `Campaign`
- `user_id: UUID` — FK to `User`; the authenticated account that owns this player record (added in migration `0004_player_user_link`)
- `player_name: str` — display name; populated automatically from `User.username` at join time; not entered by the user at join
- `character_id: UUID | None` — optional link to the player's character
- `created_at: datetime`
- Constraints:
  - Unique on `(campaign_id, user_id)` — one Player record per User per Campaign (index `ix_players_campaign_user`, replaces the old `ix_players_campaign_player_name_lower`)
- Behavior:
  - `get_or_create_player()` performs upsert on `(campaign_id, user_id)`; `player_name` is set from `User.username` on creation and not updated on subsequent lookups

## Character
- `id: UUID`
- `campaign_id: UUID`
- `player_display_name: str` — player-facing label for the character
- `name: str` — character name, unique per campaign case-insensitive
- `race: str`
- `discipline: str`
- `circle: int`
- `attributes: JSON`
- `derived_stats: JSON`
- `talents: JSON`
- `skills: JSON`
- `equipment: JSON`
- `background: str`
- `personality: str`
- `goals: str | None`
- `relationships: JSON`
- `physical_description: str | None`
- `portrait_url: str | None`
- `created_at: datetime`
- `updated_at: datetime`
- Behavior:
  - Character save operations must use case-insensitive name matching per campaign to update existing records rather than create duplicates.

## NPC
- `id: UUID`
- `campaign_id: UUID`
- `name: str` — unique per campaign case-insensitive
- `role: str | None`
- `race: str | None`
- `is_visible_to_players: bool`
- `discipline: str | None`
- `circle: int`
- `attributes: JSON`
- `derived_stats: JSON`
- `talents: JSON`
- `skills: JSON`
- `personality: str | None`
- `background: str | None`
- `physical_description: str | None`
- `portrait_url: str | None`
- `gm_notes: str | None`
- `created_at: datetime`
- `updated_at: datetime`
- Behavior:
  - NPC save operations must use case-insensitive name matching per campaign to update existing records rather than create duplicates.

## DigitalTwin
- `id: UUID`
- `entity_type: str` — `character` or `npc`
- `entity_id: UUID`
- `campaign_id: UUID`
- `conversation_history: JSON`
- `last_active: datetime`
- `created_at: datetime`
- Constraints:
  - Unique constraint on `(entity_type, entity_id)` ensures one twin per entity.

## Session
- `id: UUID`
- `campaign_id: UUID`
- `session_number: int` — auto-incremented per campaign
- `title: str` — GM-provided session name (e.g. "Session 1 — The Kaer")
- `date_played: date` — defaults to creation date; editable by GM
- `summary: str | None`
- `created_at: datetime`
- Behavior:
  - GMs create a Session before logging story events. StoryEvents are linked to a Session via `session_id`. Sessions act as grouping headers in the Story History view.

## StoryEvent
- `id: UUID`
- `campaign_id: UUID`
- `session_id: UUID | None`
- `event_type: str`
- `content: str`
- `participants: JSON`
- `is_public: bool`
- `event_order: int`
- `created_at: datetime`

## SessionPlan
- `id: UUID`
- `campaign_id: UUID`
- `session_id: UUID | None`
- `content: str`
- `annotations: JSON`
- `created_at: datetime`
- `updated_at: datetime`

## Runtime Session State
- `CampaignSession` is transient Gradio state, not persisted:
  - `campaign_id: UUID`
  - `display_name: str` — set from `User.username` for both roles
  - `role: "player" | "gm"`
  - `join_code: str`
  - `ai_available: bool`
  - `user_id: UUID` — the authenticated user's ID; used by player dashboard pages to look up the correct Player record via `(campaign_id, user_id)` instead of player name

## Relationships
- `User` owns `Campaign`
- `Campaign` owns `Character`, `NPC`, `Player`, `Session`, `SessionPlan`
- `Character` may have one `DigitalTwin`
- `NPC` may have one `DigitalTwin`
- `Player` may be linked to one `Character`

## Key Validation Rules
- `Campaign.join_code` must be globally unique.
- `Campaign.name` must be unique per owner, case-insensitive.
- `Campaign.archived` defaults to `False`; archived campaigns are excluded from the default campaign list query.
- `Player` is unique per `(campaign_id, user_id)` — one record per authenticated user per campaign.
- `Player.player_name` is populated from `User.username` at join time; no user input is required or accepted.
- `Character.name` must be unique per campaign, case-insensitive.
- `NPC.name` must be unique per campaign, case-insensitive.
- Player join requires an authenticated `user_id` and a non-empty `join_code`. No `player_name` field is presented to the user. Campaign name is not required.
- All users — including players — must be authenticated before any campaign join is permitted.
- `StoryEvent.session_id` should reference an existing `Session` for the same campaign; standalone events without a session are permitted but displayed under an "Unsorted" group.

## Required Migration
- **`0004_player_user_link`**: Adds `user_id UUID REFERENCES users(id) ON DELETE RESTRICT` (nullable in the migration to allow backfill; set NOT NULL after migration if no anonymous records exist). Drops `ix_players_campaign_player_name_lower`. Adds `ix_players_campaign_user` unique index on `(campaign_id, user_id)`.
