"""Integration tests for campaign creation and admin UI (US3)."""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from core.models import Campaign, User
from services.auth import hash_password
from storage.sqlite.adapter import SQLiteBackend


@pytest.fixture
def backend(tmp_path):
    db_url = f"sqlite+aiosqlite:///{tmp_path}/test.db"
    return SQLiteBackend(db_url)


@pytest_asyncio.fixture
async def seeded(backend):
    await backend.initialize_db()
    async with await backend.get_session() as session:
        user = User(
            id=uuid.uuid4(),
            username="gm1",
            email="gm1@example.com",
            hashed_password=hash_password("pass1"),
        )
        session.add(user)
        await session.commit()
        owner_id = user.id
    return backend, owner_id


@pytest_asyncio.fixture
async def two_users(backend):
    await backend.initialize_db()
    async with await backend.get_session() as session:
        user1 = User(
            id=uuid.uuid4(),
            username="gm1",
            email="gm1@example.com",
            hashed_password=hash_password("pass1"),
        )
        user2 = User(
            id=uuid.uuid4(),
            username="gm2",
            email="gm2@example.com",
            hashed_password=hash_password("pass2"),
        )
        session.add_all([user1, user2])
        await session.commit()
        return backend, user1.id, user2.id


def _make_join_code() -> str:
    import re
    import secrets
    chars = re.sub(r"[^A-Z0-9]", "", secrets.token_urlsafe(16).upper())
    return chars[:6]


@pytest.mark.asyncio
async def test_campaign_creation_sets_owner_id(seeded):
    backend, owner_id = seeded
    async with await backend.get_session() as session:
        campaign = Campaign(
            id=uuid.uuid4(),
            name="Iron Crown",
            join_code=_make_join_code(),
            gm_display_name="gm1",
            owner_id=owner_id,
        )
        session.add(campaign)
        await session.commit()
        cid = campaign.id

    async with await backend.get_session() as session:
        from sqlalchemy import select
        result = await session.execute(select(Campaign).where(Campaign.id == cid))
        stored = result.scalar_one()
    assert stored.owner_id == owner_id


@pytest.mark.asyncio
async def test_join_code_is_six_char_alphanumeric(seeded):
    backend, owner_id = seeded
    code = _make_join_code()
    assert len(code) == 6
    assert code.isalnum()
    assert code == code.upper()


@pytest.mark.asyncio
async def test_campaign_list_returns_only_owner_campaigns(seeded):
    backend, owner_id = seeded
    other_id = uuid.uuid4()
    async with await backend.get_session() as session:
        user2 = User(
            id=other_id,
            username="gm2",
            email="gm2@example.com",
            hashed_password=hash_password("pass2"),
        )
        session.add(user2)
        c1 = Campaign(
            id=uuid.uuid4(),
            name="Campaign A",
            join_code=_make_join_code(),
            gm_display_name="gm1",
            owner_id=owner_id,
        )
        c2 = Campaign(
            id=uuid.uuid4(),
            name="Campaign B",
            join_code=_make_join_code(),
            gm_display_name="gm2",
            owner_id=other_id,
        )
        session.add_all([c1, c2])
        await session.commit()

    from sqlalchemy import select
    async with await backend.get_session() as session:
        result = await session.execute(
            select(Campaign)
            .where(Campaign.owner_id == owner_id)
            .order_by(Campaign.created_at.desc())
        )
        campaigns = result.scalars().all()
    assert len(campaigns) == 1
    assert campaigns[0].name == "Campaign A"


@pytest.mark.asyncio
async def test_two_users_can_have_same_campaign_name(two_users):
    backend, user1_id, user2_id = two_users
    async with await backend.get_session() as session:
        c1 = Campaign(
            id=uuid.uuid4(),
            name="Shared Name",
            join_code=_make_join_code(),
            gm_display_name="gm1",
            owner_id=user1_id,
        )
        c2 = Campaign(
            id=uuid.uuid4(),
            name="Shared Name",
            join_code=_make_join_code(),
            gm_display_name="gm2",
            owner_id=user2_id,
        )
        session.add_all([c1, c2])
        await session.commit()

    from sqlalchemy import select
    async with await backend.get_session() as session:
        result = await session.execute(
            select(Campaign).where(Campaign.name == "Shared Name")
        )
        all_campaigns = result.scalars().all()
    assert len(all_campaigns) == 2
