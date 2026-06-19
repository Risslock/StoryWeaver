# UI Contract: Auth & Admin Reboot

## Auth Screen
### Inputs
- `identifier` (textbox) — username or email
- `password` (textbox, password type)
- `username` (textbox) — for account creation
- `email` (textbox) — for account creation
- `password` (textbox, password type) — for account creation
- `confirm_password` (textbox, password type) — for account creation

### Outputs
- `user_state` — `UserInfo` on success, or `None` on failure
- `login_status` / `reg_status` — visible text describing success or failure

### Behavior
- `Sign In` returns `Invalid username or password.` when credentials fail.
- `Create Account` returns a visible error for invalid input or duplicate username/email.
- On successful registration, the app should populate `user_state` and transition to the admin dashboard.

## Player Join Screen
### Inputs
- `join_code` (textbox)
- `player_name` (textbox)

### Outputs
- `session_state` — `CampaignSession` with `role = "player"` on success
- `join_status` — visible success or failure message

### Contract
- Player join requires only `join_code` and `player_name`.
- If `join_code` is invalid, return `Error: No campaign found with that join code.`
- If either field is empty, return an inline validation error explaining the missing field.

## GM Campaign Dashboard
### Inputs
- `campaign_name` (textbox)
- `game_system` (dropdown)
- `create_btn` — create campaign action
- campaign table row selection
- `resume_btn` — enter selected campaign
- `archive_btn` — archive the selected campaign (soft-delete)

### Outputs
- campaign table rows: `[Name, Join Code, Created]` — shows only non-archived campaigns by default
- campaign detail fields: name, join code, game system, created date
- `session_state` — `CampaignSession` with `role = "gm"` on resume
- `archive_status` — visible confirmation or error message after archive action

### Contract
- Campaign names must be unique per user, case-insensitive.
- Duplicate names show a visible error message near the create form.
- Successful campaign creation refreshes the table and hides the create form.
- Archiving a campaign sets `Campaign.archived = True` and removes it from the table. A visible confirmation message is shown. No data is deleted.

## GM Dashboard
### Outputs
- `gm_join_code` — read-only textbox showing the active campaign join code, displayed prominently at the top
- Tabs: Characters, NPCs, Story History, World Notes, Session Plan, Players
- Visible placeholder banner on AI-dependent tabs when `CampaignSession.ai_available` is false

### World Notes Tab Contract
- Inputs: `world_notes_input` (Markdown text area), `save_notes_btn`
- Outputs: rendered Markdown preview of the saved content, `notes_status` (visible save confirmation or error)
- Behavior: loads the current `Campaign.world_notes` value on tab entry; saving writes to `Campaign.world_notes` and re-renders the Markdown preview.

### Story History Tab Contract
- Inputs: `session_title` (textbox), `session_date` (date picker, defaults to today), `create_session_btn`; `event_description` (textbox), `log_event_btn`, `session_selector` (dropdown — selects which session to log under)
- Outputs: history view grouped by Session (session title as header, story events listed below); `session_status` / `event_status` visible messages
- Behavior: GMs create a Session before logging events; events are displayed grouped by session in chronological order.

### Players Tab Contract
- Outputs: read-only table with columns `[Player Name, Character Name]`; character name shows "—" if no character has been created yet
- Behavior: lists all `Player` records for the active campaign; no edit or remove actions.

## Player Dashboard
### Outputs
- Tabs: Character, Twin Chat, Story History
- Character tab allows viewing and editing of the player's character sheet.
- Twin Chat tab shows an AI unavailable placeholder if Ollama is down.
- History tab lists public story events.

## Transient State Contract
- `CampaignSession` fields:
  - `campaign_id: UUID`
  - `display_name: str`
  - `role: "player" | "gm"`
  - `join_code: str`
  - `ai_available: bool`

- `UserInfo` fields:
  - `user_id: UUID`
  - `username: str`
