"""User and Player repository functions."""

from __future__ import annotations

import uuid

from core.models import Campaign, Player, User
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


async def get_user_by_username_or_email(
    session: AsyncSession,
    identifier: str,
) -> User | None:
    """Look up a user by username or email (both case-insensitive)."""
    normalised = identifier.strip().lower()
    result = await session.execute(
        select(User).where(func.lower(User.username) == normalised)
    )
    user = result.scalar_one_or_none()
    if user is not None:
        return user
    result = await session.execute(
        select(User).where(func.lower(User.email) == normalised)
    )
    return result.scalar_one_or_none()


async def create_user(
    session: AsyncSession,
    username: str,
    email: str,
    hashed_password: str,
) -> User:
    user = User(
        id=uuid.uuid4(),
        username=username.strip(),
        email=email.lower().strip(),
        hashed_password=hashed_password,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def get_or_create_player(
    session: AsyncSession,
    campaign_id: uuid.UUID,
    user_id: uuid.UUID,
    username: str,
) -> Player:
    """Return existing Player for (campaign_id, user_id) or create a new one.

    player_name is set from username at creation and not updated on lookup.
    """
    result = await session.execute(
        select(Player).where(
            Player.campaign_id == campaign_id,
            Player.user_id == user_id,
        )
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        return existing
    player = Player(
        id=uuid.uuid4(),
        campaign_id=campaign_id,
        user_id=user_id,
        player_name=username.strip(),
    )
    session.add(player)
    await session.commit()
    await session.refresh(player)
    return player


async def get_campaign_by_join_code(
    session: AsyncSession,
    join_code: str,
) -> Campaign | None:
    """Look up a campaign by its join code (case-insensitive)."""
    result = await session.execute(
        select(Campaign).where(
            func.upper(Campaign.join_code) == join_code.strip().upper()
        )
    )
    return result.scalar_one_or_none()


async def get_campaigns_for_user(
    session: AsyncSession,
    user_id: uuid.UUID,
) -> list[Campaign]:
    """Return non-archived campaigns owned by the user, newest first."""
    result = await session.execute(
        select(Campaign)
        .where(Campaign.owner_id == user_id, Campaign.archived.is_(False))
        .order_by(Campaign.created_at.desc())
    )
    return list(result.scalars().all())


async def archive_campaign(
    session: AsyncSession,
    campaign_id: uuid.UUID,
) -> None:
    """Soft-delete a campaign by setting archived=True. Data is never deleted."""
    result = await session.execute(
        select(Campaign).where(Campaign.id == campaign_id)
    )
    campaign = result.scalar_one_or_none()
    if campaign is not None:
        campaign.archived = True
        await session.commit()


async def get_campaigns_for_player(
    session: AsyncSession,
    user_id: uuid.UUID,
) -> list[Campaign]:
    """Return non-archived campaigns where the user has a Player record, newest first."""
    result = await session.execute(
        select(Campaign)
        .join(Player, Player.campaign_id == Campaign.id)
        .where(Player.user_id == user_id, Campaign.archived.is_(False))
        .order_by(Campaign.created_at.desc())
    )
    return list(result.scalars().all())


async def link_player_character(
    session: AsyncSession,
    player_id: uuid.UUID,
    character_id: uuid.UUID,
) -> Player:
    result = await session.execute(select(Player).where(Player.id == player_id))
    player = result.scalar_one()
    player.character_id = character_id
    await session.commit()
    await session.refresh(player)
    return player
