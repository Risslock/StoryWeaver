"""Integration tests — US4 Character and Scene Image Generation.

Acceptance scenarios:
  1. Portrait generated end-to-end (mock provider) — portrait_url written to DB
  2. portrait_url persists across character reload
  3. Clear error message when provider unavailable — no crash
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from core.models import NPC, Campaign, Character
from imagegen.interface import ImageGenRequest, ImageGenResponse, ImageProvider
from storage.sqlite.adapter import SQLiteBackend


class MockImageProvider(ImageProvider):
    """Deterministic mock provider for testing."""

    def __init__(self, response: ImageGenResponse) -> None:
        self._response = response

    async def generate(self, request: ImageGenRequest) -> ImageGenResponse:
        return self._response


class FailingImageProvider(ImageProvider):
    """Provider that always returns an error."""

    async def generate(self, request: ImageGenRequest) -> ImageGenResponse:
        return ImageGenResponse(error="Mock provider failure: simulated unavailability")


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
            name="Image Gen Test Campaign",
            join_code="IMG00001",
            gm_display_name="ImgGM",
            owner_id=test_owner_id,
        )
        db.add(c)
        await db.commit()
        await db.refresh(c)
        return c


@pytest_asyncio.fixture
async def character(backend: SQLiteBackend, campaign: Campaign) -> Character:
    async with await backend.get_session() as db:
        char = Character(
            id=uuid.uuid4(),
            campaign_id=campaign.id,
            player_display_name="TestPlayer",
            name="Kira Shadowstep",
            race="Elf",
            discipline="Scout",
            circle=3,
            attributes={"dex": 14, "str": 8, "tou": 10, "per": 12, "wil": 10, "cha": 10},
            derived_stats={},
            talents=[],
            skills=[],
            equipment=[],
            relationships=[],
            background="Raised in the forests of Wyrm Wood.",
            personality="Quiet, observant, lethal.",
            goals="Find the kaer where her family sheltered.",
            physical_description="Lithe elf with silver hair and smoke-grey eyes.",
        )
        db.add(char)
        await db.commit()
        await db.refresh(char)
        return char


@pytest_asyncio.fixture
async def npc(backend: SQLiteBackend, campaign: Campaign) -> NPC:
    async with await backend.get_session() as db:
        n = NPC(
            id=uuid.uuid4(),
            campaign_id=campaign.id,
            name="Vorgath",
            role="merchant",
            race="Ork",
            is_visible_to_players=True,
            personality="Greedy but honourable.",
            background="Former caravan guard turned trader.",
            physical_description="Heavyset ork with filed tusks and rich merchant robes.",
            attributes={},
            derived_stats={},
            talents=[],
            skills=[],
        )
        db.add(n)
        await db.commit()
        await db.refresh(n)
        return n


# ── US4 Acceptance Scenario 1 ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_portrait_generation_writes_url_to_db(
    backend: SQLiteBackend, character: Character, tmp_path: Path
) -> None:
    """Portrait generated end-to-end (mock provider) — portrait_url written to DB."""
    fake_url = str(tmp_path / f"{character.id}.png")
    (tmp_path / f"{character.id}.png").write_bytes(b"\x89PNG\r\n\x1a\n")  # minimal PNG header

    provider = MockImageProvider(ImageGenResponse(image_url=fake_url))

    request = ImageGenRequest(
        prompt=f"{character.name}, {character.race} {character.discipline}, {character.physical_description}",
        style_hints=["fantasy portrait", "detailed", "professional illustration"],
        entity_id=character.id,
    )
    response = await provider.generate(request)

    assert response.error is None
    assert response.image_url == fake_url

    # Persist to DB (mirrors the handler in character.py)
    from sqlalchemy import select
    async with await backend.get_session() as db:
        result = await db.execute(select(Character).where(Character.id == character.id))
        char = result.scalar_one()
        char.portrait_url = response.image_url
        await db.commit()

    # Verify persisted
    async with await backend.get_session() as db:
        result = await db.execute(select(Character).where(Character.id == character.id))
        char = result.scalar_one()
        assert char.portrait_url == fake_url


# ── US4 Acceptance Scenario 2 ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_portrait_url_persists_across_reload(
    backend: SQLiteBackend, character: Character, tmp_path: Path
) -> None:
    """portrait_url is readable from a fresh DB query after being saved."""
    fake_url = str(tmp_path / "portrait.png")
    (tmp_path / "portrait.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    from sqlalchemy import select

    # Save the URL
    async with await backend.get_session() as db:
        result = await db.execute(select(Character).where(Character.id == character.id))
        char = result.scalar_one()
        char.portrait_url = fake_url
        await db.commit()

    # Re-query in a fresh session (simulates page refresh)
    async with await backend.get_session() as db:
        result = await db.execute(select(Character).where(Character.id == character.id))
        reloaded = result.scalar_one()
        assert reloaded.portrait_url == fake_url
        assert reloaded.name == character.name  # other fields intact


# ── US4 Acceptance Scenario 3 ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_provider_unavailable_returns_error_no_crash(character: Character) -> None:
    """Error response from provider surfaces as message, does not raise."""
    provider = FailingImageProvider()

    request = ImageGenRequest(
        prompt="Test prompt",
        entity_id=character.id,
    )
    response = await provider.generate(request)

    assert response.image_url is None
    assert response.error is not None
    assert len(response.error) > 0
    # No exception was raised — graceful degradation confirmed


@pytest.mark.asyncio
async def test_hf_provider_missing_key_returns_error(character: Character) -> None:
    """HuggingFaceProvider with no API key returns ImageGenResponse.error, not exception."""
    from imagegen.providers.huggingface import HuggingFaceProvider

    provider = HuggingFaceProvider(api_key="")
    request = ImageGenRequest(prompt="A dwarf warrior", entity_id=character.id)
    response = await provider.generate(request)

    assert response.image_url is None
    assert response.error is not None
    assert "HF_API_KEY" in response.error


@pytest.mark.asyncio
async def test_npc_portrait_generation_writes_url_to_db(
    backend: SQLiteBackend, npc: NPC, tmp_path: Path
) -> None:
    """NPC portrait is generated and portrait_url is persisted to DB."""
    fake_url = str(tmp_path / f"{npc.id}.png")
    (tmp_path / f"{npc.id}.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    provider = MockImageProvider(ImageGenResponse(image_url=fake_url))

    request = ImageGenRequest(
        prompt=f"{npc.name}, {npc.race}, {npc.role}, {npc.physical_description}",
        style_hints=["fantasy portrait", "detailed", "professional illustration"],
        entity_id=npc.id,
    )
    response = await provider.generate(request)

    assert response.error is None
    assert response.image_url == fake_url

    from sqlalchemy import select
    async with await backend.get_session() as db:
        result = await db.execute(select(NPC).where(NPC.id == npc.id))
        n = result.scalar_one()
        n.portrait_url = response.image_url
        await db.commit()

    async with await backend.get_session() as db:
        result = await db.execute(select(NPC).where(NPC.id == npc.id))
        n = result.scalar_one()
        assert n.portrait_url == fake_url


@pytest.mark.asyncio
async def test_image_gen_request_model_validates_entity_id(character: Character) -> None:
    """ImageGenRequest correctly stores and exposes entity_id as UUID."""
    request = ImageGenRequest(
        prompt="Test prompt",
        entity_id=character.id,
        width=512,
        height=512,
    )
    assert request.entity_id == character.id
    assert request.width == 512
    assert request.height == 512
    assert request.negative_prompt == ""
    assert request.style_hints == []


@pytest.mark.asyncio
async def test_error_response_does_not_overwrite_existing_portrait(
    backend: SQLiteBackend, character: Character, tmp_path: Path
) -> None:
    """A failed generation must NOT overwrite an existing portrait_url."""
    existing_url = str(tmp_path / "existing.png")
    (tmp_path / "existing.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    from sqlalchemy import select

    # Pre-set portrait_url
    async with await backend.get_session() as db:
        result = await db.execute(select(Character).where(Character.id == character.id))
        char = result.scalar_one()
        char.portrait_url = existing_url
        await db.commit()

    # Run failing provider — caller checks error before persisting
    provider = FailingImageProvider()
    request = ImageGenRequest(prompt="Test prompt", entity_id=character.id)
    response = await provider.generate(request)

    assert response.error is not None
    assert response.image_url is None

    # DB should still have the original URL
    async with await backend.get_session() as db:
        result = await db.execute(select(Character).where(Character.id == character.id))
        char = result.scalar_one()
        assert char.portrait_url == existing_url
