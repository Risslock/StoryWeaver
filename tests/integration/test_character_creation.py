"""Integration tests — US1 acceptance scenarios 1 and 3.

Scenario 1: Create character → all fields saved to DB
Scenario 3: Character sheet displays all saved data accurately and completely
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select

from core.models import Campaign, Character
from core.schemas import CharacterSchema
from rules_earthdawn.validator import validate_character
from storage.sqlite.adapter import SQLiteBackend


@pytest_asyncio.fixture
async def backend() -> SQLiteBackend:
    db = SQLiteBackend("sqlite+aiosqlite:///:memory:")
    await db.initialize_db()
    return db


@pytest_asyncio.fixture
async def campaign(backend: SQLiteBackend) -> Campaign:
    async with await backend.get_session() as session:
        c = Campaign(
            id=uuid.uuid4(),
            name="Test Campaign",
            join_code="TESTC001",
            gm_display_name="TestGM",
        )
        session.add(c)
        await session.commit()
        await session.refresh(c)
        return c


_VALID_CHARACTER_DATA = {
    "name": "Brekk Stonefist",
    "race": "Ork",
    "discipline": "Warrior",
    "circle": 2,
    "attributes": {"dex": 12, "str": 16, "tou": 14, "per": 9, "wil": 10, "cha": 8},
    "derived_stats": {},
    "talents": [{"name": "Melee Weapons", "circle": 1, "rank": 4}],
    "skills": [{"name": "Climbing", "rank": 2}],
    "equipment": [{"name": "Battle Axe", "type": "weapon", "notes": "Well-worn"}],
    "background": "Raised in a warclan near Throal. Sole survivor of a horror attack.",
    "personality": "Gruff and direct. Deeply loyal to companions.",
    "goals": "Avenge his fallen clanmates.",
    "relationships": [{"name": "Sera Dawntide", "nature": "traveling companion", "notes": "Reluctant trust"}],
    "physical_description": "Tall ork with heavy scars across his left forearm.",
}


@pytest.mark.asyncio
async def test_character_creation_saves_all_fields(
    backend: SQLiteBackend, campaign: Campaign
) -> None:
    """Scenario 1: all character fields are persisted to the DB."""
    result = validate_character(_VALID_CHARACTER_DATA)
    assert result.valid, f"Validation failed: {result.errors}"

    async with await backend.get_session() as session:
        char = Character(
            id=uuid.uuid4(),
            campaign_id=campaign.id,
            player_display_name="TestPlayer",
            **_VALID_CHARACTER_DATA,
        )
        session.add(char)
        await session.commit()

        # Reload from DB
        row = await session.execute(select(Character).where(Character.id == char.id))
        saved = row.scalar_one()

        assert saved.name == "Brekk Stonefist"
        assert saved.race == "Ork"
        assert saved.discipline == "Warrior"
        assert saved.circle == 2
        assert saved.background == _VALID_CHARACTER_DATA["background"]
        assert saved.personality == _VALID_CHARACTER_DATA["personality"]
        assert saved.goals == _VALID_CHARACTER_DATA["goals"]
        assert saved.physical_description == _VALID_CHARACTER_DATA["physical_description"]
        assert len(saved.talents) == 1
        assert len(saved.skills) == 1
        assert len(saved.equipment) == 1
        assert len(saved.relationships) == 1


@pytest.mark.asyncio
async def test_character_sheet_schema_completeness(
    backend: SQLiteBackend, campaign: Campaign
) -> None:
    """Scenario 3: CharacterSchema correctly reflects all saved data."""
    async with await backend.get_session() as session:
        char = Character(
            id=uuid.uuid4(),
            campaign_id=campaign.id,
            player_display_name="TestPlayer",
            **_VALID_CHARACTER_DATA,
        )
        session.add(char)
        await session.commit()
        await session.refresh(char)

        schema = CharacterSchema.model_validate(char)

        assert schema.name == char.name
        assert schema.race == char.race
        assert schema.discipline == char.discipline
        assert schema.circle == char.circle
        assert schema.background == char.background
        assert schema.personality == char.personality
        assert schema.goals == char.goals
        assert schema.physical_description == char.physical_description
        assert schema.portrait_url is None
        assert len(schema.talents) == 1
        assert len(schema.skills) == 1
        assert len(schema.equipment) == 1
        assert len(schema.relationships) == 1


@pytest.mark.asyncio
async def test_character_validation_rejects_missing_required_fields() -> None:
    """Validator catches missing required fields before any DB write."""
    bad = {k: v for k, v in _VALID_CHARACTER_DATA.items() if k not in ("name", "background")}
    result = validate_character(bad)
    assert not result.valid
    assert any("name" in e for e in result.errors)
    assert any("background" in e for e in result.errors)


@pytest.mark.asyncio
async def test_character_validation_rejects_out_of_range_circle() -> None:
    bad = {**_VALID_CHARACTER_DATA, "circle": 16}
    result = validate_character(bad)
    assert not result.valid
    assert any("circle" in e for e in result.errors)


@pytest.mark.asyncio
async def test_multiple_characters_per_player(
    backend: SQLiteBackend, campaign: Campaign
) -> None:
    """A player may own multiple characters in the same campaign."""
    async with await backend.get_session() as session:
        char1 = Character(
            id=uuid.uuid4(),
            campaign_id=campaign.id,
            player_display_name="Alice",
            **_VALID_CHARACTER_DATA,
        )
        char2 = Character(
            id=uuid.uuid4(),
            campaign_id=campaign.id,
            player_display_name="Alice",
            name="Alt Character",
            race="Elf",
            discipline="Elementalist",
            circle=1,
            attributes={"dex": 10, "str": 8, "tou": 9, "per": 14, "wil": 13, "cha": 11},
            derived_stats={},
            talents=[],
            skills=[],
            equipment=[],
            background="An elven scholar from Throal.",
            personality="Curious and cautious.",
            goals="Learn all elemental secrets.",
            relationships=[],
        )
        session.add(char1)
        session.add(char2)
        await session.commit()

        rows = await session.execute(
            select(Character).where(
                Character.campaign_id == campaign.id,
                Character.player_display_name == "Alice",
            )
        )
        chars = rows.scalars().all()
        assert len(chars) == 2