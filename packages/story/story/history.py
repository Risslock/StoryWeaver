"""StoryEvent CRUD and role-scoped chronological query for campaign story history."""

from __future__ import annotations

import uuid
from typing import Literal

from core.models import Session as GameSession
from core.models import StoryEvent
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def create_event(
    db: AsyncSession,
    campaign_id: uuid.UUID,
    event_type: str,
    content: str,
    is_public: bool = True,
    session_id: uuid.UUID | None = None,
    participants: list[dict] | None = None,
) -> StoryEvent:
    """Append a StoryEvent to the campaign timeline.

    event_order is computed as the count of existing events in the same session
    scope so that insertion order is preserved within a session.
    """
    scope_stmt = select(StoryEvent).where(StoryEvent.campaign_id == campaign_id)
    if session_id is not None:
        scope_stmt = scope_stmt.where(StoryEvent.session_id == session_id)
    else:
        scope_stmt = scope_stmt.where(StoryEvent.session_id.is_(None))
    scope_result = await db.execute(scope_stmt)
    event_order = len(list(scope_result.scalars().all()))

    event = StoryEvent(
        campaign_id=campaign_id,
        session_id=session_id,
        event_type=event_type,
        content=content,
        participants=participants or [],
        is_public=is_public,
        event_order=event_order,
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return event


async def list_events(
    db: AsyncSession,
    campaign_id: uuid.UUID,
    role: Literal["player", "gm"],
    session_id: uuid.UUID | None = None,
) -> list[StoryEvent]:
    """Return StoryEvents for a campaign, role-scoped and chronologically ordered.

    Player role: only is_public=True events.
    GM role: all events.
    Order: session_number ascending (NULL-session events appear last), then
    event_order ascending within each session.
    Restrict to a single session when session_id is provided.
    """
    stmt = (
        select(StoryEvent)
        .outerjoin(GameSession, StoryEvent.session_id == GameSession.id)
        .where(StoryEvent.campaign_id == campaign_id)
    )

    if role == "player":
        stmt = stmt.where(StoryEvent.is_public.is_(True))

    if session_id is not None:
        stmt = stmt.where(StoryEvent.session_id == session_id)

    stmt = stmt.order_by(
        GameSession.session_number.asc().nulls_last(),
        StoryEvent.event_order.asc(),
    )

    result = await db.execute(stmt)
    return list(result.scalars().all())