"""Provider factory functions for knowledge ingestion and retrieval.

Follows the get_image_provider() pattern from packages/imagegen/imagegen/factory.py.
Validates required env vars and raises EnvironmentError (with ERROR log) if any are absent,
blank, or unrecognised — ensuring fast, clear failures rather than silent misconfiguration.
"""

from __future__ import annotations

import logging

from core.config import settings as _cfg

_log = logging.getLogger(__name__)

_VALID_PROVIDERS = {"ollama", "huggingface"}


def get_knowledge_enrich_provider(model: str) -> object:
    """Return the LLM provider for chunk enrichment and query expansion/reranking.

    Reads:
        KNOWLEDGE_ENRICH_PROVIDER — required; "ollama" | "huggingface"
        HF_API_KEY                — required if KNOWLEDGE_ENRICH_PROVIDER=huggingface
        OLLAMA_BASE_URL           — used if KNOWLEDGE_ENRICH_PROVIDER=ollama

    Args:
        model: model name (caller reads KNOWLEDGE_ENRICH_MODEL)

    Raises:
        EnvironmentError: if any required env var is absent, blank, or unrecognised
    """
    if not model or not model.strip():
        _log.error("KNOWLEDGE_ENRICH_MODEL is required but not set")
        raise EnvironmentError("KNOWLEDGE_ENRICH_MODEL is required but not set")

    provider_name = _cfg.knowledge_enrich_provider.strip()
    if not provider_name:
        _log.error("KNOWLEDGE_ENRICH_PROVIDER is required but not set")
        raise EnvironmentError("KNOWLEDGE_ENRICH_PROVIDER is required but not set")

    if provider_name not in _VALID_PROVIDERS:
        _log.error(
            "KNOWLEDGE_ENRICH_PROVIDER=%r is not recognised; valid values: %s",
            provider_name,
            ", ".join(sorted(_VALID_PROVIDERS)),
        )
        raise EnvironmentError(
            f"KNOWLEDGE_ENRICH_PROVIDER={provider_name!r} is not recognised; "
            f"valid values: {', '.join(sorted(_VALID_PROVIDERS))}"
        )

    if provider_name == "ollama":
        from llm.providers.ollama import OllamaProvider  # type: ignore[import-untyped]

        return OllamaProvider(model=model, base_url=_cfg.ollama_base_url)

    # provider_name == "huggingface"
    api_key = _cfg.hf_api_key.strip()
    if not api_key:
        _log.error(
            "HF_API_KEY is required when KNOWLEDGE_ENRICH_PROVIDER=huggingface but not set"
        )
        raise EnvironmentError(
            "HF_API_KEY is required when KNOWLEDGE_ENRICH_PROVIDER=huggingface but not set"
        )

    from llm.providers.huggingface import HuggingFaceLLMProvider  # type: ignore[import-untyped]

    return HuggingFaceLLMProvider(model=model, api_key=api_key)


def get_knowledge_embed_fn() -> object:
    """Return the embedding function for knowledge ingestion and retrieval.

    Reads:
        KNOWLEDGE_EMBED_PROVIDER — required; "ollama" | "huggingface"
        KNOWLEDGE_EMBED_MODEL    — required; no code-level default
        HF_API_KEY               — required if KNOWLEDGE_EMBED_PROVIDER=huggingface
        OLLAMA_BASE_URL          — used if KNOWLEDGE_EMBED_PROVIDER=ollama

    Raises:
        EnvironmentError: if any required env var is absent, blank, or unrecognised
    """
    embed_model = _cfg.knowledge_embed_model.strip()
    if not embed_model:
        _log.error("KNOWLEDGE_EMBED_MODEL is required but not set")
        raise EnvironmentError("KNOWLEDGE_EMBED_MODEL is required but not set")

    provider_name = _cfg.knowledge_embed_provider.strip()
    if not provider_name:
        _log.error("KNOWLEDGE_EMBED_PROVIDER is required but not set")
        raise EnvironmentError("KNOWLEDGE_EMBED_PROVIDER is required but not set")

    if provider_name not in _VALID_PROVIDERS:
        _log.error(
            "KNOWLEDGE_EMBED_PROVIDER=%r is not recognised; valid values: %s",
            provider_name,
            ", ".join(sorted(_VALID_PROVIDERS)),
        )
        raise EnvironmentError(
            f"KNOWLEDGE_EMBED_PROVIDER={provider_name!r} is not recognised; "
            f"valid values: {', '.join(sorted(_VALID_PROVIDERS))}"
        )

    if provider_name == "ollama":
        from rag.knowledge.embedder import OllamaEmbedFn

        return OllamaEmbedFn(model=embed_model, base_url=_cfg.ollama_base_url)

    # provider_name == "huggingface"
    api_key = _cfg.hf_api_key.strip()
    if not api_key:
        _log.error(
            "HF_API_KEY is required when KNOWLEDGE_EMBED_PROVIDER=huggingface but not set"
        )
        raise EnvironmentError(
            "HF_API_KEY is required when KNOWLEDGE_EMBED_PROVIDER=huggingface but not set"
        )

    from rag.knowledge.embedder import HuggingFaceEmbedFn

    return HuggingFaceEmbedFn(model=embed_model, api_key=api_key)
