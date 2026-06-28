"""ChromaDB-backed knowledge retriever with multi-query expansion and RRF ranking.

All embeddings are pre-computed by the active embed function (Ollama or HuggingFace,
selected via KNOWLEDGE_EMBED_PROVIDER) before being passed to ChromaDB.
No embedding function is registered on the collection — this avoids ChromaDB 0.5+
protocol requirements that break custom embedding classes.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from core.config import settings as _cfg
from core.errors import ProviderUnavailableError
from core.models import Campaign
from sqlalchemy import select
from storage.sqlite.adapter import SQLiteBackend

from rag.knowledge.factory import get_knowledge_embed_fn, get_knowledge_enrich_provider
from rag.knowledge.interface import KnowledgeChunk, KnowledgeRetriever
from rag.knowledge.vector_store import (
    GLOBAL_COLLECTION,
    ChromaVectorStore,
    campaign_collection,
)

_backend = SQLiteBackend(_cfg.database_url)

_log = logging.getLogger(__name__)


def _rerank_repr(c: KnowledgeChunk, max_body: int = 300) -> str:
    """Build a reranker representation using enriched metadata + body snippet.

    headline + summary give the LLM high-quality semantic signal without consuming
    all available context; body snippet adds literal-match anchors for fact questions.
    """
    parts: list[str] = []
    if c.headline:
        parts.append(c.headline)
    if c.summary:
        parts.append(c.summary)
    body = c.text
    if c.breadcrumb and body.startswith(c.breadcrumb):
        body = body[len(c.breadcrumb):].lstrip()
    if body:
        parts.append(body[:max_body])
    return "\n".join(parts)


class ChromaKnowledgeRetriever(KnowledgeRetriever):
    """Retriever over knowledge_global + knowledge_{campaign_id} ChromaDB collections."""

    def __init__(self, chroma_path: str | None = None) -> None:
        self._store = ChromaVectorStore(chroma_path) if chroma_path else ChromaVectorStore()

    async def delete_chunks_by_doc(
        self,
        doc_id: str,
        scope: str,
        campaign_id: str | None,
    ) -> None:
        """Delete all chunks for a document from the appropriate collection."""
        col_name = GLOBAL_COLLECTION if scope == "global" else campaign_collection(campaign_id or "")
        await self._store.delete_by_doc(col_name, doc_id)

    async def _embed_query(self, query: str) -> list[float]:
        """Pre-compute a single query embedding via the configured provider."""
        embed_fn = get_knowledge_embed_fn()
        vectors = await embed_fn.embed([query])
        return vectors[0]

    async def _get_game_system(self, campaign_id: str) -> str | None:
        """Return the campaign's game_system string, or None if not found."""
        try:
            async with await _backend.get_session() as db:
                result = await db.execute(
                    select(Campaign).where(Campaign.id == uuid.UUID(campaign_id))
                )
                campaign = result.scalar_one_or_none()
                return campaign.game_system if campaign else None
        except Exception as exc:
            _log.debug("[retriever] could not fetch game_system for campaign %s: %s", campaign_id, exc)
            return None

    async def search(
        self,
        query: str,
        campaign_id: str,
        role: str,
        top_k: int = 8,
    ) -> list[KnowledgeChunk]:
        from rag.knowledge.enricher import ChunkEnricher

        enricher = ChunkEnricher(get_knowledge_enrich_provider(_cfg.knowledge_llm_model))

        expansion_count = _cfg.knowledge_expansion_count
        top_k = top_k or _cfg.knowledge_top_k
        rrf_k = _cfg.knowledge_rrf_k

        game_system = await self._get_game_system(campaign_id) if campaign_id else None
        _log.debug("[retriever] game_system=%s", game_system)

        try:
            alternatives = await enricher.expand_query(
                query, n=expansion_count, setting_context=game_system
            )
        except ProviderUnavailableError:
            alternatives = []

        queries = [query] + alternatives

        where: dict[str, Any] | None = None
        if role == "player":
            where = {"access_level": {"$eq": "player_visible"}}

        collections = [GLOBAL_COLLECTION]
        if campaign_id:
            collections.append(campaign_collection(campaign_id))

        result_sets: list[list[tuple[str, dict[str, Any], str]]] = []

        for q in queries:
            try:
                q_embedding = await self._embed_query(q)
            except ProviderUnavailableError:
                raise

            for col_name in collections:
                try:
                    res = await self._store.query(
                        collection_name=col_name,
                        query_embeddings=[q_embedding],
                        n_results=top_k,
                        where=where,
                        include=["documents", "metadatas", "distances"],
                    )
                    if res is None:
                        result_sets.append([])
                        continue
                    ranked: list[tuple[str, dict[str, Any], str]] = []
                    for chunk_id, meta, doc in zip(
                        res["ids"][0],
                        res["metadatas"][0],
                        res["documents"][0],
                        strict=False,
                    ):
                        ranked.append((str(chunk_id), dict(meta), str(doc)))
                    result_sets.append(ranked)
                except ProviderUnavailableError:
                    raise
                except Exception as exc:
                    _log.warning("ChromaDB query failed for collection %r: %s", col_name, exc)
                    result_sets.append([])

        rrf_scores: dict[str, float] = {}
        chunk_data: dict[str, tuple[dict[str, Any], str]] = {}

        for ranked in result_sets:
            for rank, (chunk_id, meta, doc) in enumerate(ranked):
                rrf_scores[chunk_id] = rrf_scores.get(chunk_id, 0.0) + 1.0 / (rrf_k + rank + 1)
                if chunk_id not in chunk_data:
                    chunk_data[chunk_id] = (meta, doc)

        sorted_ids = sorted(rrf_scores, key=lambda cid: rrf_scores[cid], reverse=True)

        retrieval_k = min(top_k + 4, len(sorted_ids))
        candidates: list[KnowledgeChunk] = []
        for chunk_id in sorted_ids[:retrieval_k]:
            meta, doc = chunk_data[chunk_id]
            candidates.append(
                KnowledgeChunk(
                    chunk_id=chunk_id,
                    doc_id=str(meta.get("doc_id", "")),
                    doc_title=str(meta.get("doc_title", "")),
                    headline=str(meta.get("headline", "")),
                    summary=str(meta.get("summary", "")),
                    topic=str(meta.get("topic", "")),
                    access_level=str(meta.get("access_level", "player_visible")),
                    scope=str(meta.get("scope", "")),
                    text=str(meta.get("original_text", doc)),
                    rrf_score=rrf_scores[chunk_id],
                    breadcrumb=str(meta.get("breadcrumb", "")),
                    source_type=str(meta.get("source_type", "rulebook")),
                )
            )

        if len(candidates) > 1:
            try:
                order = await enricher.rerank(query, [_rerank_repr(c) for c in candidates])
                candidates = [candidates[i] for i in order if i < len(candidates)]
            except ProviderUnavailableError:
                pass

        return candidates[:top_k]
