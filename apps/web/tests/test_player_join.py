"""Integration tests for player join flow (US2)."""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from core.models import Campaign, User
from services.auth import hash_password
from storage.sqlite.adapter import SQLiteBackend
from storage.users import get_or_create_player, link_player_character


@pytest.fixture
def backend(tmp_path):
    db_url = f"sqlite+aiosqlite:///{tmp_path}/test.db"
    return SQLiteBackend(db_url)


@pytest_asyncio.fixture
async def seeded(backend):
    await backend.initialize_db()
    # Create a user and campaign for tests
    async with await backend.get_session() as session:
        user = User(
            id=uuid.uuid4(),
            username="gm",
            email="gm@example.com",
            hashed_password=hash_password("password"),
        )
        session.add(user)
        await session.flush()
        campaign = Campaign(
            id=uuid.uuid4(),
            name="Test Campaign",
            join_code="ABC123",
            gm_display_name="gm",
            owner_id=user.id,
        )
        session.add(campaign)
        await session.commit()
    return backend, campaign.id


@pytest.mark.asyncio
async def test_player_created_on_first_join(seeded):
    backend, campaign_id = seeded
    async with await backend.get_session() as session:
        player = await get_or_create_player(session, campaign_id, "Kira")
    assert player.id is not None
    assert player.player_name == "Kira"
    assert player.character_id is None


@pytest.mark.asyncio
async def test_player_not_duplicated_on_rejoin(seeded):
    backend, campaign_id = seeded
    async with await backend.get_session() as session:
        p1 = await get_or_create_player(session, campaign_id, "Kira")
    async with await backend.get_session() as session:
        p2 = await get_or_create_player(session, campaign_id, "Kira")
    assert p1.id == p2.id


@pytest.mark.asyncio
async def test_player_case_insensitive_match(seeded):
    backend, campaign_id = seeded
    async with await backend.get_session() as session:
        p1 = await get_or_create_player(session, campaign_id, "Kira")
    async with await backend.get_session() as session:
        p2 = await get_or_create_player(session, campaign_id, "kira")
    assert p1.id == p2.id


@pytest.mark.asyncio
async def test_player_character_id_restored_on_rejoin(seeded):
    backend, campaign_id = seeded
    char_id = uuid.uuid4()

    async with await backend.get_session() as session:
        player = await get_or_create_player(session, campaign_id, "Kira")
        player = await link_player_character(session, player.id, char_id)

    async with await backend.get_session() as session:
        rejoined = await get_or_create_player(session, campaign_id, "Kira")
    assert rejoined.character_id == char_id


@pytest.mark.asyncio
async def test_invalid_join_code_not_found(backend):
    await backend.initialize_db()
    from core.models import Campaign
    from sqlalchemy import select
    async with await backend.get_session() as session:
        result = await session.execute(
            select(Campaign).where(Campaign.join_code == "XXXXXX")
        )
        assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_wrong_campaign_name_wrong_join_code(seeded):
    backend, campaign_id = seeded
    from core.models import Campaign
    from sqlalchemy import func, select
    async with await backend.get_session() as session:
        result = await session.execute(
            select(Campaign).where(
                func.lower(Campaign.name) == "wrong campaign",
                Campaign.join_code == "XXXXXX",
            )
        )
        assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_correct_join_code_wrong_name_returns_nothing(seeded):
    backend, campaign_id = seeded
    from core.models import Campaign
    from sqlalchemy import func, select
    async with await backend.get_session() as session:
        result = await session.execute(
            select(Campaign).where(
                func.lower(Campaign.name) == "wrong name",
                Campaign.join_code == "ABC123",
            )
        )
        assert result.scalar_one_or_none() is None
