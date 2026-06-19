"""ChromaDB-backed character profile index for digital twin grounding.

Each character/NPC gets a scoped collection so twin agents retrieve only
their own entity's data. Players cannot query another character's index;
NPC indexes are GM-only.
"""

from __future__ import annotations

import uuid
from typing import Any

from rag.interface import Retriever, RetrievedChunk

_COLLECTION_PREFIX = "character"


class CharacterRetriever(Retriever):
    """Semantic retriever for a single character or NPC profile."""

    def __init__(self, entity_id: uuid.UUID, chroma_path: str = "./data/chroma") -> None:
        self._entity_id = entity_id
        self._chroma_path = chroma_path
        self._collection_name = f"{_COLLECTION_PREFIX}_{entity_id.hex}"
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
        count = self._collection.count()
        if count == 0:
            return []
        results = self._collection.query(
            query_texts=[query],
            n_results=min(top_k, count),
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

    async def index_profile(self, field: str, value: str) -> None:
        """Index a character profile field (e.g. background, personality)."""
        doc_id = f"{self._entity_id.hex}_{field}"
        await self.add(doc_id, value, {"field": field})