"""ChromaDB client shared by the ingestion (write) and retrieval (read) paths."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from core.errors import ProviderUnavailableError

_log = logging.getLogger(__name__)

_CHROMA_PATH = "./data/chroma"
GLOBAL_COLLECTION = "knowledge_global"


def campaign_collection(campaign_id: str) -> str:
    return f"knowledge_{campaign_id.replace('-', '')}"


class ChromaVectorStore:
    """Thin wrapper around a ChromaDB PersistentClient.

    The write path (ingestion) passes pre-computed embeddings to ``upsert``.
    The read path (retrieval) passes an ``embed_fn`` to ``collection`` so
    ChromaDB can embed query texts at search time.
    """

    def __init__(self, chroma_path: str = _CHROMA_PATH) -> None:
        self._chroma_path = chroma_path
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            import chromadb  # type: ignore[import-untyped]

            self._client = chromadb.PersistentClient(path=self._chroma_path)
            return self._client
        except Exception as exc:
            raise ProviderUnavailableError(f"Cannot initialise ChromaDB: {exc}") from exc

    def collection(self, name: str, embed_fn: Any | None = None) -> Any:
        """Return a ChromaDB collection, optionally wired with an embedding function."""
        client = self._get_client()
        kwargs: dict[str, Any] = {"name": name, "metadata": {"hnsw:space": "cosine"}}
        if embed_fn is not None:
            kwargs["embedding_function"] = embed_fn
        return client.get_or_create_collection(**kwargs)

    async def upsert(
        self,
        collection_name: str,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict[str, object]],
        embed_fn: Any | None = None,
    ) -> None:
        try:
            col = self.collection(collection_name, embed_fn=embed_fn)
            await asyncio.to_thread(
                col.upsert,
                ids=ids,
                embeddings=embeddings,
                documents=documents,
                metadatas=metadatas,
            )
        except ProviderUnavailableError:
            raise
        except Exception as exc:
            raise ProviderUnavailableError(f"ChromaDB upsert failed: {exc}") from exc

    async def delete_by_doc(self, collection_name: str, doc_id: str) -> None:
        try:
            col = self.collection(collection_name)
            result = await asyncio.to_thread(
                col.get, where={"doc_id": {"$eq": doc_id}}
            )
            if result and result.get("ids"):
                await asyncio.to_thread(col.delete, ids=result["ids"])
        except ProviderUnavailableError:
            raise
        except Exception as exc:
            raise ProviderUnavailableError(f"ChromaDB delete failed: {exc}") from exc
