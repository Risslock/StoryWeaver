"""ChromaDB-backed Earthdawn rules index.

Indexes distilled mechanics tables (disciplines, races, circle progressions)
for semantic lookup during character validation and twin Q&A. No copyrighted
rulebook text is stored — only structured facts derived from the user's books.
"""

from __future__ import annotations

from typing import Any

from rag.interface import Retriever, RetrievedChunk

_COLLECTION_NAME = "earthdawn_rules"


class RulesRetriever(Retriever):
    """Semantic retriever for Earthdawn 4E mechanics tables."""

    def __init__(self, chroma_path: str = "./data/chroma") -> None:
        self._chroma_path = chroma_path
        self._client: Any = None
        self._collection: Any = None

    def _ensure_client(self) -> None:
        if self._client is not None:
            return
        import chromadb  # type: ignore[import-untyped]

        self._client = chromadb.PersistentClient(path=self._chroma_path)
        self._collection = self._client.get_or_create_collection(
            name=_COLLECTION_NAME,
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

    async def index_rules_data(self, rule_id: str, content: str, category: str) -> None:
        """Index a single rules entry (e.g., a Discipline row, a table cell)."""
        await self.add(rule_id, content, {"category": category})