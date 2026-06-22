"""Ingestion pipeline: convert → chunk → enrich → index, with SQLite status tracking."""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import UTC, datetime

from core.config import settings
from core.errors import ProviderUnavailableError
from core.models import KnowledgeDocument
from sqlalchemy import select, update as sa_update
from storage.sqlite.adapter import SQLiteBackend

from rag.knowledge.enricher import ENRICH_BATCH_SIZE, ChunkEnricher
from rag.knowledge.interface import ChunkEnrichment
from rag.knowledge.retriever import ChromaKnowledgeRetriever

_backend = SQLiteBackend(settings.database_url)


class IngestionPipeline:
    """Orchestrates the full ingestion flow for a single document."""

    def __init__(self) -> None:
        self._retriever = ChromaKnowledgeRetriever()

    async def run(
        self,
        doc_id: str,
        file_path: str,
        format: str,
        access_level_default: str | None,
        scope: str,
        campaign_id: str | None,
    ) -> None:
        """Run the pipeline and update KnowledgeDocument status in the DB."""
        await self._set_status(doc_id, "processing")
        try:
            chunks = self._extract_chunks(file_path, format)
            total = len(chunks)

            # Record total upfront so the UI can show "enriching N chunks…"
            await self._set_status(
                doc_id, "processing", chunk_count=total, chunks_processed=0
            )

            enrich_model = os.environ.get(
                "KNOWLEDGE_ENRICH_MODEL", settings.knowledge_enrich_model
            )
            batch_size = int(
                os.environ.get(
                    "KNOWLEDGE_ENRICH_BATCH_SIZE",
                    str(settings.knowledge_enrich_batch_size),
                )
            )
            from llm.providers.ollama import OllamaProvider

            enricher = ChunkEnricher(OllamaProvider(model=enrich_model))

            completed = 0

            async def _enrich_batch_tracked(
                batch_texts: list[str],
            ) -> list[ChunkEnrichment]:
                nonlocal completed
                result = await enricher.enrich_batch(batch_texts)
                completed += len(result)
                await self._set_progress(doc_id, completed)
                return result

            batches = [chunks[i : i + batch_size] for i in range(0, total, batch_size)]
            batch_results = await asyncio.gather(
                *[_enrich_batch_tracked(b) for b in batches]
            )
            enrichments: list[ChunkEnrichment] = [
                e for batch in batch_results for e in batch
            ]

            doc_title = await self._get_doc_title(doc_id)
            enriched_chunks: list[tuple[str, str, str, dict[str, object]]] = []
            for idx, (text, enrichment) in enumerate(zip(chunks, enrichments)):
                effective_access = (
                    access_level_default
                    if access_level_default is not None
                    else enrichment.access_level
                )
                chunk_id = f"{doc_id.replace('-', '')}_{idx:04d}"
                # Compound document: headline + summary + original text for richer embeddings.
                # Original text preserved in metadata for citation display.
                compound_text = (
                    f"{enrichment.headline}\n\n{enrichment.summary}\n\n{text}"
                )
                metadata: dict[str, object] = {
                    "doc_id": doc_id,
                    "doc_title": doc_title,
                    "chunk_index": idx,
                    "headline": enrichment.headline,
                    "summary": enrichment.summary,
                    "topic": enrichment.topic,
                    "access_level": effective_access,
                    "scope": scope,
                    "campaign_id": campaign_id or "",
                    "original_text": text,
                }
                enriched_chunks.append((chunk_id, compound_text, text, metadata))

            for chunk_id, compound_text, __, metadata in enriched_chunks:
                await self._retriever.add_chunk(
                    chunk_id=chunk_id,
                    text=compound_text,
                    metadata=metadata,
                    scope=scope,
                    campaign_id=campaign_id,
                )

            await self._set_status(doc_id, "ready", chunk_count=len(enriched_chunks))

        except ProviderUnavailableError as exc:
            await self._set_status(doc_id, "failed", error=str(exc))
        except Exception as exc:
            await self._set_status(doc_id, "failed", error=str(exc))

    def _extract_chunks(self, file_path: str, format: str) -> list[str]:
        if format == "pdf":
            from rag.knowledge.ingestor import PdfIngestor

            return PdfIngestor().ingest(file_path)
        from rag.knowledge.ingestor import MarkdownIngestor

        return MarkdownIngestor().ingest(file_path)

    async def _get_doc_title(self, doc_id: str) -> str:
        try:
            async with await _backend.get_session() as db:
                result = await db.execute(
                    select(KnowledgeDocument).where(
                        KnowledgeDocument.id == uuid.UUID(doc_id)
                    )
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
                    select(KnowledgeDocument).where(
                        KnowledgeDocument.id == uuid.UUID(doc_id)
                    )
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
        except Exception:
            pass

    async def _set_progress(self, doc_id: str, chunks_processed: int) -> None:
        try:
            async with await _backend.get_session() as db:
                await db.execute(
                    sa_update(KnowledgeDocument)
                    .where(KnowledgeDocument.id == uuid.UUID(doc_id))
                    .values(
                        chunks_processed=chunks_processed, updated_at=datetime.now(UTC)
                    )
                )
                await db.commit()
        except Exception:
            pass
