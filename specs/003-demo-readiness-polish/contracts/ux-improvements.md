# UX Improvement Contracts: Demo-Readiness Polish

**Plan**: [plan.md](../plan.md) | **Research**: [research.md](../research.md)

---

## Contract 1 — Session Summary (AI-Enhanced)

**File**: `apps/web/pages/gm/history.py` — `on_generate_summary`

### Current behavior

Returns a markdown string concatenating events with emoji prefixes. Example:
```
## Session: Tuesday Night (Session 3)

💬 Dialogue: The party interrogates the innkeeper
🔍 Discovery: A hidden tunnel is found beneath the hearth
```

### New behavior (AI mode)

Calls an LLM to produce a 2–3 sentence narrative paragraph. Example:
```
The adventurers confronted the wary innkeeper, extracting a confession about 
the criminal network using his cellar. Their search of the premises uncovered 
a concealed tunnel beneath the hearth, revealing how the smugglers had evaded 
the city guard for months.
```

### New behavior (degraded mode / LLM error)

Same as current behavior: returns the formatted event list. Never returns blank output when events exist.

### Handler signature (no change)

```python
async def on_generate_summary(
    state: CampaignSession,
    summary_sel: str | None,
    session_map: dict[str, uuid.UUID],
) -> str:
```

Return type is `str` (markdown text for `gr.Markdown` component). No new Gradio outputs added.

### Prompt template

```
System:
You are a tabletop RPG scribe. Write a 2-3 sentence narrative summary 
of the session events listed below. Use past tense. Be concise and vivid.
Do not reference game mechanics, dice rolls, or rule terms.

User:
Session: {session_label}
Events:
{event_list_lines}
```

Where `event_list_lines` is each event formatted as `- [{type}] {content}`.

---

## Contract 2 — Scene Description Pre-population

**File**: `apps/web/pages/gm/history.py` — new handler `on_populate_scene_description`

### Trigger

Fires when the GM selects a session in `view_session_selector` (the existing session filter dropdown in the Scene Illustration section).

### Behavior

1. If the selected session has no events → set `scene_description_input` to `""` (empty string, preserving any text the GM may have typed manually if no session selected)
2. If events exist → format up to 5 events as `[Type] content` lines and set `scene_description_input` to that text

### Example output in `scene_description_input`

```
[Dialogue] The party negotiates passage with the border guards
[Discovery] A collapsed tower marks the edge of the ancient ruins
[Combat] Ambush by three armed scouts near the northern gate
```

### Handler signature (new function)

```python
async def on_populate_scene_description(
    state: CampaignSession,
    session_label: str | None,
    session_map: dict[str, uuid.UUID],
) -> str:
```

Return type is `str` (plain text for `gr.Textbox`).

### Wiring

```python
view_session_selector.change(
    on_populate_scene_description,
    inputs=[session_state, view_session_selector, session_map_state],
    outputs=[scene_description_input],
)
```

This is a **second** `.change` listener on `view_session_selector`. The existing listener that refreshes the event table continues unchanged.

---

## Contract 3 — Ruff Linting Baseline

**Files**: `pyproject.toml` (1 line addition only)

### Addition to `[tool.ruff.lint.per-file-ignores]`

```toml
"harness/**" = ["E501"]
```

This removes `harness/runner.py` (107 violations) from the E501 gate, scoping linting to app and package code only. Harness is evaluation tooling; its long lines describe eval scenarios and are intentional.

All other ruff rules continue to apply to `harness/`. This change does not suppress any rule for `apps/` or `packages/`.

---

## Contract 4 — on_log_event Variable Rename

**File**: `apps/web/pages/gm/history.py` — `on_log_event`

### Current (confusing)

```python
_, new_session_map, view_update, updated_session_map, rows, ids, ...
```

### Renamed (matches actual semantics)

```python
log_sel_update, view_sel_update, summary_sel_update, session_map, rows, ids, ...
```

Values are identical; only variable names change. This is a pure readability fix bundled with the linting pass.