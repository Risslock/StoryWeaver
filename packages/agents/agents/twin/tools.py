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
    rag_retriever: Any | None = None,
) -> Any:
    """Return an async callable suitable for registration as a Pydantic-AI tool.

    Access control: character twins (player context) receive only is_public=True
    events; NPC twins (GM context) receive all events.

    When rag_retriever is provided (a HistoryRetriever instance), semantic search
    is used and results are re-ordered by semantic relevance. Falls back to SQL
    chronological query when RAG is unavailable.
    """
    from core.models import Session as GameSession
    from core.models import StoryEvent
    from sqlalchemy import select

    is_public_only = entity_type == "character"

    async def recall_story_events(inp: RecallEventsInput) -> RecallEventsOutput:
        # Attempt semantic RAG retrieval first.
        if rag_retriever is not None:
            try:
                chunks = await rag_retriever.search(inp.query, top_k=inp.limit)
                if chunks:
                    events: list[StoryEventSummary] = []
                    for chunk in chunks:
                        meta = chunk.metadata
                        if is_public_only and not meta.get("is_public", True):
                            continue
                        sn = meta.get("session_number")
                        events.append(
                            StoryEventSummary(
                                session_number=int(sn) if isinstance(sn, int) and sn >= 0 else None,
                                event_type=str(meta.get("event_type", "unknown")),
                                content=chunk.content,
                                created_at=datetime.utcnow(),
                            )
                        )
                    return RecallEventsOutput(events=events[: inp.limit])
            except Exception:
                pass  # RAG unavailable — fall through to SQL

        # SQL chronological fallback.
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

        sql_events = [
            StoryEventSummary(
                session_number=row[1].session_number if row[1] else None,
                event_type=row[0].event_type,
                content=row[0].content,
                created_at=row[0].created_at,
            )
            for row in rows
        ]
        sql_events.reverse()
        return RecallEventsOutput(events=sql_events)

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