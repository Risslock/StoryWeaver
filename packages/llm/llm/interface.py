"""LLMProvider ABC — all LLM adapters implement this interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMProvider(ABC):
    @abstractmethod
    async def generate(self, prompt: str, system: str = "") -> str:
        """Generate a response from the LLM.

        Raises:
            ProviderUnavailableError: when the provider cannot be reached.
        """

    async def generate_structured(
        self,
        prompt: str,
        response_type: type[T],
        system: str = "",
    ) -> T:
        """Return a Pydantic model instance parsed from the LLM response.

        Default implementation calls generate() and parses with model_validate_json().
        Providers that support native structured output (response_format) SHOULD override
        this method to constrain the model's sampler.

        Raises:
            pydantic.ValidationError: if the response cannot be parsed into response_type.
            ProviderUnavailableError: if the underlying generate() call fails.
        """
        raw = await self.generate(prompt=prompt, system=system)
        return response_type.model_validate_json(raw)


class VisionLLMProvider(ABC):
    """ABC for vision-capable LLM adapters that extract text from page images."""

    @abstractmethod
    async def extract_page(self, image_bytes: bytes, prompt: str) -> str:
        """Extract text from a rendered page image.

        Returns:
            Markdown string (never None; may be empty if the page has no text).

        Raises:
            RuntimeError: on provider call failure (HTTP error, timeout, bad response).
        """