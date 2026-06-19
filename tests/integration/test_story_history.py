"""Integration tests — US3 Campaign Story History.

Acceptance scenarios:
  1. GM logs event → Player refresh sees it (is_public=True)
  2. Events appear in chronological order (session_number, event_order)
  SC-008: history load < 5 seconds for 5+ sessions / 20+ events
"""

from __future__ import annotations

import time
import uuid
from datetime import date

import pytest
import pytest_asyncio
from core.models import Campaign
from storage.sqlite.adapter import SQLiteBackend
from story.history import create_event, list_events
from story.session import create_session, get_session, list_sessions


@pytest_asyncio.fixture
async def backend() -> SQLiteBackend:
    db = SQLiteBackend("sqlite+aiosqlite:///:memory:")
    await db.initialize_db()
    return db


@pytest_asyncio.fixture
async def campaign(backend: SQLiteBackend, test_owner_id: uuid.UUID) -> Campaign:
    async with await backend.get_session() as db:
        c = Campaign(
            id=uuid.uuid4(),
            name="Story History Test Campaign",
            join_code="HIST0001",
            gm_display_name="HistoryGM",
            owner_id=test_owner_id,
        )
        db.add(c)
        await db.commit()
        await db.refresh(c)
        return c


# ── US3 Acceptance Scenario 1 ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_gm_event_visible_to_player_after_log(
    backend: SQLiteBackend, campaign: Campaign
) -> None:
    """GM logs a public event; player role query includes it immediately."""
    async with await backend.get_session() as db:
        session = await create_session(
            db,
            campaign_id=campaign.id,
            title="Session 1: The Arrival",
            date_played=date(2026, 1, 10),
        )
        await create_event(
            db,
            campaign_id=campaign.id,
            event_type="dialogue",
            content="The party arrived at the city gates and met the guard captain.",
            is_public=True,
            session_id=session.id,
        )

    async with await backend.get_session() as db:
        player_events = await list_events(db, campaign.id, role="player")

    contents = [e.content for e in player_events]
    assert any("city gates" in c for c in contents), (
        "Player should see the public event after GM logs it"
    )


@pytest.mark.asyncio
async def test_gm_private_event_not_visible_to_player(
    backend: SQLiteBackend, campaign: Campaign
) -> None:
    """GM-only event (is_public=False) is absent from player role query."""
    async with await backend.get_session() as db:
        session = await create_session(
            db,
            campaign_id=campaign.id,
            title="Session 1: Secrets",
            date_played=date(2026, 1, 10),
        )
        await create_event(
            db,
            campaign_id=campaign.id,
            event_type="world_change",
            content="Private: the guard captain is a Brotherhood spy.",
            is_public=False,
            session_id=session.id,
        )
        await create_event(
            db,
            campaign_id=campaign.id,
            event_type="dialogue",
            content="Public: the party learned about the missing caravan.",
            is_public=True,
            session_id=session.id,
        )

    async with await backend.get_session() as db:
        player_events = await list_events(db, campaign.id, role="player")
        gm_events = await list_events(db, campaign.id, role="gm")

    player_contents = [e.content for e in player_events]
    gm_contents = [e.content for e in gm_events]

    assert not any("Brotherhood spy" in c for c in player_contents), (
        "Private event must not appear in player query"
    )
    assert any("missing caravan" in c for c in player_contents), (
        "Public event must appear in player query"
    )
    assert any("Brotherhood spy" in c for c in gm_contents), (
        "Private event must appear in GM query"
    )


# ── US3 Acceptance Scenario 2 ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_events_in_chronological_order(
    backend: SQLiteBackend, campaign: Campaign
) -> None:
    """Events are ordered by (session_number asc, event_order asc)."""
    async with await backend.get_session() as db:
        s1 = await create_session(
            db,
            campaign_id=campaign.id,
            title="Session 1: Beginning",
            date_played=date(2026, 1, 5),
        )
        s2 = await create_session(
            db,
            campaign_id=campaign.id,
            title="Session 2: Middle",
            date_played=date(2026, 1, 12),
        )

        # Insert session 2 event first to ensure ordering is not insertion-based
        await create_event(
            db,
            campaign_id=campaign.id,
            event_type="combat_outcome",
            content="S2-E0: Party defeated the bandits.",
            is_public=True,
            session_id=s2.id,
        )
        await create_event(
            db,
            campaign_id=campaign.id,
            event_type="dialogue",
            content="S1-E0: Party received the mission.",
            is_public=True,
            session_id=s1.id,
        )
        await create_event(
            db,
            campaign_id=campaign.id,
            event_type="decision",
            content="S1-E1: Party chose the mountain route.",
            is_public=True,
            session_id=s1.id,
        )

    async with await backend.get_session() as db:
        events = await list_events(db, campaign.id, role="gm")

    contents = [e.content for e in events]
    assert len(contents) == 3

    s1_e0_idx = next(i for i, c in enumerate(contents) if "S1-E0" in c)
    s1_e1_idx = next(i for i, c in enumerate(contents) if "S1-E1" in c)
    s2_e0_idx = next(i for i, c in enumerate(contents) if "S2-E0" in c)

    assert s1_e0_idx < s1_e1_idx < s2_e0_idx, (
        "Events must appear in (session_number, event_order) order"
    )


@pytest.mark.asyncio
async def test_session_filter_isolates_single_session(
    backend: SQLiteBackend, campaign: Campaign
) -> None:
    """Filtering list_events by session_id returns only events from that session."""
    async with await backend.get_session() as db:
        s1 = await create_session(
            db,
            campaign_id=campaign.id,
            title="Session 1",
            date_played=date(2026, 1, 5),
        )
        s2 = await create_session(
            db,
            campaign_id=campaign.id,
            title="Session 2",
            date_played=date(2026, 1, 12),
        )
        await create_event(
            db,
            campaign_id=campaign.id,
            event_type="dialogue",
            content="Only in session 1.",
            is_public=True,
            session_id=s1.id,
        )
        await create_event(
            db,
            campaign_id=campaign.id,
            event_type="dialogue",
            content="Only in session 2.",
            is_public=True,
            session_id=s2.id,
        )

    async with await backend.get_session() as db:
        s1_events = await list_events(db, campaign.id, role="gm", session_id=s1.id)

    assert len(s1_events) == 1
    assert "Only in session 1." in s1_events[0].content


@pytest.mark.asyncio
async def test_session_crud_list_and_get(
    backend: SQLiteBackend, campaign: Campaign
) -> None:
    """create_session auto-increments session_number; list_sessions and get_session work."""
    async with await backend.get_session() as db:
        s1 = await create_session(db, campaign.id, "Session One", date(2026, 2, 1))
        await create_session(db, campaign.id, "Session Two", date(2026, 2, 8))

    async with await backend.get_session() as db:
        all_sessions = await list_sessions(db, campaign.id)
        fetched = await get_session(db, s1.id)

    assert [s.session_number for s in all_sessions] == [1, 2]
    assert fetched is not None
    assert fetched.title == "Session One"


# ── SC-008: Load time < 5 seconds for 5+ sessions / 20+ events ───────────────

@pytest.mark.asyncio
async def test_history_load_time(
    backend: SQLiteBackend, campaign: Campaign
) -> None:
    """History load must complete in < 5 seconds for 5+ sessions / 20+ public events."""
    async with await backend.get_session() as db:
        sessions = []
        for i in range(1, 6):
            s = await create_session(
                db,
                campaign_id=campaign.id,
                title=f"Session {i}: Chapter {i}",
                date_played=date(2026, 1, i),
            )
            sessions.append(s)

        # 4 events per session = 20 total
        for s in sessions:
            for j in range(4):
                await create_event(
                    db,
                    campaign_id=campaign.id,
                    event_type="dialogue",
                    content=f"Event {j} for session {s.session_number}: some narrative content.",
                    is_public=True,
                    session_id=s.id,
                )

    async with await backend.get_session() as db:
        start = time.monotonic()
        events = await list_events(db, campaign.id, role="player")
        elapsed = time.monotonic() - start

    assert len(events) == 20, f"Expected 20 events, got {len(events)}"
    assert elapsed < 5.0, (
        f"SC-008 violation: history load took {elapsed:.3f}s (limit: 5.0s)"
    )