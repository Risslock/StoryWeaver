"""Knowledge Q&A service — bridge between Gradio UI and the RAG knowledge pipeline."""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import UTC, datetime

from core.config import settings
from core.errors import ProviderUnavailableError
from core.models import KnowledgeDocument
from sqlalchemy import select
from storage.sqlite.adapter import SQLiteBackend

_backend = SQLiteBackend(settings.database_url)


# ── Q&A ──────────────────────────────────────────────────────────────────────

async def ask_question(
    question: str,
    campaign_id: uuid.UUID,
    role: str,
) -> tuple[str, list]:
    """Return (answer_text, ranked_cited_chunks). Raises ProviderUnavailableError."""
    from rag.knowledge.retriever import ChromaKnowledgeRetriever
    from llm.providers.ollama import OllamaProvider

    llm_model = os.environ.get("KNOWLEDGE_LLM_MODEL", settings.knowledge_llm_model)
    retriever = ChromaKnowledgeRetriever()
    chunks = await retriever.search(
        query=question,
        campaign_id=str(campaign_id).replace("-", ""),
        role=role,
    )

    if not chunks:
        return (
            "I couldn't find relevant information for your question in the current knowledge base.",
            [],
        )

    context_parts = []
    for i, c in enumerate(chunks, 1):
        context_parts.append(
            f"[{i}] {c.doc_title} — {c.headline}\n{c.text}"
        )
    context = "\n\n".join(context_parts)

    system = (
        "You are a knowledgeable assistant for a tabletop RPG game. "
        "Answer the question using only the provided context. "
        "If the context does not contain enough information, say so clearly. "
        "Do not invent facts not present in the context."
    )
    prompt = (
        f"Context from the knowledge base:\n\n{context}\n\n"
        f"Question: {question}\n\n"
        "Provide a clear, concise answer based on the context above."
    )

    llm = OllamaProvider(model=llm_model)
    answer = await llm.generate(prompt, system=system)
    return answer, chunks


# ── Document management ───────────────────────────────────────────────────────

async def list_documents(
    campaign_id: uuid.UUID,
    scope_filter: str | None = None,
) -> list[KnowledgeDocument]:
    """Return documents visible to this campaign, ordered by created_at desc."""
    async with await _backend.get_session() as db:
        stmt = select(KnowledgeDocument).where(
            (KnowledgeDocument.scope == "global")
            | (KnowledgeDocument.campaign_id == campaign_id)
        )
        if scope_filter is not None:
            stmt = stmt.where(KnowledgeDocument.scope == scope_filter)
        stmt = stmt.order_by(KnowledgeDocument.created_at.desc())
        result = await db.execute(stmt)
        return list(result.scalars().all())


async def check_duplicate(
    title: str,
    scope: str,
    campaign_id: uuid.UUID | None,
) -> KnowledgeDocument | None:
    """Return existing document if a duplicate exists (same scope+campaign+title), else None."""
    async with await _backend.get_session() as db:
        stmt = select(KnowledgeDocument).where(
            KnowledgeDocument.scope == scope,
            KnowledgeDocument.title == title,
        )
        if campaign_id is None:
            stmt = stmt.where(KnowledgeDocument.campaign_id.is_(None))
        else:
            stmt = stmt.where(KnowledgeDocument.campaign_id == campaign_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()


async def submit_document(
    file_path: str,
    filename: str,
    title: str,
    scope: str,
    campaign_id: uuid.UUID | None,
    access_level_default: str | None,
    format: str,
) -> KnowledgeDocument:
    """Register document with pending status and fire background ingestion task."""
    async with await _backend.get_session() as db:
        doc = KnowledgeDocument(
            id=uuid.uuid4(),
            scope=scope,
            campaign_id=campaign_id,
            title=title,
            original_filename=filename,
            format=format,
            access_level_default=access_level_default,
            ingestion_status="processing",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        db.add(doc)
        await db.commit()
        await db.refresh(doc)
        doc_id = doc.id

    asyncio.create_task(_run_pipeline(str(doc_id), file_path, format, access_level_default, scope, campaign_id))
    return doc


async def confirm_overwrite(
    doc_id: uuid.UUID,
    file_path: str,
) -> None:
    """Delete existing chunks, reset status to processing, and re-ingest."""
    async with await _backend.get_session() as db:
        result = await db.execute(select(KnowledgeDocument).where(KnowledgeDocument.id == doc_id))
        doc = result.scalar_one_or_none()
        if doc is None:
            return
        doc.ingestion_status = "processing"
        doc.error_message = None
        doc.chunk_count = None
        doc.updated_at = datetime.now(UTC)
        scope = doc.scope
        campaign_id = doc.campaign_id
        fmt = doc.format
        access_default = doc.access_level_default
        await db.commit()

    from rag.knowledge.retriever import ChromaKnowledgeRetriever
    retriever = ChromaKnowledgeRetriever()
    try:
        await retriever.delete_chunks_by_doc(
            str(doc_id),
            scope=scope,
            campaign_id=str(campaign_id).replace("-", "") if campaign_id else None,
        )
    except Exception:
        pass

    asyncio.create_task(_run_pipeline(str(doc_id), file_path, fmt, access_default, scope, campaign_id))


async def _run_pipeline(
    doc_id: str,
    file_path: str,
    format: str,
    access_level_default: str | None,
    scope: str,
    campaign_id: uuid.UUID | None,
) -> None:
    from rag.knowledge.pipeline import IngestionPipeline
    pipeline = IngestionPipeline()
    await pipeline.run(
        doc_id=doc_id,
        file_path=file_path,
        format=format,
        access_level_default=access_level_default,
        scope=scope,
        campaign_id=str(campaign_id).replace("-", "") if campaign_id else None,
    )
