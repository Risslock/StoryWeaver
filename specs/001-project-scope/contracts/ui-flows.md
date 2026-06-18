# UI Contracts: Gradio Role-Scoped Flows

**Branch**: `001-project-scope` | **Date**: 2026-06-18

StoryWeaver's Gradio UI has two role-scoped layouts and a shared landing flow. All page files live in `apps/web/pages/`. Role routing is determined after joining based on `CampaignSession.role`.

---

## Flow 1 — Campaign Join (Landing)

**File**: `apps/web/pages/landing.py`

**Purpose**: Allow a user to join an existing Campaign or create a new one, establishing their `CampaignSession`.

### Create Campaign

| Component | Type | Validation |
|-----------|------|-----------|
| `campaign_name` | `gr.Textbox` | Required; 1–255 chars |
| `gm_display_name` | `gr.Textbox` | Required; 1–100 chars |
| `create_btn` | `gr.Button` | Creates Campaign, assigns GM role |

**Outputs**: `join_code` displayed for sharing; user session set to GM role.

### Join Campaign

| Component | Type | Validation |
|-----------|------|-----------|
| `join_code` | `gr.Textbox` | Required; 8-char alphanumeric |
| `display_name` | `gr.Textbox` | Required; 1–100 chars |
| `join_btn` | `gr.Button` | Triggers join flow |

**Outputs**:

| Component | Type | Notes |
|-----------|------|-------|
| `session_state` | `gr.State` | Populated `CampaignSession` on success |
| `error_message` | `gr.Markdown` | Shown on invalid code or blank name |
| Role layout | conditional `visible` | Player or GM tabs made visible |

**Business rules**:
- If join code matches a Campaign and `display_name` equals `Campaign.gm_display_name`, role = `"gm"` (GM re-join after refresh).
- If join code matches but display name differs, role = `"player"`.
- If join code does not exist, show error; state remains null.
- AI availability is checked at join time via health-check on the configured LLM provider; `CampaignSession.ai_available` is set accordingly.

---

## Flow 2 — Player Layout

**Files**: `apps/web/pages/player/`

Three tabs are visible to Players: **My Character**, **My Twin**, **Story History**.

### Tab: My Character (`character.py`)

| Component | Type | Notes |
|-----------|------|-------|
| Character selector | `gr.Dropdown` | Player's own characters in this campaign; supports multiple |
| New character button | `gr.Button` | Opens character creation form |
| Character fields | `gr.Textbox`, `gr.Number`, `gr.JSON` | One component per Character entity field |
| Save button | `gr.Button` | |
| Generate portrait button | `gr.Button` | Triggers `packages/imagegen` call; `interactive=False` in degraded mode |
| Character portrait | `gr.Image` | Displayed if `portrait_url` is set |
| Confirmation message | `gr.Markdown` | Shown on successful save |

**Business rules**: Player sees and edits only their own characters (filtered by `player_display_name` from session state).

---

### Tab: My Twin (`twin_chat.py`)

| Component | Type | Notes |
|-----------|------|-------|
| Character selector | `gr.Dropdown` | Player's own characters |
| `user_prompt` | `gr.Textbox` | Situation or question for the twin |
| Submit button | `gr.Button` | Sends to DigitalTwin agent; `interactive=False` in degraded mode |
| `chat_history` | `gr.Chatbot` | Rolling conversation; persisted to `DigitalTwin.conversation_history` |
| AI unavailable notice | `gr.Markdown` | Visible when `ai_available = False` |

**Business rules**: The submit button is `interactive=False` when `CampaignSession.ai_available = False`. Each response is appended to `DigitalTwin.conversation_history` and saved.

---

### Tab: Story History (`history.py`)

| Component | Type | Notes |
|-----------|------|-------|
| Session selector | `gr.Dropdown` | All sessions in the Campaign |
| Filter by event type | `gr.CheckboxGroup` | Filters by `StoryEvent.event_type` |
| Event list | `gr.Dataframe` or `gr.Markdown` | Shows public events only (`is_public = True`) |

**Business rules**: Only `StoryEvent` records with `is_public = True` are returned for Player-role requests. Events displayed in chronological order (by `session_number`, then `event_order`).

**Performance**: Load must complete in < 5 seconds for ≥5 sessions / ≥20 events (SC-008).

---

## Flow 3 — GM Layout

**Files**: `apps/web/pages/gm/`

Five tabs visible to GMs: **Characters**, **NPCs**, **Story History**, **World Notes**, **Session Plan**.

---

### Tab: Characters (`characters.py`)

Read-only overview of all Characters in the Campaign. GM sees all characters from all players but cannot edit them (player ownership is preserved).

| Component | Type | Notes |
|-----------|------|-------|
| Character list | `gr.Dataframe` | All campaign characters: name, race, discipline, player |
| Character detail view | `gr.Markdown` | Full sheet on selection; read-only |

---

### Tab: NPCs (`npcs.py`)

| Component | Type | Notes |
|-----------|------|-------|
| NPC selector | `gr.Dropdown` | All campaign NPCs |
| New NPC button | `gr.Button` | Opens NPC creation form |
| NPC profile fields | `gr.Textbox`, `gr.JSON` | Full profile including `gm_notes` |
| Visibility toggle | `gr.Checkbox` | Sets `is_visible_to_players`; default unchecked |
| Save button | `gr.Button` | |
| Twin chat prompt | `gr.Textbox` | GM queries this NPC's DigitalTwin |
| Twin submit button | `gr.Button` | `interactive=False` in degraded mode |
| Twin response | `gr.Chatbot` | NPC DigitalTwin conversation |
| Generate portrait button | `gr.Button` | `interactive=False` in degraded mode |
| NPC portrait | `gr.Image` | Displayed if `portrait_url` set |

**Business rules**: All NPC fields including `gm_notes` are visible to the GM. Visibility toggle directly sets `NPC.is_visible_to_players`.

---

### Tab: Story History (`history.py`)

Same as the player history tab with these additions:

| Component | Type | Notes |
|-----------|------|-------|
| Event list | Shows all events including `is_public = False` (GM-only events) |
| Log event form | `gr.Group` | Creates new `StoryEvent`: type, content, participants, public flag |
| Log event button | `gr.Button` | |
| Generate summary button | `gr.Button` | Calls LLM to summarize selected session; `interactive=False` in degraded mode |

---

### Tab: World Notes (`world_notes.py`)

Private GM lore notes for the Campaign. In v1, stored as `StoryEvent` records with `event_type = "world_change"` and `is_public = False`. Rendered as a live markdown editor.

| Component | Type | Notes |
|-----------|------|-------|
| Notes editor | `gr.Code` (markdown mode) | Full markdown editing |
| Save button | `gr.Button` | Persists as `StoryEvent` |
| Notes history | `gr.Dataframe` | Past world-change entries, newest first |

---

### Tab: Session Plan (`session_plan.py`)

| Component | Type | Notes |
|-----------|------|-------|
| Session selector | `gr.Dropdown` | Upcoming or current session |
| Generate plan button | `gr.Button` | Calls GM planning agent with story history context; `interactive=False` in degraded mode |
| Plan editor | `gr.Code` (markdown mode) | GM edits the generated or existing plan |
| Save button | `gr.Button` | Persists to `SessionPlan` |
| Generated plan preview | `gr.Markdown` | Live preview of plan content |
| Planning unavailable notice | `gr.Markdown` | Visible when `ai_available = False` |

**Business rules**: The planning agent uses the Campaign's `StoryEvent` history as context to generate the plan. GM edits are preserved; re-generating overwrites the current plan content (with confirmation prompt).

---

## Degraded Mode Banner

**File**: `apps/web/components/banner.py`

A persistent `gr.HTML` component rendered at the top of every page layout when `CampaignSession.ai_available = False`.

**Content**: "AI features are currently unavailable. Character sheets, story history, and campaign navigation remain accessible."

**Effect on AI-dependent controls** (all set `interactive=False`):
- Twin chat submit buttons (Player and GM)
- Generate portrait buttons (Player character, GM NPC)
- Generate scene art button (GM)
- Generate session summary button (GM)
- Generate session plan button (GM)