"""OpenAI LLM provider using the Chat Completions API."""

from __future__ import annotations

import httpx
from core.config import settings
from core.errors import ProviderUnavailableError

from llm.interface import LLMProvider

_API_URL = "https://api.openai.com/v1/chat/completions"
_DEFAULT_MODEL = "gpt-4o-mini"


class OpenAIProvider(LLMProvider):
    def __init__(
        self,
        api_key: str | None = None,
        model: str = _DEFAULT_MODEL,
    ) -> None:
        self._api_key = api_key or settings.llm_api_key
        self._model = model

    async def generate(self, prompt: str, system: str = "") -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self._model,
            "messages": messages,
        }

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(_API_URL, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
                return str(data["choices"][0]["message"]["content"])
        except httpx.ConnectError as exc:
            raise ProviderUnavailableError("Cannot reach OpenAI API") from exc
        except httpx.HTTPStatusError as exc:
            raise ProviderUnavailableError(
                f"OpenAI API returned {exc.response.status_code}"
            ) from exc