"""Session CRUD — create, list, and retrieve play Sessions within a Campaign."""

from __future__ import annotations

import uuid
from datetime import date

from core.models import Session as GameSession
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def create_session(
    db: AsyncSession,
    campaign_id: uuid.UUID,
    title: str,
    date_played: date,
    summary: str | None = None,
) -> GameSession:
    """Create a new Session; session_number auto-increments within the campaign."""
    result = await db.execute(
        select(GameSession)
        .where(GameSession.campaign_id == campaign_id)
        .order_by(GameSession.session_number.desc())
        .limit(1)
    )
    last = result.scalar_one_or_none()
    next_number = (last.session_number + 1) if last is not None else 1

    session = GameSession(
        campaign_id=campaign_id,
        session_number=next_number,
        title=title,
        date_played=date_played,
        summary=summary,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


async def list_sessions(
    db: AsyncSession,
    campaign_id: uuid.UUID,
) -> list[GameSession]:
    """Return all Sessions for a campaign ordered by session_number ascending."""
    result = await db.execute(
        select(GameSession)
        .where(GameSession.campaign_id == campaign_id)
        .order_by(GameSession.session_number)
    )
    return list(result.scalars().all())


async def get_session(
    db: AsyncSession,
    session_id: uuid.UUID,
) -> GameSession | None:
    """Return a Session by its primary key, or None if not found."""
    result = await db.execute(
        select(GameSession).where(GameSession.id == session_id)
    )
    return result.scalar_one_or_none()