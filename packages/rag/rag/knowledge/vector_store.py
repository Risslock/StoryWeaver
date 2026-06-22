"""ChromaDB client shared by the ingestion (write) and retrieval (read) paths.

Both paths use pre-computed embeddings — no embedding function is ever registered
on the collection.  This avoids ChromaDB 0.5+ protocol requirements (is_legacy,
create_collection_configuration) that break custom embedding classes.

  Write path: OllamaEmbedFn.embed(texts) → upsert(embeddings=[...])
  Read path:  OllamaEmbedFn.embed([query]) → query(query_embeddings=[...])
"""

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

    Collections are always created without an embedding function.
    Callers are responsible for pre-computing all embeddings before calling
    ``upsert`` or ``query``.
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

    def collection(self, name: str) -> Any:
        """Return a ChromaDB collection (no embedding function — pre-computed vectors only)."""
        client = self._get_client()
        return client.get_or_create_collection(
            name=name, metadata={"hnsw:space": "cosine"}
        )

    async def upsert(
        self,
        collection_name: str,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict[str, object]],
    ) -> None:
        try:
            col = self.collection(collection_name)
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

    async def query(
        self,
        collection_name: str,
        query_embeddings: list[list[float]],
        n_results: int,
        where: dict[str, Any] | None = None,
        include: list[str] | None = None,
    ) -> Any:
        """Query a collection using pre-computed query embeddings."""
        try:
            col = self.collection(collection_name)
            count = await asyncio.to_thread(col.count)
            if count == 0:
                return None
            n_results = min(n_results, count)
            kwargs: dict[str, Any] = {
                "query_embeddings": query_embeddings,
                "n_results": n_results,
                "include": include or ["documents", "metadatas", "distances"],
            }
            if where is not None:
                kwargs["where"] = where
            return await asyncio.to_thread(col.query, **kwargs)
        except ProviderUnavailableError:
            raise
        except Exception as exc:
            raise ProviderUnavailableError(f"ChromaDB query failed: {exc}") from exc

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

    async def get_all(self, collection_name: str) -> Any:
        """Fetch all documents and metadata from a collection."""
        try:
            col = self.collection(collection_name)
            return await asyncio.to_thread(
                col.get, include=["metadatas", "documents"]
            )
        except ProviderUnavailableError:
            raise
        except Exception as exc:
            raise ProviderUnavailableError(f"ChromaDB get failed: {exc}") from exc
