"""Integration tests — US2 role access scenarios.

- NPC hidden from players when is_visible_to_players=False
- GM toggles visibility; player sees NPC via PlayerNPCSchema (no gm_notes)
- GM-only StoryEvent absent from player history
- gm_notes never returned in player-role queries
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from core.models import NPC, Campaign, Character, StoryEvent
from core.schemas import NPCSchema, PlayerNPCSchema
from sqlalchemy import select
from storage.sqlite.adapter import SQLiteBackend


@pytest_asyncio.fixture
async def backend() -> SQLiteBackend:
    db = SQLiteBackend("sqlite+aiosqlite:///:memory:")
    await db.initialize_db()
    return db


@pytest_asyncio.fixture
async def campaign(backend: SQLiteBackend, test_owner_id: uuid.UUID) -> Campaign:
    async with await backend.get_session() as session:
        c = Campaign(
            id=uuid.uuid4(),
            name="Role Access Test Campaign",
            join_code="RATEST01",
            gm_display_name="TestGM",
            owner_id=test_owner_id,
        )
        session.add(c)
        await session.commit()
        await session.refresh(c)
        return c


@pytest_asyncio.fixture
async def hidden_npc(backend: SQLiteBackend, campaign: Campaign) -> NPC:
    async with await backend.get_session() as session:
        npc = NPC(
            id=uuid.uuid4(),
            campaign_id=campaign.id,
            name="Shadow Informant",
            role="villain",
            race="Troll",
            personality="Cold and calculating.",
            background="Spy for a horror cult.",
            gm_notes="Secret: he is working for the Blood Elf faction.",
            is_visible_to_players=False,
        )
        session.add(npc)
        await session.commit()
        await session.refresh(npc)
        return npc


@pytest_asyncio.fixture
async def visible_npc(backend: SQLiteBackend, campaign: Campaign) -> NPC:
    async with await backend.get_session() as session:
        npc = NPC(
            id=uuid.uuid4(),
            campaign_id=campaign.id,
            name="Friendly Merchant",
            role="merchant",
            race="Dwarf",
            personality="Cheerful and talkative.",
            background="Runs a shop in Throal.",
            gm_notes="He owes the thieves guild a substantial debt.",
            is_visible_to_players=True,
        )
        session.add(npc)
        await session.commit()
        await session.refresh(npc)
        return npc


@pytest.mark.asyncio
async def test_hidden_npc_not_in_player_query(
    backend: SQLiteBackend, campaign: Campaign, hidden_npc: NPC
) -> None:
    """NPC with is_visible_to_players=False must not appear in player-role queries."""
    async with await backend.get_session() as session:
        result = await session.execute(
            select(NPC).where(
                NPC.campaign_id == campaign.id,
                NPC.is_visible_to_players.is_(True),
            )
        )
        player_visible = list(result.scalars().all())

    ids = [n.id for n in player_visible]
    assert hidden_npc.id not in ids


@pytest.mark.asyncio
async def test_gm_toggle_reveals_npc_to_players(
    backend: SQLiteBackend, campaign: Campaign, hidden_npc: NPC
) -> None:
    """GM toggles NPC visibility; player query now includes the NPC via PlayerNPCSchema."""
    # GM toggles
    async with await backend.get_session() as session:
        result = await session.execute(select(NPC).where(NPC.id == hidden_npc.id))
        npc = result.scalar_one()
        npc.is_visible_to_players = True
        await session.commit()

    # Player-role query now sees it
    async with await backend.get_session() as session:
        result = await session.execute(
            select(NPC).where(
                NPC.campaign_id == campaign.id,
                NPC.is_visible_to_players.is_(True),
            )
        )
        player_visible = list(result.scalars().all())

    assert any(n.id == hidden_npc.id for n in player_visible)


@pytest.mark.asyncio
async def test_player_npc_schema_excludes_gm_notes(
    backend: SQLiteBackend, campaign: Campaign, visible_npc: NPC
) -> None:
    """PlayerNPCSchema must not expose gm_notes or background fields."""
    async with await backend.get_session() as session:
        result = await session.execute(select(NPC).where(NPC.id == visible_npc.id))
        npc = result.scalar_one()

    schema = PlayerNPCSchema.model_validate(npc)

    # PlayerNPCSchema must not have gm_notes
    assert not hasattr(schema, "gm_notes")
    # background also excluded from PlayerNPCSchema
    assert not hasattr(schema, "background")
    # Included fields are present
    assert schema.name == visible_npc.name
    assert schema.role == visible_npc.role
    assert schema.race == visible_npc.race
    assert schema.personality == visible_npc.personality


@pytest.mark.asyncio
async def test_gm_notes_present_in_full_npc_schema(
    backend: SQLiteBackend, campaign: Campaign, visible_npc: NPC
) -> None:
    """Full NPCSchema (GM role) includes gm_notes."""
    async with await backend.get_session() as session:
        result = await session.execute(select(NPC).where(NPC.id == visible_npc.id))
        npc = result.scalar_one()

    schema = NPCSchema.model_validate(npc)
    assert schema.gm_notes == visible_npc.gm_notes


@pytest.mark.asyncio
async def test_private_story_event_absent_from_player_query(
    backend: SQLiteBackend, campaign: Campaign
) -> None:
    """GM-only StoryEvent (is_public=False) must not appear in player-role history queries."""
    async with await backend.get_session() as session:
        private_event = StoryEvent(
            campaign_id=campaign.id,
            event_type="world_change",
            content="Secret: the lich is controlling the mayor.",
            participants=[],
            is_public=False,
            event_order=0,
        )
        public_event = StoryEvent(
            campaign_id=campaign.id,
            event_type="dialogue",
            content="The party met the mayor at the town hall.",
            participants=[],
            is_public=True,
            event_order=1,
        )
        session.add(private_event)
        session.add(public_event)
        await session.commit()

        # Player-role query: only public events
        result = await session.execute(
            select(StoryEvent).where(
                StoryEvent.campaign_id == campaign.id,
                StoryEvent.is_public.is_(True),
            )
        )
        player_events = list(result.scalars().all())

    contents = [e.content for e in player_events]
    assert any("mayor at the town hall" in c for c in contents)
    assert not any("lich is controlling" in c for c in contents)


@pytest.mark.asyncio
async def test_gm_query_includes_private_events(
    backend: SQLiteBackend, campaign: Campaign
) -> None:
    """GM-role query returns all events including is_public=False."""
    async with await backend.get_session() as session:
        private_event = StoryEvent(
            campaign_id=campaign.id,
            event_type="world_change",
            content="GM private note about the dungeon layout.",
            participants=[],
            is_public=False,
            event_order=0,
        )
        session.add(private_event)
        await session.commit()

        # GM query: all events
        result = await session.execute(
            select(StoryEvent).where(StoryEvent.campaign_id == campaign.id)
        )
        gm_events = list(result.scalars().all())

    assert any("GM private note" in e.content for e in gm_events)


@pytest.mark.asyncio
async def test_player_agent_access_denied_for_other_player_character(
    backend: SQLiteBackend, campaign: Campaign
) -> None:
    """Player agent raises AccessDeniedError when accessing another player's character."""
    from agents.player_agent.player_agent import (
        GetCharacterInput,
        build_player_agent_tools,
    )
    from core.errors import AccessDeniedError

    async with await backend.get_session() as session:
        char = Character(
            id=uuid.uuid4(),
            campaign_id=campaign.id,
            player_display_name="Alice",
            name="Alice's Hero",
            race="Elf",
            discipline="Elementalist",
            circle=1,
            attributes={"dex": 10, "str": 8, "tou": 9, "per": 14, "wil": 13, "cha": 11},
            derived_stats={},
            talents=[],
            skills=[],
            equipment=[],
            background="Elven scholar.",
            personality="Curious.",
            relationships=[],
        )
        session.add(char)
        await session.commit()

        # Bob attempts to access Alice's character
        tools = build_player_agent_tools("Bob", campaign.id, session)
        with pytest.raises(AccessDeniedError):
            await tools["get_character_sheet"](GetCharacterInput(character_id=char.id))


@pytest.mark.asyncio
async def test_player_agent_allows_own_character(
    backend: SQLiteBackend, campaign: Campaign
) -> None:
    """Player agent returns character sheet when the player owns the character."""
    from agents.player_agent.player_agent import (
        GetCharacterInput,
        build_player_agent_tools,
    )

    async with await backend.get_session() as session:
        char = Character(
            id=uuid.uuid4(),
            campaign_id=campaign.id,
            player_display_name="Alice",
            name="Alice's Hero",
            race="Elf",
            discipline="Elementalist",
            circle=1,
            attributes={"dex": 10, "str": 8, "tou": 9, "per": 14, "wil": 13, "cha": 11},
            derived_stats={},
            talents=[],
            skills=[],
            equipment=[],
            background="Elven scholar.",
            personality="Curious.",
            relationships=[],
        )
        session.add(char)
        await session.commit()

        tools = build_player_agent_tools("Alice", campaign.id, session)
        result = await tools["get_character_sheet"](GetCharacterInput(character_id=char.id))
        assert result.name == "Alice's Hero"
        assert result.player_display_name == "Alice"