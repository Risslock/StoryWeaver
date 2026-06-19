"""ChromaDB-backed campaign history index.

Indexes StoryEvent content so twins and the GM planning tool can retrieve
relevant past events via semantic search. Falls back gracefully when ChromaDB
is unavailable.

Local embeddings: nomic-embed-text via Ollama.
Cloud override:   EMBEDDING_PROVIDER=huggingface + BAAI/bge-base-en-v1.5.
"""

from __future__ import annotations

import uuid
from typing import Any

from rag.interface import Retriever, RetrievedChunk

_COLLECTION_PREFIX = "campaign_history"


class HistoryRetriever(Retriever):
    """Semantic retriever for campaign story events (ChromaDB backend)."""

    def __init__(self, campaign_id: uuid.UUID, chroma_path: str = "./data/chroma") -> None:
        self._campaign_id = campaign_id
        self._chroma_path = chroma_path
        self._collection_name = f"{_COLLECTION_PREFIX}_{campaign_id.hex}"
        self._client: Any = None
        self._collection: Any = None

    def _ensure_client(self) -> None:
        if self._client is not None:
            return
        import chromadb  # type: ignore[import-untyped]

        self._client = chromadb.PersistentClient(path=self._chroma_path)
        self._collection = self._client.get_or_create_collection(
            name=self._collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    async def add(self, doc_id: str, content: str, metadata: dict[str, object] | None = None) -> None:
        self._ensure_client()
        self._collection.upsert(
            ids=[doc_id],
            documents=[content],
            metadatas=[metadata or {}],
        )

    async def search(self, query: str, top_k: int = 5) -> list[RetrievedChunk]:
        self._ensure_client()
        results = self._collection.query(
            query_texts=[query],
            n_results=min(top_k, max(self._collection.count(), 1)),
        )
        chunks: list[RetrievedChunk] = []
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            chunks.append(
                RetrievedChunk(
                    content=str(doc),
                    score=float(1.0 - dist),
                    metadata=dict(meta),
                )
            )
        return chunks

    async def delete(self, doc_id: str) -> None:
        self._ensure_client()
        self._collection.delete(ids=[doc_id])

    async def index_event(
        self,
        event_id: uuid.UUID,
        content: str,
        event_type: str,
        is_public: bool,
        session_number: int | None = None,
    ) -> None:
        metadata: dict[str, object] = {
            "event_type": event_type,
            "is_public": is_public,
            "session_number": session_number if session_number is not None else -1,
        }
        await self.add(str(event_id), content, metadata)