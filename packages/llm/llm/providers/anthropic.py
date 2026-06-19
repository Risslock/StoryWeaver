"""Anthropic Claude LLM provider using the Messages API."""

from __future__ import annotations

import httpx
from core.config import settings
from core.errors import ProviderUnavailableError

from llm.interface import LLMProvider

_API_URL = "https://api.anthropic.com/v1/messages"
_DEFAULT_MODEL = "claude-haiku-4-5-20251001"
_ANTHROPIC_VERSION = "2023-06-01"


class AnthropicProvider(LLMProvider):
    def __init__(
        self,
        api_key: str | None = None,
        model: str = _DEFAULT_MODEL,
    ) -> None:
        self._api_key = api_key or settings.llm_api_key
        self._model = model

    async def generate(self, prompt: str, system: str = "") -> str:
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": _ANTHROPIC_VERSION,
            "content-type": "application/json",
        }
        payload: dict[object, object] = {
            "model": self._model,
            "max_tokens": 1024,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            payload["system"] = system

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(_API_URL, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
                return str(data["content"][0]["text"])
        except httpx.ConnectError as exc:
            raise ProviderUnavailableError("Cannot reach Anthropic API") from exc
        except httpx.HTTPStatusError as exc:
            raise ProviderUnavailableError(
                f"Anthropic API returned {exc.response.status_code}"
            ) from exc