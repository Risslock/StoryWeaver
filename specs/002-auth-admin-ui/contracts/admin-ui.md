# Contract: Admin Campaign UI

**Feature**: 002-auth-admin-ui | **Date**: 2026-06-19

This contract defines the screens, interactions, and data shapes for the authenticated GM admin interface (`apps/web/pages/admin/campaigns.py`).

---

## Screen 1: Campaign Dashboard

**URL path**: `/` (main Gradio app, shown after login)

**Trigger**: Rendered when an authenticated GM opens the app or navigates back from a campaign.

### Layout

```
╔══════════════════════════════════════════════╗
║  StoryWeaver — My Campaigns                  ║
╠══════════════════════════════════════════════╣
║  [+ New Campaign]                            ║
║                                              ║
║  ┌────────────────────────────────────────┐  ║
║  │ Name       │ Join Code │ Created       │  ║
║  ├────────────────────────────────────────┤  ║
║  │ The Iron   │  A3KP72   │ 2026-06-01    │  ║
║  │ Crown      │  [copy]   │  [Open →]     │  ║
║  ├────────────────────────────────────────┤  ║
║  │ Thornhaven │  B9QZ14   │ 2026-06-15    │  ║
║  │            │  [copy]   │  [Open →]     │  ║
║  └────────────────────────────────────────┘  ║
╚══════════════════════════════════════════════╝
```

### Components

| Component | Gradio Type | Behaviour |
|-----------|-------------|-----------|
| Campaign list | `gr.Dataframe` (read-only) | Rows: `[name, join_code, created_at]`; refreshed on load and after create |
| New Campaign button | `gr.Button` | Expands inline "Create Campaign" form |
| Create Campaign form | `gr.Group` (hidden until toggled) | Fields: campaign name (`gr.Textbox`), game system (`gr.Dropdown`); [Create] button |
| Open → button | `gr.Button` per row (or row click) | Loads Campaign Detail screen for selected campaign |
| Copy join code | `gr.Button` with `copy` action | Copies join code to clipboard |

### Data Queries

- **Load**: `SELECT id, name, join_code, created_at FROM campaigns WHERE owner_id = ? ORDER BY created_at DESC`
- **Create**: Validate uniqueness, generate join code, `INSERT INTO campaigns`
- **Error state**: If create fails (duplicate name), display inline error below the form

### Create Campaign Interaction

```
Input:  campaign name (str), game system (str, default "earthdawn_4e")
Output: success message + updated campaign list, OR error message (duplicate name)

Validation:
  - Name must not be empty
  - Name must not already exist for this owner (case-insensitive)
  - Join code generated as 6-char UPPERCASE alphanumeric, globally unique (retry if collision)
```

---

## Screen 2: Campaign Detail

**Trigger**: GM selects a campaign from the dashboard (Open →).

### Layout

```
╔══════════════════════════════════════════════╗
║  [← Back to Campaigns]                       ║
║  Campaign: The Iron Crown                    ║
║                                              ║
║  Join Code:  A3KP72   [copy]                 ║
║  Game System: Earthdawn 4th Ed               ║
║  Created:    2026-06-01                      ║
║                                              ║
║  [Resume Campaign →]                         ║
╚══════════════════════════════════════════════╝
```

### Components

| Component | Gradio Type | Behaviour |
|-----------|-------------|-----------|
| Campaign name | `gr.Markdown` | Display only |
| Join code | `gr.Textbox` (interactive=False, buttons=["copy"]) | Copyable string, NOT editable |
| Game system | `gr.Markdown` | Display only |
| Created at | `gr.Markdown` | ISO date display |
| Back button | `gr.Button` | Returns to Campaign Dashboard screen |
| Resume Campaign | `gr.Button` | Loads the full GM dashboard (`gm_col`) with this campaign's session state |

### Data Query

- `SELECT name, join_code, game_system, created_at FROM campaigns WHERE id = ? AND owner_id = ?`
- The `owner_id` check prevents GMs from accessing campaigns they don't own (authorization, not just authentication).

### Resume Campaign

When the GM clicks "Resume Campaign":
1. Load `CampaignSession(campaign_id=..., display_name=username, role="gm", join_code=..., ai_available=...)` into `gr.State`.
2. The existing `session_state.change` → `_navigate()` handler shows `gm_col` (no changes needed to that logic).

---

## Navigation State Machine

```
[Login screen]
     │ success
     ▼
[Campaign Dashboard]  ◄─────────────┐
     │ Open →                       │ ← Back
     ▼                               │
[Campaign Detail] ──── Resume ──► [GM Dashboard]
```

---

## Error States

| Scenario | Display |
|----------|---------|
| Create campaign — duplicate name | `gr.Warning` below form: "A campaign named '{name}' already exists." |
| Create campaign — empty name | `gr.Warning`: "Campaign name cannot be empty." |
| Resume campaign — campaign not found (deleted race) | `gr.Warning`: "Campaign no longer exists." → return to dashboard |
| Load dashboard — no campaigns yet | Empty dataframe with helper text: "No campaigns yet — create one above." |