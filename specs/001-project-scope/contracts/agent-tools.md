# Agent Tool Contracts: StoryWeaver

**Branch**: `001-project-scope` | **Date**: 2026-06-18

All agents are implemented using Pydantic-AI (see research.md). Each tool is a typed Python function registered on a Pydantic-AI `Agent` instance. Inputs and outputs are Pydantic models. These schemas are the contracts; implementation lives in `packages/agents/`.

---

## Digital Twin Agent (Character or NPC)

**Location**: `packages/agents/twin/`

One `Agent` instance per Character or NPC. The system prompt is constructed from the entity's profile fields at instantiation. Context is isolated per entity — no cross-entity data leakage.

### Tool: `recall_story_events`

Retrieves recent or semantically relevant campaign story events for in-character grounding.

**Input**:
```python
class RecallEventsInput(BaseModel):
    query: str                       # Semantic or keyword query
    limit: int = 5                   # Max events to return
    session_id: UUID | None = None   # Restrict to a specific session if provided
```

**Output**:
```python
class RecallEventsOutput(BaseModel):
    events: list[StoryEventSummary]  # Ordered chronologically

class StoryEventSummary(BaseModel):
    session_number: int | None
    event_type: str
    content: str
    created_at: datetime
```

**Access control**: Character twin (player context) receives only `is_public = True` events. NPC twin (GM context) receives all events including `is_public = False`.

---

### Tool: `describe_entity_trait`

Retrieves a specific aspect of the entity's profile for in-character reference.

**Input**:
```python
class DescribeTraitInput(BaseModel):
    trait: Literal[
        "personality", "background", "goals",
        "relationships", "discipline", "skills", "profile"
    ]
```

**Output**:
```python
class DescribeTraitOutput(BaseModel):
    trait: str
    value: str
```

**Notes**: `"profile"` is valid only for NPC twins (maps to `NPC.profile` JSON). Character twins use the other trait values.

---

## Player Agent

**Location**: `packages/agents/player_agent/`

Wraps character management and twin interaction for the Player role. Enforces that Players only access their own data.

### Tool: `get_character_sheet`

**Input**:
```python
class GetCharacterInput(BaseModel):
    character_id: UUID
```

**Output**: `CharacterSchema` — Pydantic model mirroring the Character entity (all fields except `campaign_id`, which is implicit from session context).

**Access control**: Returns only characters where `Character.player_display_name` matches `CampaignSession.display_name`. Raises `AccessDeniedError` otherwise.

---

### Tool: `update_character_field`

**Input**:
```python
class UpdateCharacterInput(BaseModel):
    character_id: UUID
    field: str    # One of the updatable Character fields (validated against allowlist)
    value: Any    # Validated against the field's type before persisting
```

**Output**:
```python
class UpdateCharacterOutput(BaseModel):
    success: bool
    updated_field: str
    updated_value: Any
```

**Access control**: Player may only update their own characters. `portrait_url` is not updatable via this tool (image generation is a separate flow).

---

### Tool: `list_own_characters`

**Input**:
```python
class ListCharactersInput(BaseModel):
    campaign_id: UUID  # Implicit from session; included for explicitness
```

**Output**:
```python
class ListCharactersOutput(BaseModel):
    characters: list[CharacterSummary]

class CharacterSummary(BaseModel):
    id: UUID
    name: str
    race: str
    discipline: str
    circle: int
    has_portrait: bool
```

---

## GM Agent

**Location**: `packages/agents/gm_agent/`

Full campaign access including private NPC data and GM-only story events.

### Tool: `create_story_event`

**Input**:
```python
class CreateEventInput(BaseModel):
    session_id: UUID | None
    event_type: EventType  # Enum from data model
    content: str
    participants: list[ParticipantRef]
    is_public: bool = True

class ParticipantRef(BaseModel):
    entity_type: Literal["character", "npc"]
    entity_id: UUID
    name: str
```

**Output**:
```python
class CreateEventOutput(BaseModel):
    event_id: UUID
    created_at: datetime
```

---

### Tool: `toggle_npc_visibility`

**Input**:
```python
class ToggleNPCVisibilityInput(BaseModel):
    npc_id: UUID
    is_visible: bool
```

**Output**:
```python
class ToggleNPCVisibilityOutput(BaseModel):
    npc_id: UUID
    npc_name: str
    is_visible_to_players: bool
```

---

### Tool: `generate_session_plan`

Calls the LLM with story history context to draft a session plan.

**Input**:
```python
class GenerateSessionPlanInput(BaseModel):
    campaign_id: UUID
    session_number: int        # Upcoming session number
    focus_hints: list[str] = []  # GM-provided areas to emphasize
```

**Output**:
```python
class GenerateSessionPlanOutput(BaseModel):
    plan_markdown: str
    events_referenced: list[UUID]  # StoryEvent IDs used as context
```

**Precondition**: At least one Session must exist in the Campaign (FR-009 acceptance scenario 3 handled by returning a starter plan when history is empty, with a note that history is minimal).

---

### Tool: `get_all_npcs`

Returns all NPCs in the Campaign including private fields.

**Input**:
```python
class GetNPCsInput(BaseModel):
    campaign_id: UUID
    include_hidden: bool = True  # GM always sees hidden NPCs
```

**Output**:
```python
class GetNPCsOutput(BaseModel):
    npcs: list[NPCSchema]  # Full NPC entity including gm_notes
```

---

## Image Generation Interface (direct service call — not an agent tool)

Image generation is triggered from the Gradio UI layer, calling `packages/imagegen/interface.py` directly rather than routing through an agent tool.

```python
class ImageGenRequest(BaseModel):
    prompt: str              # Constructed from entity description fields
    negative_prompt: str = ""
    style_hints: list[str] = []
    width: int = 512
    height: int = 512
    entity_id: UUID          # For associating the result back to Character/NPC

class ImageGenResponse(BaseModel):
    image_url: str | None    # Path or URL to generated image; None on failure
    error: str | None        # Human-readable error when image_url is None
```

**Callers**:
- `apps/web/pages/player/character.py` — character portrait generation
- `apps/web/pages/gm/npcs.py` — NPC portrait generation
- `apps/web/pages/gm/history.py` — scene illustration (prompt from GM-provided description)