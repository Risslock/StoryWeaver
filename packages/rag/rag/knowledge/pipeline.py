"""Ingestion pipeline: extract → (enrich → embed → store) per batch, with SQLite status tracking.

Each batch of chunks is enriched, embedded, and upserted to ChromaDB before moving to the next
batch. This makes the document partially queryable as ingestion progresses, keeps individual
Ollama embedding requests small (avoiding HTTP 400 on large payloads), and limits data loss
if ingestion fails mid-document.
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import UTC, datetime

from core.config import settings
from core.errors import ProviderUnavailableError
from core.models import KnowledgeDocument
from sqlalchemy import select
from sqlalchemy import update as sa_update
from storage.sqlite.adapter import SQLiteBackend

from rag.knowledge.embedder import get_embed_fn
from rag.knowledge.enricher import ChunkEnricher
from rag.knowledge.interface import ChunkEnrichment, IngestionConfig
from rag.knowledge.vector_store import (
    GLOBAL_COLLECTION,
    ChromaVectorStore,
    campaign_collection,
)

_log = logging.getLogger(__name__)
_backend = SQLiteBackend(settings.database_url)


class IngestionPipeline:
    """Orchestrates the full ingestion flow for a single document."""

    def __init__(self, chroma_path: str | None = None) -> None:
        self._store = ChromaVectorStore(chroma_path) if chroma_path else ChromaVectorStore()

    async def run(
        self,
        doc_id: str,
        file_path: str,
        format: str,
        scope: str,
        campaign_id: str | None,
        config: IngestionConfig | None = None,
    ) -> None:
        """Run the pipeline and persist status to SQLite throughout.

        Phases per batch:
          1. Extract all chunks upfront (needed for total count).
          2. For each batch: enrich → embed → upsert to ChromaDB → update progress.
        """
        if config is None:
            config = IngestionConfig()
        await self._set_status(doc_id, "processing")
        try:
            from rag.knowledge.chunker import create_chunker
            _log.info(
                "Ingestion started — chunking strategy: %s, doc_id: %s",
                create_chunker().strategy_name,
                doc_id,
            )
            # Phase 1 — Extract: file → full text + raw text chunks (all at once)
            full_text, chunks = await self._extract(file_path, format, config)
            total = len(chunks)
            await self._set_status(doc_id, "processing", chunk_count=total, chunks_processed=0)

            enrich_model = os.environ.get("KNOWLEDGE_ENRICH_MODEL", settings.knowledge_enrich_model)
            batch_size = int(
                os.environ.get("KNOWLEDGE_ENRICH_BATCH_SIZE", str(settings.knowledge_enrich_batch_size))
            )
            from llm.providers.ollama import OllamaProvider

            enricher = ChunkEnricher(OllamaProvider(model=enrich_model))
            embed_fn = get_embed_fn()
            doc_title = await self._get_doc_title(doc_id)
            collection_name = (
                GLOBAL_COLLECTION if scope == "global" else campaign_collection(campaign_id or "")
            )

            # Phase 2 — Breadcrumbs: compute once for all chunks before batching
            if config.enable_breadcrumbs:
                from rag.knowledge.breadcrumb import BreadcrumbExtractor
                all_breadcrumbs = BreadcrumbExtractor().extract(full_text, chunks, doc_title)
            else:
                all_breadcrumbs = [""] * total

            stored = 0
            batches = [chunks[i : i + batch_size] for i in range(0, total, batch_size)]

            for batch_idx, batch in enumerate(batches):
                chunk_offset = batch_idx * batch_size
                batch_breadcrumbs = all_breadcrumbs[chunk_offset : chunk_offset + len(batch)]

                # Phase 3 — Enrich: LLM assigns headline / summary / topic / access_level
                enrichments = await enricher.enrich_batch(batch)

                # Phase 4 — Contextual summaries (opt-in)
                if config.enable_contextual_summaries:
                    contextual_summaries = await enricher.generate_contextual_summaries(
                        batch, batch_breadcrumbs, doc_title
                    )
                else:
                    contextual_summaries = [""] * len(batch)

                # Phase 5 — Embed: compound texts → float vectors (Ollama)
                ids, compound_texts, metadatas = self._build_records(
                    doc_id, doc_title, batch, enrichments,
                    batch_breadcrumbs, contextual_summaries,
                    config, scope, campaign_id,
                    chunk_offset=chunk_offset,
                )
                embeddings = await embed_fn.embed(compound_texts)

                # Phase 6 — Store: upsert this batch immediately so it is queryable now
                await self._store.upsert(collection_name, ids, embeddings, compound_texts, metadatas)

                stored += len(batch)
                await self._set_progress(doc_id, stored)

            await self._set_status(doc_id, "ready", chunk_count=stored)

        except ProviderUnavailableError as exc:
            await self._set_status(doc_id, "failed", error=f"{type(exc).__name__}: {exc}")
        except Exception as exc:
            await self._set_status(doc_id, "failed", error=f"{type(exc).__name__}: {exc}")

    # ------------------------------------------------------------------ helpers

    async def _extract(self, file_path: str, format: str, config: IngestionConfig) -> tuple[str, list[str]]:
        if format == "pdf":
            from rag.knowledge.ingestor import PdfIngestor
            return await PdfIngestor().extract_with_context(file_path, config)
        from rag.knowledge.ingestor import MarkdownIngestor
        return await MarkdownIngestor().extract_with_context(file_path, config)

    def _build_records(
        self,
        doc_id: str,
        doc_title: str,
        chunks: list[str],
        enrichments: list[ChunkEnrichment],
        breadcrumbs: list[str],
        contextual_summaries: list[str],
        config: IngestionConfig,
        scope: str,
        campaign_id: str | None,
        chunk_offset: int = 0,
    ) -> tuple[list[str], list[str], list[dict[str, object]]]:
        ids: list[str] = []
        compound_texts: list[str] = []
        metadatas: list[dict[str, object]] = []

        doc_id_hex = doc_id.replace("-", "")
        for local_idx, (raw_text, enrichment) in enumerate(zip(chunks, enrichments, strict=False)):
            global_idx = chunk_offset + local_idx
            effective_access = (
                config.access_level_default
                if config.access_level_default is not None
                else enrichment.access_level
            )
            breadcrumb = breadcrumbs[local_idx] if local_idx < len(breadcrumbs) else ""
            ctx_summary = contextual_summaries[local_idx] if local_idx < len(contextual_summaries) else ""

            # original_text includes breadcrumb prefix so KnowledgeChunk.text displays it
            original_text = f"{breadcrumb}\n\n{raw_text}" if breadcrumb else raw_text

            # Compound text order per contracts/ingestion-pipeline.md
            if breadcrumb and ctx_summary:
                compound = f"{breadcrumb}\n\n{ctx_summary}\n\n{enrichment.headline}\n\n{enrichment.summary}\n\n{raw_text}"
            elif breadcrumb:
                compound = f"{breadcrumb}\n\n{enrichment.headline}\n\n{enrichment.summary}\n\n{raw_text}"
            else:
                compound = f"{enrichment.headline}\n\n{enrichment.summary}\n\n{raw_text}"

            ids.append(f"{doc_id_hex}_{global_idx:04d}")
            compound_texts.append(compound)
            metadatas.append({
                "doc_id": doc_id,
                "doc_title": doc_title,
                "chunk_index": global_idx,
                "headline": enrichment.headline,
                "summary": enrichment.summary,
                "topic": enrichment.topic,
                "access_level": effective_access,
                "scope": scope,
                "campaign_id": campaign_id or "",
                "original_text": original_text,
                "breadcrumb": breadcrumb,
                "source_type": config.source_type,
            })

        return ids, compound_texts, metadatas

    # --------------------------------------------------------- DB status helpers

    async def _get_doc_title(self, doc_id: str) -> str:
        try:
            async with await _backend.get_session() as db:
                result = await db.execute(
                    select(KnowledgeDocument).where(KnowledgeDocument.id == uuid.UUID(doc_id))
                )
                doc = result.scalar_one_or_none()
                return doc.title if doc else doc_id
        except Exception:
            return doc_id

    async def _set_status(
        self,
        doc_id: str,
        status: str,
        chunk_count: int | None = None,
        chunks_processed: int | None = None,
        error: str | None = None,
    ) -> None:
        try:
            async with await _backend.get_session() as db:
                result = await db.execute(
                    select(KnowledgeDocument).where(KnowledgeDocument.id == uuid.UUID(doc_id))
                )
                doc = result.scalar_one_or_none()
                if doc is not None:
                    doc.ingestion_status = status
                    doc.updated_at = datetime.now(UTC)
                    if chunk_count is not None:
                        doc.chunk_count = chunk_count
                    if chunks_processed is not None:
                        doc.chunks_processed = chunks_processed
                    if error is not None:
                        doc.error_message = error[:500]
                    await db.commit()
        except Exception as _e:
            _log.warning("_set_status failed (doc_id=%s, status=%s): %s", doc_id, status, _e)

    async def _set_progress(self, doc_id: str, chunks_processed: int) -> None:
        try:
            async with await _backend.get_session() as db:
                await db.execute(
                    sa_update(KnowledgeDocument)
                    .where(KnowledgeDocument.id == uuid.UUID(doc_id))
                    .values(chunks_processed=chunks_processed, updated_at=datetime.now(UTC))
                )
                await db.commit()
        except Exception as _e:
            _log.warning("_set_progress failed (doc_id=%s): %s", doc_id, _e)
