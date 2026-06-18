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


def build_gm_agent_tools(campaign_id: uuid.UUID, db_session: Any) -> dict[str, Any]:
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

    return {
        "create_story_event": create_story_event,
        "toggle_npc_visibility": toggle_npc_visibility,
        "get_all_npcs": get_all_npcs,
    }