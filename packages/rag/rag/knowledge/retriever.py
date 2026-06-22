"""ChromaDB-backed knowledge retriever with multi-query expansion and RRF ranking."""

from __future__ import annotations

import os
from typing import Any

from core.errors import ProviderUnavailableError

from rag.knowledge.embedder import get_embed_fn
from rag.knowledge.interface import KnowledgeChunk, KnowledgeRetriever
from rag.knowledge.vector_store import (
    GLOBAL_COLLECTION,
    ChromaVectorStore,
    campaign_collection,
)


class ChromaKnowledgeRetriever(KnowledgeRetriever):
    """Retriever over knowledge_global + knowledge_{campaign_id} ChromaDB collections."""

    def __init__(self, chroma_path: str | None = None) -> None:
        self._store = ChromaVectorStore(chroma_path) if chroma_path else ChromaVectorStore()

    def _get_collection(self, name: str) -> Any:
        return self._store.collection(name, embed_fn=get_embed_fn())

    async def search(
        self,
        query: str,
        campaign_id: str,
        role: str,
        top_k: int = 8,
    ) -> list[KnowledgeChunk]:
        from rag.knowledge.enricher import ChunkEnricher
        from llm.providers.ollama import OllamaProvider

        from core.config import settings as _cfg

        llm_model = os.environ.get("KNOWLEDGE_LLM_MODEL", _cfg.knowledge_llm_model)
        enricher = ChunkEnricher(OllamaProvider(model=llm_model))

        expansion_count = int(os.environ.get("KNOWLEDGE_EXPANSION_COUNT", str(_cfg.knowledge_expansion_count)))
        top_k = int(os.environ.get("KNOWLEDGE_TOP_K", str(top_k or _cfg.knowledge_top_k)))
        rrf_k = int(os.environ.get("KNOWLEDGE_RRF_K", str(_cfg.knowledge_rrf_k)))

        try:
            alternatives = await enricher.expand_query(query)
        except ProviderUnavailableError:
            alternatives = []

        queries = [query] + alternatives[:expansion_count]

        where: dict[str, Any] | None = None
        if role == "player":
            where = {"access_level": {"$eq": "player_visible"}}

        result_sets: list[list[tuple[str, dict[str, Any], str]]] = []

        for q in queries:
            for col_name in [GLOBAL_COLLECTION, campaign_collection(campaign_id)]:
                try:
                    col = self._get_collection(col_name)
                    count = col.count()
                    if count == 0:
                        result_sets.append([])
                        continue
                    kwargs: dict[str, Any] = {
                        "query_texts": [q],
                        "n_results": min(top_k, count),
                        "include": ["documents", "metadatas", "distances"],
                    }
                    if where is not None:
                        kwargs["where"] = where
                    res = col.query(**kwargs)
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
                except Exception:
                    result_sets.append([])

        rrf_scores: dict[str, float] = {}
        chunk_data: dict[str, tuple[dict[str, Any], str]] = {}

        for ranked in result_sets:
            for rank, (chunk_id, meta, doc) in enumerate(ranked):
                rrf_scores[chunk_id] = rrf_scores.get(chunk_id, 0.0) + 1.0 / (rrf_k + rank + 1)
                if chunk_id not in chunk_data:
                    chunk_data[chunk_id] = (meta, doc)

        sorted_ids = sorted(rrf_scores, key=lambda cid: rrf_scores[cid], reverse=True)

        # Build a larger candidate pool for LLM re-ranking, then trim to top_k.
        retrieval_k = min(top_k * 2, len(sorted_ids))
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
                )
            )

        if len(candidates) > 1:
            try:
                order = await enricher.rerank(query, [c.text for c in candidates])
                candidates = [candidates[i] for i in order if i < len(candidates)]
            except ProviderUnavailableError:
                pass

        return candidates[:top_k]
