"""Unit tests for feature 015: greedy-decoding temperature passthrough (FR-018)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from llm.providers.ollama import OllamaProvider
from pydantic import BaseModel


class _Echo(BaseModel):
    value: str


def _mock_response(json_body: dict) -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json = MagicMock(return_value=json_body)
    return resp


def _patched_client(captured_payloads: list[dict], json_body: dict):
    """Patch httpx.AsyncClient so client.post(...) records its payload and returns json_body."""
    mock_client = AsyncMock()

    async def _post(url: str, json: dict) -> MagicMock:
        captured_payloads.append(json)
        return _mock_response(json_body)

    mock_client.post = AsyncMock(side_effect=_post)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return patch("httpx.AsyncClient", return_value=mock_client)


@pytest.mark.asyncio
async def test_generate_sends_temperature_default_zero() -> None:
    """OllamaProvider.generate() includes temperature=0.0 by default (greedy decoding)."""
    captured: list[dict] = []
    body = {"choices": [{"message": {"content": "hello"}}]}
    with _patched_client(captured, body):
        provider = OllamaProvider(model="llama3.1")
        result = await provider.generate("prompt")

    assert result == "hello"
    assert len(captured) == 1
    assert captured[0]["temperature"] == 0.0


@pytest.mark.asyncio
async def test_generate_structured_sends_temperature_default_zero() -> None:
    """OllamaProvider.generate_structured() includes temperature=0.0 alongside response_format."""
    captured: list[dict] = []
    body = {"choices": [{"message": {"content": '{"value": "ok"}'}}]}
    with _patched_client(captured, body):
        provider = OllamaProvider(model="llama3.1")
        result = await provider.generate_structured("prompt", _Echo)

    assert result.value == "ok"
    assert len(captured) == 1
    assert captured[0]["temperature"] == 0.0
    assert captured[0]["response_format"] == {"type": "json_object"}


@pytest.mark.asyncio
async def test_generate_temperature_follows_settings_override() -> None:
    """Changing settings.knowledge_eval_temperature changes the payload sent."""
    from core.config import settings as _cfg

    captured: list[dict] = []
    body = {"choices": [{"message": {"content": "hello"}}]}
    original = _cfg.knowledge_eval_temperature
    try:
        _cfg.knowledge_eval_temperature = 0.7
        with _patched_client(captured, body):
            provider = OllamaProvider(model="llama3.1")
            await provider.generate("prompt")
        assert captured[0]["temperature"] == 0.7
    finally:
        _cfg.knowledge_eval_temperature = original
