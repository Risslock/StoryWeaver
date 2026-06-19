"""HuggingFace Inference API LLM provider (free-tier serverless endpoints)."""

from __future__ import annotations

import httpx
from core.config import settings
from core.errors import ProviderUnavailableError

from llm.interface import LLMProvider

_HF_INFERENCE_BASE = "https://api-inference.huggingface.co/models"


class HuggingFaceLLMProvider(LLMProvider):
    """LLM provider using HuggingFace serverless Inference API.

    Uses the text-generation endpoint with chat-template formatting so
    instruction-tuned models (Mistral, Llama, Qwen) respond correctly.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        self._api_key = api_key or settings.hf_api_key
        self._model = model or settings.hf_llm_model

    @property
    def _endpoint(self) -> str:
        return f"{_HF_INFERENCE_BASE}/{self._model}/v1/chat/completions"

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
            "max_tokens": 1024,
            "stream": False,
        }

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(self._endpoint, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
                return str(data["choices"][0]["message"]["content"])
        except httpx.ConnectError as exc:
            raise ProviderUnavailableError(
                f"Cannot reach HuggingFace Inference API for model {self._model}"
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise ProviderUnavailableError(
                f"HuggingFace API returned {exc.response.status_code}"
            ) from exc