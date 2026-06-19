"""Ollama LLM provider using the OpenAI-compatible REST API."""

from __future__ import annotations

import httpx
from core.config import settings
from core.errors import ProviderUnavailableError

from llm.interface import LLMProvider


class OllamaProvider(LLMProvider):
    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        self._base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self._model = model or settings.ollama_model

    async def generate(self, prompt: str, system: str = "") -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {"model": self._model, "messages": messages, "stream": False}

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self._base_url}/v1/chat/completions",
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
                return str(data["choices"][0]["message"]["content"])
        except httpx.ConnectError as exc:
            raise ProviderUnavailableError(f"Cannot reach Ollama at {self._base_url}") from exc
        except httpx.HTTPStatusError as exc:
            raise ProviderUnavailableError(f"Ollama returned {exc.response.status_code}") from exc

    async def health_check(self) -> bool:
        """Return True if Ollama is reachable, False otherwise."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self._base_url}/api/tags")
                return resp.status_code == 200
        except Exception:
            return False