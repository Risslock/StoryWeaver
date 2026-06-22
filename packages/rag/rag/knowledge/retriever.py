"""ChromaDB-backed knowledge retriever with multi-query expansion and RRF ranking."""

from __future__ import annotations

import json
import os
import urllib.request
from typing import Any

from core.errors import ProviderUnavailableError

from rag.knowledge.interface import KnowledgeChunk, KnowledgeRetriever

_CHROMA_PATH = "./data/chroma"
_GLOBAL_COLLECTION = "knowledge_global"


class _OllamaEmbedFn:
    """ChromaDB-compatible embedding function backed by Ollama's /api/embed.

    Avoids chromadb's built-in OllamaEmbeddingFunction which has moved across
    versions and requires an explicit package install in chromadb >= 0.5.
    """

    def __init__(self, model: str, base_url: str) -> None:
        self._model = model
        self._url = base_url.rstrip("/") + "/api/embed"

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


def _campaign_collection(campaign_id: str) -> str:
    return f"knowledge_{campaign_id.replace('-', '')}"


class ChromaKnowledgeRetriever(KnowledgeRetriever):
    """Retriever over knowledge_global + knowledge_{campaign_id} ChromaDB collections."""

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

    def _embed_fn(self) -> _OllamaEmbedFn:
        from core.config import settings as _cfg
        embed_model = os.environ.get("KNOWLEDGE_EMBED_MODEL", _cfg.knowledge_embed_model)
        ollama_url = os.environ.get("OLLAMA_BASE_URL", _cfg.ollama_base_url)
        return _OllamaEmbedFn(model=embed_model, base_url=ollama_url)

    def _get_collection(self, name: str) -> Any:
        client = self._get_client()
        ef = self._embed_fn()
        return client.get_or_create_collection(
            name=name,
            embedding_function=ef,
            metadata={"hnsw:space": "cosine"},
        )

    async def add_chunk(
        self,
        chunk_id: str,
        text: str,
        metadata: dict[str, object],
        scope: str,
        campaign_id: str | None = None,
    ) -> None:
        try:
            if scope == "global":
                col = self._get_collection(_GLOBAL_COLLECTION)
            else:
                if campaign_id is None:
                    raise ValueError("campaign_id required for campaign-scoped chunks")
                col = self._get_collection(_campaign_collection(campaign_id))
            col.upsert(ids=[chunk_id], documents=[text], metadatas=[metadata])
        except ProviderUnavailableError:
            raise
        except Exception as exc:
            raise ProviderUnavailableError(f"ChromaDB upsert failed: {exc}") from exc

    async def delete_chunks_by_doc(
        self,
        doc_id: str,
        scope: str,
        campaign_id: str | None = None,
    ) -> None:
        try:
            if scope == "global":
                col = self._get_collection(_GLOBAL_COLLECTION)
            else:
                if campaign_id is None:
                    return
                col = self._get_collection(_campaign_collection(campaign_id))
            all_ids = col.get(where={"doc_id": {"$eq": doc_id}})
            if all_ids and all_ids.get("ids"):
                col.delete(ids=all_ids["ids"])
        except ProviderUnavailableError:
            raise
        except Exception as exc:
            raise ProviderUnavailableError(f"ChromaDB delete failed: {exc}") from exc

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
            for col_name, col_scope in [
                (_GLOBAL_COLLECTION, "global"),
                (_campaign_collection(campaign_id), "campaign"),
            ]:
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
