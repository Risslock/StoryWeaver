"""Knowledge Q&A interfaces, dataclasses, and Pydantic result schemas."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel


@dataclass
class IngestionConfig:
    """All preprocessing options for a single ingestion run.

    Add new ingestion-time options here — never as extra kwargs on pipeline.run().
    """
    source_type: Literal["rulebook", "supplement", "handwritten_note", "novel"] = "rulebook"
    access_level_default: str | None = None
    enable_breadcrumbs: bool = True
    enable_contextual_summaries: bool = False
    cleaning: bool = True


class ChunkEnrichment(BaseModel):
    headline: str
    summary: str
    topic: str
    access_level: Literal["gm_only", "player_visible"]


class QueryExpansion(BaseModel):
    alternatives: list[str]


class BatchEnrichment(BaseModel):
    """Enrichment for every chunk in a document, returned in a single LLM call."""
    chunks: list[ChunkEnrichment]


class RankOrder(BaseModel):
    """LLM re-ranker output — chunk indices (1-based) ordered most → least relevant."""
    order: list[int]


@dataclass
class KnowledgeChunk:
    chunk_id: str
    doc_id: str
    doc_title: str
    headline: str
    summary: str
    topic: str
    access_level: str
    scope: str
    text: str
    rrf_score: float
    breadcrumb: str = ""
    source_type: str = "rulebook"


class KnowledgeRetriever(ABC):
    """Abstract retriever for the two-tier knowledge collections."""

    @abstractmethod
    async def search(
        self,
        query: str,
        campaign_id: str,
        role: str,
        top_k: int = 8,
    ) -> list[KnowledgeChunk]:
        """Return RRF-ranked chunks visible to the given role."""
