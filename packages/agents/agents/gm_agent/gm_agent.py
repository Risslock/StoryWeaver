"""GM role agent — full campaign access including private NPC data and GM-only events."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from core.errors import EntityNotFoundError
from core.models import NPC, StoryEvent
from core.schemas import NPCSchema
from pydantic import BaseModel
from sqlalchemy import func, select
from story.history import list_events as _list_events
from story.session import list_sessions as _list_sessions


class ParticipantRef(BaseModel):
    entity_type: Literal["character", "npc"]
    entity_id: uuid.UUID
    name: str


EventType = Literal[
    "dialogue", "decision", "discovery", "combat_outcome",
    "npc_state_change", "world_change", "plot_thread_opened", "plot_thread_closed",
]


class CreateEventInput(BaseModel):
    session_id: uuid.UUID | None = None
    event_type: EventType
    content: str
    participants: list[ParticipantRef] = []
    is_public: bool = True


class CreateEventOutput(BaseModel):
    event_id: uuid.UUID
    created_at: datetime


class ToggleNPCVisibilityInput(BaseModel):
    npc_id: uuid.UUID
    is_visible: bool


class ToggleNPCVisibilityOutput(BaseModel):
    npc_id: uuid.UUID
    npc_name: str
    is_visible_to_players: bool


class GetNPCsInput(BaseModel):
    campaign_id: uuid.UUID
    include_hidden: bool = True


class GetNPCsOutput(BaseModel):
    npcs: list[NPCSchema]


class GenerateSessionPlanInput(BaseModel):
    campaign_id: uuid.UUID
    session_number: int
    focus_hints: list[str] = []


class GenerateSessionPlanOutput(BaseModel):
    plan_markdown: str
    events_referenced: list[uuid.UUID]


_PLANNING_SYSTEM_PROMPT = (
    "You are an expert tabletop RPG Game Master assistant specialising in Earthdawn 4E. "
    "Help the GM plan an engaging session that follows naturally from the campaign's story history. "
    "Reference specific past events and open plot threads. "
    "Be concise and actionable. Format your response as markdown with clear section headings."
)


def _format_events_for_prompt(
    events: list[Any],
    session_num_by_id: dict[uuid.UUID, int],
) -> str:
    lines: list[str] = []
    for e in events:
        session_label = (
            f"Session {session_num_by_id[e.session_id]}"
            if e.session_id and e.session_id in session_num_by_id
            else "Campaign-wide"
        )
        visibility = "Public" if e.is_public else "GM-only"
        lines.append(f"- [{session_label}] [{e.event_type}] [{visibility}] {e.content}")
    return "\n".join(lines)


def _build_planning_prompt(
    session_number: int,
    history_text: str,
    focus_hints: list[str],
) -> str:
    hints_block = ""
    if focus_hints:
        hints_block = "\n\nGM Focus Areas:\n" + "\n".join(f"- {h}" for h in focus_hints)
    return (
        f"Campaign Story History:\n{history_text}{hints_block}\n\n"
        f"Create a detailed plan for Session {session_number}. "
        "Reference specific past events and open plot threads from the history above. "
        "Include: session goals, key scenes, potential NPC interactions, and plot hooks."
    )


def _build_starter_plan(session_number: int, focus_hints: list[str]) -> str:
    hints_block = ""
    if focus_hints:
        hints_block = "\n\n**GM Focus Areas:**\n" + "\n".join(f"- {h}" for h in focus_hints)
    return (
        f"# Session {session_number} Plan\n\n"
        "_Note: This is a starter plan. The campaign has minimal story history — "
        "add completed sessions and events to enable more contextual AI planning._\n\n"
        "## Session Goals\n\n"
        "1. Introduce the players to the world of Barsaive\n"
        "2. Establish the central conflict or quest hook\n"
        "3. Create connections between player characters\n\n"
        "## Key Scenes\n\n"
        "- **Opening Scene**: Set the tone and draw players in\n"
        "- **Inciting Incident**: Present the main conflict or call to action\n"
        "- **Exploration**: Allow players to investigate and gather information\n"
        "- **Closing Hook**: End with a compelling reason to return next session\n\n"
        "## NPC Interactions\n\n"
        "- Introduce at least one memorable NPC with a clear agenda\n"
        "- Consider allies, rivals, or neutral parties\n\n"
        "## Notes\n\n"
        "- Adjust difficulty based on the group's playstyle\n"
        "- Leave room for player agency and unexpected choices"
        + hints_block
    )


def build_gm_agent_tools(
    campaign_id: uuid.UUID,
    db_session: Any,
    llm_provider: Any = None,
) -> dict[str, Any]:
    """Return async tool callables for the GM role.

    GM has full campaign access including private NPC fields and GM-only events.
    """

    async def create_story_event(inp: CreateEventInput) -> CreateEventOutput:
        count_stmt = select(func.count()).select_from(StoryEvent).where(
            StoryEvent.campaign_id == campaign_id
        )
        if inp.session_id is not None:
            count_stmt = count_stmt.where(StoryEvent.session_id == inp.session_id)
        count_result = await db_session.execute(count_stmt)
        event_order = count_result.scalar() or 0

        event = StoryEvent(
            campaign_id=campaign_id,
            session_id=inp.session_id,
            event_type=inp.event_type,
            content=inp.content,
            participants=[p.model_dump(mode="json") for p in inp.participants],
            is_public=inp.is_public,
            event_order=event_order,
        )
        db_session.add(event)
        await db_session.commit()
        return CreateEventOutput(event_id=event.id, created_at=event.created_at)

    async def toggle_npc_visibility(inp: ToggleNPCVisibilityInput) -> ToggleNPCVisibilityOutput:
        result = await db_session.execute(
            select(NPC).where(NPC.id == inp.npc_id, NPC.campaign_id == campaign_id)
        )
        npc = result.scalar_one_or_none()
        if npc is None:
            raise EntityNotFoundError(f"NPC {inp.npc_id} not found in this campaign.")
        npc.is_visible_to_players = inp.is_visible
        await db_session.commit()
        return ToggleNPCVisibilityOutput(
            npc_id=npc.id,
            npc_name=npc.name,
            is_visible_to_players=npc.is_visible_to_players,
        )

    async def get_all_npcs(inp: GetNPCsInput) -> GetNPCsOutput:
        stmt = select(NPC).where(NPC.campaign_id == inp.campaign_id)
        if not inp.include_hidden:
            stmt = stmt.where(NPC.is_visible_to_players.is_(True))
        result = await db_session.execute(stmt)
        npcs = list(result.scalars().all())
        return GetNPCsOutput(npcs=[NPCSchema.model_validate(n) for n in npcs])

    async def generate_session_plan(inp: GenerateSessionPlanInput) -> GenerateSessionPlanOutput:
        sessions = await _list_sessions(db_session, inp.campaign_id)
        events = await _list_events(db_session, inp.campaign_id, role="gm")

        session_num_by_id: dict[uuid.UUID, int] = {s.id: s.session_number for s in sessions}
        referenced_ids: list[uuid.UUID] = [e.id for e in events]

        if not events:
            return GenerateSessionPlanOutput(
                plan_markdown=_build_starter_plan(inp.session_number, inp.focus_hints),
                events_referenced=[],
            )

        history_text = _format_events_for_prompt(events, session_num_by_id)
        prompt = _build_planning_prompt(inp.session_number, history_text, inp.focus_hints)

        provider = llm_provider
        if provider is None:
            from llm.providers.ollama import OllamaProvider
            provider = OllamaProvider()

        plan_markdown = await provider.generate(prompt=prompt, system=_PLANNING_SYSTEM_PROMPT)

        return GenerateSessionPlanOutput(
            plan_markdown=plan_markdown,
            events_referenced=referenced_ids,
        )

    return {
        "create_story_event": create_story_event,
        "toggle_npc_visibility": toggle_npc_visibility,
        "get_all_npcs": get_all_npcs,
        "generate_session_plan": generate_session_plan,
    }