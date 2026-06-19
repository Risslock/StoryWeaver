"""Integration tests for character and NPC upsert semantics (US4)."""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from core.models import NPC, Campaign, Character, User
from services.auth import hash_password
from sqlalchemy import func, select
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
            username="gm",
            email="gm@example.com",
            hashed_password=hash_password("password"),
        )
        session.add(user)
        await session.flush()
        campaign = Campaign(
            id=uuid.uuid4(),
            name="Test Campaign",
            join_code="AB1234",
            gm_display_name="gm",
            owner_id=user.id,
        )
        session.add(campaign)
        await session.commit()
    return backend, campaign.id


def _char_data(name: str, race: str = "Elf") -> dict:
    return {
        "player_display_name": "player1",
        "name": name,
        "race": race,
        "discipline": "Archer",
        "circle": 1,
        "attributes": {},
        "derived_stats": {},
        "talents": [],
        "skills": [],
        "equipment": [],
        "background": "bg",
        "personality": "pers",
        "goals": None,
        "relationships": [],
        "physical_description": None,
        "portrait_url": None,
    }


async def _upsert_char(session, campaign_id, data: dict) -> Character:
    """Replicate the upsert logic from pages/player/character.py."""
    result = await session.execute(
        select(Character).where(
            Character.campaign_id == campaign_id,
            func.lower(Character.name) == data["name"].lower(),
        )
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        for k, v in data.items():
            if k not in ("id", "created_at", "campaign_id"):
                setattr(existing, k, v)
        await session.commit()
        await session.refresh(existing)
        return existing
    char = Character(id=uuid.uuid4(), campaign_id=campaign_id, **data)
    session.add(char)
    await session.commit()
    await session.refresh(char)
    return char


async def _upsert_npc(session, campaign_id, data: dict) -> NPC:
    result = await session.execute(
        select(NPC).where(
            NPC.campaign_id == campaign_id,
            func.lower(NPC.name) == data["name"].lower(),
        )
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        for k, v in data.items():
            if k not in ("id", "created_at", "campaign_id"):
                setattr(existing, k, v)
        await session.commit()
        await session.refresh(existing)
        return existing
    npc = NPC(id=uuid.uuid4(), campaign_id=campaign_id, **data)
    session.add(npc)
    await session.commit()
    await session.refresh(npc)
    return npc


# ── Character upsert tests ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_character_create_new_inserts(seeded):
    backend, campaign_id = seeded
    async with await backend.get_session() as session:
        char = await _upsert_char(session, campaign_id, _char_data("Kira", "Elf"))
    assert char.id is not None
    assert char.name == "Kira"


@pytest.mark.asyncio
async def test_character_create_same_name_updates(seeded):
    backend, campaign_id = seeded
    async with await backend.get_session() as session:
        c1 = await _upsert_char(session, campaign_id, _char_data("Kira", "Elf"))
    async with await backend.get_session() as session:
        c2 = await _upsert_char(session, campaign_id, _char_data("Kira", "Human"))
    assert c1.id == c2.id
    assert c2.race == "Human"


@pytest.mark.asyncio
async def test_character_create_case_insensitive_updates(seeded):
    backend, campaign_id = seeded
    async with await backend.get_session() as session:
        c1 = await _upsert_char(session, campaign_id, _char_data("Kira", "Elf"))
    async with await backend.get_session() as session:
        c2 = await _upsert_char(session, campaign_id, _char_data("KIRA", "Human"))
    assert c1.id == c2.id
    assert c2.race == "Human"


# ── NPC upsert tests ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_npc_create_new_inserts(seeded):
    backend, campaign_id = seeded
    async with await backend.get_session() as session:
        npc = await _upsert_npc(session, campaign_id, {
            "name": "Vorgath",
            "role": "merchant",
            "race": "Ork",
            "discipline": None,
            "circle": 0,
            "personality": "gruff",
            "background": "trader",
            "physical_description": None,
            "gm_notes": None,
            "attributes": {},
            "derived_stats": {},
            "talents": [],
            "skills": [],
            "is_visible_to_players": False,
            "portrait_url": None,
        })
    assert npc.id is not None
    assert npc.name == "Vorgath"


@pytest.mark.asyncio
async def test_npc_create_same_name_updates(seeded):
    backend, campaign_id = seeded
    data = {
        "name": "Vorgath", "role": "merchant", "race": "Ork",
        "discipline": None, "circle": 0, "personality": "gruff",
        "background": "trader", "physical_description": None,
        "gm_notes": None, "attributes": {}, "derived_stats": {},
        "talents": [], "skills": [], "is_visible_to_players": False,
        "portrait_url": None,
    }
    async with await backend.get_session() as session:
        n1 = await _upsert_npc(session, campaign_id, dict(data))
    async with await backend.get_session() as session:
        n2 = await _upsert_npc(session, campaign_id, dict(data) | {"role": "villain"})
    assert n1.id == n2.id
    assert n2.role == "villain"


@pytest.mark.asyncio
async def test_npc_create_case_insensitive_updates(seeded):
    backend, campaign_id = seeded
    data = {
        "name": "Vorgath", "role": "merchant", "race": "Ork",
        "discipline": None, "circle": 0, "personality": "gruff",
        "background": "trader", "physical_description": None,
        "gm_notes": None, "attributes": {}, "derived_stats": {},
        "talents": [], "skills": [], "is_visible_to_players": False,
        "portrait_url": None,
    }
    async with await backend.get_session() as session:
        n1 = await _upsert_npc(session, campaign_id, dict(data))
    async with await backend.get_session() as session:
        n2 = await _upsert_npc(session, campaign_id, dict(data) | {"name": "VORGATH", "role": "villain"})
    assert n1.id == n2.id
    assert n2.role == "villain"
