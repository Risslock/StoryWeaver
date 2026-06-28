"""Provider factory for the judge LLM."""

from __future__ import annotations

import logging
import os

_log = logging.getLogger(__name__)

_VALID_PROVIDERS = {"ollama", "claude"}


def get_judge_provider(provider: str, model: str) -> object:
    """Return an LLMProvider for judge evaluation.

    Args:
        provider: Value of ``JUDGE_PROVIDER`` env var ("ollama" | "claude").
        model: Value of ``JUDGE_MODEL`` env var.

    Raises:
        OSError: if provider or model is blank, or provider is unrecognised.
    """
    provider = provider.strip() if provider else ""
    model = model.strip() if model else ""

    if not provider:
        _log.error("JUDGE_PROVIDER is required but not set")
        raise OSError("JUDGE_PROVIDER is required but not set")
    if not model:
        _log.error("JUDGE_MODEL is required but not set")
        raise OSError("JUDGE_MODEL is required but not set")

    if provider not in _VALID_PROVIDERS:
        _log.error(
            "JUDGE_PROVIDER=%r is not recognised; valid values: %s",
            provider,
            ", ".join(sorted(_VALID_PROVIDERS)),
        )
        raise OSError(
            f"JUDGE_PROVIDER={provider!r} is not recognised; "
            f"valid values: {', '.join(sorted(_VALID_PROVIDERS))}"
        )

    if provider == "ollama":
        from llm.providers.ollama import OllamaProvider  # type: ignore[import-untyped]

        base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
        return OllamaProvider(model=model, base_url=base_url)

    # provider == "claude"
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        _log.error("ANTHROPIC_API_KEY is required when JUDGE_PROVIDER=claude but not set")
        raise OSError(
            "ANTHROPIC_API_KEY is required when JUDGE_PROVIDER=claude but not set"
        )
    from llm.providers.anthropic import (
        AnthropicProvider,  # type: ignore[import-untyped]
    )

    return AnthropicProvider(api_key=api_key, model=model)
