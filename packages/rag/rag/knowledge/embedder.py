"""Embedding functions for knowledge ingestion and retrieval.

OllamaEmbedFn: backed by Ollama /api/embed (local).
HuggingFaceEmbedFn: backed by HuggingFace Inference API feature-extraction endpoint.

Use get_knowledge_embed_fn() from factory.py (provider-aware) instead of the deprecated
get_embed_fn() which is hardcoded to Ollama.
"""

from __future__ import annotations

import json
import logging
from core.config import settings as _cfg
import time
import urllib.request

from core.errors import ProviderUnavailableError

_log = logging.getLogger(__name__)


class OllamaEmbedFn:
    """ChromaDB-compatible embedding function backed by Ollama's /api/embed.

    Avoids chromadb's built-in OllamaEmbeddingFunction which has moved across
    versions and requires an explicit package install in chromadb >= 0.5.
    """

    def __init__(self, model: str, base_url: str) -> None:
        self._model = model
        self._url = base_url.rstrip("/") + "/api/embed"

    @property
    def name(self) -> str:
        """ChromaDB uses this to identify and verify the embedding function per-collection."""
        return f"ollama_{self._model}"

    def __call__(self, input: list[str]) -> list[list[float]]:
        body = json.dumps({"model": self._model, "input": input}).encode()
        req = urllib.request.Request(
            self._url,
            data=body,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return json.loads(resp.read())["embeddings"]
        except Exception as exc:
            raise ProviderUnavailableError(
                f"Ollama embedding failed (model={self._model}, url={self._url}): {exc}"
            ) from exc

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Async wrapper — runs the blocking HTTP call in a thread."""
        import asyncio
        return await asyncio.to_thread(self, texts)


class HuggingFaceEmbedFn:
    """ChromaDB-compatible embedding function backed by HuggingFace Inference API.

    Endpoint: POST https://api-inference.huggingface.co/models/{model}
    Request:  {"inputs": ["text1", "text2"]}
    Response: [[float, ...], ...]

    HTTP 429 (rate limit): retries with exponential backoff — 3 attempts, delays [5, 10, 20] s.
    Other errors: raises ProviderUnavailableError immediately.
    """

    _RETRY_DELAYS = (5, 10, 20)

    def __init__(self, model: str, api_key: str) -> None:
        self._model = model
        self._api_key = api_key
        self._url = f"https://api-inference.huggingface.co/models/{model}"

    @property
    def name(self) -> str:
        return f"huggingface_{self._model}"

    def __call__(self, input: list[str]) -> list[list[float]]:
        body = json.dumps({"inputs": input}).encode()
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}",
        }
        req = urllib.request.Request(self._url, data=body, headers=headers)

        for attempt, delay in enumerate(self._RETRY_DELAYS):
            try:
                with urllib.request.urlopen(req, timeout=120) as resp:
                    return json.loads(resp.read())
            except urllib.error.HTTPError as exc:
                if exc.code == 429:
                    _log.warning(
                        "HuggingFace embedding rate-limited (429) on attempt %d; "
                        "retrying in %ds (model=%s)",
                        attempt + 1,
                        delay,
                        self._model,
                    )
                    time.sleep(delay)
                    continue
                raise ProviderUnavailableError(
                    f"HuggingFace embedding failed (HTTP {exc.code}, model={self._model}): {exc}"
                ) from exc
            except Exception as exc:
                raise ProviderUnavailableError(
                    f"HuggingFace embedding failed (model={self._model}): {exc}"
                ) from exc

        raise ProviderUnavailableError(
            f"HuggingFace embedding rate-limited after {len(self._RETRY_DELAYS)} retries "
            f"(model={self._model}). Re-run ingestion after quota resets."
        )

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Async wrapper — runs the blocking HTTP call in a thread."""
        import asyncio
        return await asyncio.to_thread(self, texts)


def get_embed_fn() -> OllamaEmbedFn:
    """Return an OllamaEmbedFn configured from env vars / settings.

    DEPRECATED(012): Use get_knowledge_embed_fn() from factory.py instead — it supports
    both Ollama and HuggingFace providers via KNOWLEDGE_EMBED_PROVIDER (feature 012).
    """
    _log.warning(
        "get_embed_fn() is deprecated (feature 012). "
        "Use get_knowledge_embed_fn() from rag.knowledge.factory instead."
    )
    return OllamaEmbedFn(model=_cfg.knowledge_embed_model, base_url=_cfg.ollama_base_url)
