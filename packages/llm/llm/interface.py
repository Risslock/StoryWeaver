"""LLMProvider ABC — all LLM adapters implement this interface."""

from __future__ import annotations

from abc import ABC, abstractmethod


class LLMProvider(ABC):
    @abstractmethod
    async def generate(self, prompt: str, system: str = "") -> str:
        """Generate a response from the LLM.

        Raises:
            ProviderUnavailableError: when the provider cannot be reached.
        """