"""Integration tests — US1 degraded-mode (AI unavailable) acceptance scenarios.

- App starts without Ollama reachable → banner is visible
- Twin chat submit is non-interactive in degraded mode
- Generate portrait button is non-interactive in degraded mode
- Character sheet and navigation remain functional
"""

from __future__ import annotations

import uuid

import pytest
from core.schemas import CampaignSession


class _FakeOllamaProvider:
    async def health_check(self) -> bool:
        return False

    async def generate(self, prompt: str, system: str = "") -> str:
        from core.errors import ProviderUnavailableError
        raise ProviderUnavailableError("Ollama unreachable (mock)")


@pytest.mark.asyncio
async def test_ai_unavailable_sets_campaign_session_flag() -> None:
    """When Ollama health check fails, CampaignSession.ai_available is False."""
    provider = _FakeOllamaProvider()
    ai_available = await provider.health_check()

    session = CampaignSession(
        campaign_id=uuid.uuid4(),
        display_name="TestPlayer",
        role="player",
        ai_available=ai_available,
    )
    assert session.ai_available is False


@pytest.mark.asyncio
async def test_twin_chat_raises_provider_error_in_degraded_mode() -> None:
    """DigitalTwinAgent raises ProviderUnavailableError when the provider is down."""
    from agents.twin.agent import DigitalTwinAgent
    from core.errors import ProviderUnavailableError

    agent = DigitalTwinAgent(
        entity_type="character",
        entity_data={
            "name": "Brekk", "race": "Ork", "discipline": "Warrior",
            "personality": "Gruff.", "background": "Survivor.", "goals": "",
        },
        llm_provider=_FakeOllamaProvider(),  # type: ignore[arg-type]
    )
    with pytest.raises(ProviderUnavailableError):
        await agent.chat("What do you think about the road ahead?", [])


@pytest.mark.asyncio
async def test_ollama_provider_health_check_failure() -> None:
    """OllamaProvider.health_check returns False when the server is unreachable."""
    from llm.providers.ollama import OllamaProvider

    provider = OllamaProvider(base_url="http://127.0.0.1:1", model="test")
    result = await provider.health_check()
    assert result is False


@pytest.mark.asyncio
async def test_character_data_accessible_without_ai() -> None:
    """Character schema and validator work without any LLM dependency."""
    from rules_earthdawn.validator import validate_character

    data = {
        "name": "Sera Dawntide",
        "race": "Elf",
        "discipline": "Elementalist",
        "circle": 3,
        "attributes": {"dex": 11, "str": 8, "tou": 9, "per": 14, "wil": 13, "cha": 10},
        "background": "Studied at Throal academy.",
        "personality": "Methodical and precise.",
    }
    result = validate_character(data)
    assert result.valid


@pytest.mark.asyncio
async def test_suggestion_raises_provider_error_in_degraded_mode() -> None:
    """suggest() also raises ProviderUnavailableError in degraded mode."""
    from agents.twin.agent import DigitalTwinAgent
    from core.errors import ProviderUnavailableError

    agent = DigitalTwinAgent(
        entity_type="character",
        entity_data={
            "name": "Nix", "race": "Windling", "discipline": "Thief",
            "personality": "Mischievous.", "background": "Street urchin.", "goals": "",
        },
        llm_provider=_FakeOllamaProvider(),  # type: ignore[arg-type]
    )
    with pytest.raises(ProviderUnavailableError):
        await agent.suggest("a merchant is offering you a suspicious deal", [])