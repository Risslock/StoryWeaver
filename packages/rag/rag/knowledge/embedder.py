"""Ollama-backed embedding function, shared by ingestion and retrieval."""

from __future__ import annotations

import json
import os
import urllib.request

from core.errors import ProviderUnavailableError


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


def get_embed_fn() -> OllamaEmbedFn:
    """Return an OllamaEmbedFn configured from env vars / settings."""
    from core.config import settings as _cfg

    model = os.environ.get("KNOWLEDGE_EMBED_MODEL", _cfg.knowledge_embed_model)
    base_url = os.environ.get("OLLAMA_BASE_URL", _cfg.ollama_base_url)
    return OllamaEmbedFn(model=model, base_url=base_url)
