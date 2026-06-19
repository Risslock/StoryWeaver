# Data Model: Auth & Admin Reboot

## User
- `id: UUID` — primary key
- `username: str` — unique, 3–50 chars, case-insensitive uniqueness enforced by app logic and DB index
- `email: str` — unique, normalized to lowercase
- `hashed_password: str` — bcrypt hash stored in SQLite
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
- `player_name: str` — case-insensitive unique per campaign
- `character_id: UUID | None` — optional link to the player's character
- `created_at: datetime`
- Behavior:
  - `get_or_create_player()` performs case-insensitive upsert semantics on `player_name` per campaign

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
- `session_number: int`
- `title: str`
- `date_played: date`
- `summary: str | None`
- `created_at: datetime`

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
  - `display_name: str`
  - `role: "player" | "gm"`
  - `join_code: str`
  - `ai_available: bool`

## Relationships
- `User` owns `Campaign`
- `Campaign` owns `Character`, `NPC`, `Player`, `Session`, `SessionPlan`
- `Character` may have one `DigitalTwin`
- `NPC` may have one `DigitalTwin`
- `Player` may be linked to one `Character`

## Key Validation Rules
- `Campaign.join_code` must be globally unique.
- `Campaign.name` must be unique per owner, case-insensitive.
- `Player.player_name` must be unique per campaign, case-insensitive.
- `Character.name` must be unique per campaign, case-insensitive.
- `NPC.name` must be unique per campaign, case-insensitive.
- Player join requires non-empty `join_code` and `player_name`; campaign name is not required.
