"""Tool schemas and implementations for the digital twin agent."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel


class RecallEventsInput(BaseModel):
    query: str
    limit: int = 5
    session_id: uuid.UUID | None = None


class StoryEventSummary(BaseModel):
    session_number: int | None
    event_type: str
    content: str
    created_at: datetime


class RecallEventsOutput(BaseModel):
    events: list[StoryEventSummary]


class DescribeTraitInput(BaseModel):
    trait: Literal[
        "personality", "background", "goals",
        "relationships", "discipline", "skills", "profile"
    ]


class DescribeTraitOutput(BaseModel):
    trait: str
    value: str


def build_recall_tool(
    campaign_id: uuid.UUID,
    entity_type: str,
    db_session: Any,
) -> Any:
    """Return an async callable suitable for registration as a Pydantic-AI tool.

    Access control: character twins (player context) receive only is_public=True
    events; NPC twins (GM context) receive all events.
    """
    from sqlalchemy import select
    from core.models import StoryEvent, Session as GameSession

    is_public_only = entity_type == "character"

    async def recall_story_events(inp: RecallEventsInput) -> RecallEventsOutput:
        stmt = (
            select(StoryEvent, GameSession)
            .outerjoin(GameSession, StoryEvent.session_id == GameSession.id)
            .where(StoryEvent.campaign_id == campaign_id)
        )
        if is_public_only:
            stmt = stmt.where(StoryEvent.is_public.is_(True))
        if inp.session_id is not None:
            stmt = stmt.where(StoryEvent.session_id == inp.session_id)
        stmt = stmt.order_by(StoryEvent.created_at.desc()).limit(inp.limit)

        result = await db_session.execute(stmt)
        rows = result.all()

        events = [
            StoryEventSummary(
                session_number=row[1].session_number if row[1] else None,
                event_type=row[0].event_type,
                content=row[0].content,
                created_at=row[0].created_at,
            )
            for row in rows
        ]
        events.reverse()
        return RecallEventsOutput(events=events)

    return recall_story_events


def build_describe_trait_tool(entity_data: dict[str, Any]) -> Any:
    """Return an async callable that looks up a trait from the entity profile dict."""

    async def describe_entity_trait(inp: DescribeTraitInput) -> DescribeTraitOutput:
        trait = inp.trait
        value: Any = entity_data.get(trait, "")
        if isinstance(value, list):
            value = ", ".join(str(item) for item in value) if value else "none"
        elif isinstance(value, dict):
            value = "; ".join(f"{k}: {v}" for k, v in value.items()) if value else "none"
        elif not value:
            value = "not specified"
        return DescribeTraitOutput(trait=trait, value=str(value))

    return describe_entity_trait