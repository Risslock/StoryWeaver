"""Retriever ABC — all RAG adapters implement this interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class RetrievedChunk:
    content: str
    score: float
    metadata: dict[str, object]


class Retriever(ABC):
    """Base interface for all RAG retrievers."""

    @abstractmethod
    async def add(self, doc_id: str, content: str, metadata: dict[str, object] | None = None) -> None:
        """Index a document chunk."""

    @abstractmethod
    async def search(self, query: str, top_k: int = 5) -> list[RetrievedChunk]:
        """Return the top_k most relevant chunks for the query."""

    @abstractmethod
    async def delete(self, doc_id: str) -> None:
        """Remove a previously indexed document."""