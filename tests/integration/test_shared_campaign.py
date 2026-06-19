"""Integration tests — US5 Shared Campaign Session.

Acceptance scenarios:
  1. GM creates private NPC note → Player cannot see it
  2. GM logs public event → Player refresh sees it in story history
  3. Concurrent GM + Player actions produce no data corruption
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import date
from pathlib import Path

import pytest
import pytest_asyncio
from core.models import NPC, Campaign
from core.schemas import PlayerNPCSchema
from sqlalchemy import select
from storage.sqlite.adapter import SQLiteBackend
from story.history import create_event, list_events
from story.session import create_session


@pytest_asyncio.fixture
async def backend() -> SQLiteBackend:
    db = SQLiteBackend("sqlite+aiosqlite:///:memory:")
    await db.initialize_db()
    return db


@pytest_asyncio.fixture
async def campaign(backend: SQLiteBackend) -> Campaign:
    async with await backend.get_session() as db:
        c = Campaign(
            id=uuid.uuid4(),
            name="Shared Campaign Test",
            join_code="SHARE001",
            gm_display_name="SharedGM",
        )
        db.add(c)
        await db.commit()
        await db.refresh(c)
        return c


# ── US5 Acceptance Scenario 2 ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_gm_public_event_visible_to_player_after_log(
    backend: SQLiteBackend, campaign: Campaign
) -> None:
    """GM logs a public event; Player's next read (simulating a refresh) sees it."""
    async with await backend.get_session() as db:
        game_session = await create_session(
            db,
            campaign_id=campaign.id,
            title="Session 1: The Shared Moment",
            date_played=date(2026, 6, 1),
        )
        await create_event(
            db,
            campaign_id=campaign.id,
            event_type="dialogue",
            content="The party discovered the ancient kaer entrance.",
            is_public=True,
            session_id=game_session.id,
        )

    # Simulate Player refresh: new session (new connection) re-queries history
    async with await backend.get_session() as player_db:
        player_events = await list_events(player_db, campaign.id, role="player")

    contents = [e.content for e in player_events]
    assert any("kaer entrance" in c for c in contents), (
        "Player should see the public event after GM logs it (US5 scenario 2)"
    )


# ── US5 Acceptance Scenario 1 ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_gm_private_npc_note_not_visible_to_player(
    backend: SQLiteBackend, campaign: Campaign
) -> None:
    """GM creates an NPC with gm_notes and a private event; Player sees neither."""
    async with await backend.get_session() as db:
        game_session = await create_session(
            db,
            campaign_id=campaign.id,
            title="Session 1: Hidden Threats",
            date_played=date(2026, 6, 1),
        )
        npc = NPC(
            id=uuid.uuid4(),
            campaign_id=campaign.id,
            name="Lord Varek",
            role="villain",
            personality="Charismatic and treacherous.",
            background="A corrupted t'skrang noble.",
            gm_notes="Secret: Varek serves a Horror. Reveal in session 4.",
            is_visible_to_players=True,
        )
        db.add(npc)
        # Private event: Player must not see this
        await create_event(
            db,
            campaign_id=campaign.id,
            event_type="npc_state_change",
            content="Private: Varek has activated his Horror-mark.",
            is_public=False,
            session_id=game_session.id,
        )
        # Public event: Player can see this
        await create_event(
            db,
            campaign_id=campaign.id,
            event_type="dialogue",
            content="Lord Varek greeted the party at the feast.",
            is_public=True,
            session_id=game_session.id,
        )
        await db.commit()

    # Player NPC query: gm_notes must not be exposed via PlayerNPCSchema
    async with await backend.get_session() as player_db:
        result = await player_db.execute(
            select(NPC).where(
                NPC.campaign_id == campaign.id,
                NPC.is_visible_to_players.is_(True),
            )
        )
        visible_npcs = list(result.scalars().all())

    assert len(visible_npcs) == 1
    player_npc = PlayerNPCSchema.model_validate(visible_npcs[0])
    assert not hasattr(player_npc, "gm_notes"), (
        "PlayerNPCSchema must not expose gm_notes (US5 scenario 1)"
    )
    assert player_npc.name == "Lord Varek"

    # Player history query: private event must be absent
    async with await backend.get_session() as player_db:
        player_events = await list_events(player_db, campaign.id, role="player")

    contents = [e.content for e in player_events]
    assert not any("Horror-mark" in c for c in contents), (
        "Private NPC-state event must not appear in Player history (US5 scenario 1)"
    )
    assert any("feast" in c for c in contents), (
        "Public event must remain visible to Player after GM adds a private event"
    )


# ── US5 Acceptance Scenario 3 ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_concurrent_gm_player_no_data_corruption(tmp_path: Path) -> None:
    """Concurrent GM writes and Player reads produce no data corruption (US5 scenario 3).

    Uses a file-based SQLite database so WAL mode is exercised across two separate
    engine connections, accurately simulating two independent users hitting the same DB.
    """
    db_url = f"sqlite+aiosqlite:///{(tmp_path / 'shared.db').as_posix()}"

    gm_backend = SQLiteBackend(db_url)
    player_backend = SQLiteBackend(db_url)
    await gm_backend.initialize_db()

    # Seed: campaign and session via the GM backend
    async with await gm_backend.get_session() as db:
        camp = Campaign(
            id=uuid.uuid4(),
            name="Concurrent Campaign",
            join_code="CONC0001",
            gm_display_name="ConcurrentGM",
        )
        db.add(camp)
        await db.commit()
        await db.refresh(camp)
        campaign_id = camp.id

    async with await gm_backend.get_session() as db:
        game_session = await create_session(
            db,
            campaign_id=campaign_id,
            title="Session 1: Chaos",
            date_played=date(2026, 6, 1),
        )
        session_id = game_session.id

    async def gm_writes_events() -> int:
        """GM logs 5 public events, each committed individually."""
        async with await gm_backend.get_session() as db:
            for i in range(5):
                await create_event(
                    db,
                    campaign_id=campaign_id,
                    event_type="dialogue",
                    content=f"GM event {i}: narrative content.",
                    is_public=True,
                    session_id=session_id,
                )
        return 5

    async def player_reads_history() -> list[int]:
        """Player reads history 3 times while GM is writing."""
        counts: list[int] = []
        for _ in range(3):
            async with await player_backend.get_session() as db:
                events = await list_events(db, campaign_id, role="player")
                counts.append(len(events))
        return counts

    # Run GM writes and Player reads concurrently
    gm_count, _ = await asyncio.gather(
        gm_writes_events(),
        player_reads_history(),
    )

    assert gm_count == 5

    # After all concurrent operations: every event must be present and content intact
    async with await gm_backend.get_session() as db:
        all_events = await list_events(db, campaign_id, role="gm")
        player_events_final = await list_events(db, campaign_id, role="player")

    assert len(all_events) == 5, (
        f"Expected 5 events after concurrent writes; got {len(all_events)} — "
        "possible data loss under concurrent access"
    )
    assert len(player_events_final) == 5, (
        "Player should see all 5 public events after concurrent operations resolve"
    )

    final_contents = [e.content for e in all_events]
    for i in range(5):
        assert any(f"GM event {i}" in c for c in final_contents), (
            f"GM event {i} missing after concurrent write — data loss detected"
        )