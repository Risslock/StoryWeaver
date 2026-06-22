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
- On successful registration (or sign-in), the app populates `user_state` and transitions to the **Hub Screen** — not directly to a campaign view.

## Hub Screen
**Who sees it**: any authenticated user (`user_state` set, `session_state` is None).

### Outputs
- Two action buttons: `"My Campaigns (GM)"` and `"Join a Campaign (Player)"`
- `"Sign Out"` button

### Behavior
- Clicking `"My Campaigns (GM)"` shows the GM Campaign List (hub is hidden).
- Clicking `"Join a Campaign (Player)"` shows the Player Join Screen (hub is hidden).
- Both paths have a `"← Hub"` back button to return without signing out.
- The same authenticated account can use both GM and Player paths.

## Player Join Screen
**Who sees it**: authenticated users who clicked `"Join a Campaign (Player)"` from the hub.

### Inputs
- Joined-campaigns table (read-only `gr.DataFrame`, columns: `[Campaign Name, Join Code]`) — lists campaigns the user has previously joined
- `join_code` (textbox) — **no `player_name` field; player name is set automatically from account username**
- `"Join Campaign"` button

### Outputs
- `session_state` — `CampaignSession` with `role = "player"` and `user_id` on success
- `join_status` — visible success or failure message (inline, per input)
- `rejoin_status` — visible message when a joined-campaign row is clicked

### Contract
- Player join requires only `join_code`. No `player_name` field is presented.
- `player_name` is set automatically from `User.username` at join time.
- If `join_code` is empty, return `"Enter the join code your GM gave you."`.
- If `join_code` is invalid or the campaign is archived, return `"No campaign found with that join code."`.
- Clicking a row in the joined-campaigns table re-enters that campaign without requiring the join code again.
- Anonymous join (join code without an account) is not supported. All users must authenticate.

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
  - `display_name: str` — set from `User.username` for both GM and player roles
  - `role: "player" | "gm"`
  - `user_id: UUID` — the authenticated user's ID; used by player dashboard pages to load the correct Player record via `(campaign_id, user_id)` instead of player name
  - `join_code: str`
  - `ai_available: bool`

- `UserInfo` fields:
  - `user_id: UUID`
  - `username: str`
