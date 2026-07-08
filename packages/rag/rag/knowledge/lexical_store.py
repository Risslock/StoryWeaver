"""SQLite FTS5-backed lexical (BM25 keyword) index for knowledge chunks.

Lives in the same SQLite database as the rest of the app (core.config.settings.database_url),
not a separate file. Uses its own self-contained async engine, mirroring
rag.evaluation.store.EvaluationStore's pattern, since FTS5 virtual tables aren't
representable as declarative ORM models.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from core.config import settings as _cfg
from core.errors import ProviderUnavailableError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

_log = logging.getLogger(__name__)

_WORD_RE = re.compile(r"\w+", re.UNICODE)

_CREATE_TABLE_SQL = """
CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_lexical USING fts5(
    chunk_id UNINDEXED,
    doc_id UNINDEXED,
    scope UNINDEXED,
    campaign_id UNINDEXED,
    access_level UNINDEXED,
    text,
    tokenize='porter unicode61'
)
"""


def _tokenize_to_match_query(query_text: str) -> str:
    """Tokenize free-text into individually double-quoted terms joined with OR.

    Quoting each term prevents punctuation/operators in free-text user input from
    being interpreted as FTS5 query syntax. Returns "" for zero terms.
    """
    terms = _WORD_RE.findall(query_text)
    return " OR ".join(f'"{term}"' for term in terms)


class SQLiteLexicalStore:
    """FTS5-backed lexical index — mirrors ChromaVectorStore's method shape.

    Unlike ChromaVectorStore, there is no per-collection name — scope/campaign
    filtering happens via the `scope`/`campaign_id`/`access_level` WHERE columns
    in a single shared table.
    """

    def __init__(self, database_url: str | None = None) -> None:
        url = database_url or _cfg.database_url
        self._engine: AsyncEngine = create_async_engine(url, echo=False)
        self._session_factory = async_sessionmaker(self._engine, expire_on_commit=False)

    async def ensure_table(self) -> None:
        """Idempotent CREATE VIRTUAL TABLE IF NOT EXISTS."""
        try:
            async with self._engine.begin() as conn:
                await conn.execute(text(_CREATE_TABLE_SQL))
        except Exception as exc:
            raise ProviderUnavailableError(f"knowledge_lexical ensure_table failed: {exc}") from exc

    async def upsert(
        self,
        ids: list[str],
        texts: list[str],
        metadatas: list[dict[str, object]],
    ) -> None:
        """Delete-then-insert by chunk_id, one transaction per batch."""
        if not ids:
            return
        try:
            async with self._engine.begin() as conn:
                for chunk_id, chunk_text, meta in zip(ids, texts, metadatas, strict=False):
                    await conn.execute(
                        text("DELETE FROM knowledge_lexical WHERE chunk_id = :chunk_id"),
                        {"chunk_id": chunk_id},
                    )
                    # scope column holds "global" or the campaign UUID (row-level isolation
                    # equivalent to a per-collection Chroma store); campaign_id metadata is
                    # empty string for global-scoped chunks.
                    campaign_id = str(meta.get("campaign_id", "")) or ""
                    scope_value = campaign_id or "global"
                    await conn.execute(
                        text(
                            "INSERT INTO knowledge_lexical "
                            "(chunk_id, doc_id, scope, campaign_id, access_level, text) "
                            "VALUES (:chunk_id, :doc_id, :scope, :campaign_id, :access_level, :text)"
                        ),
                        {
                            "chunk_id": chunk_id,
                            "doc_id": str(meta.get("doc_id", "")),
                            "scope": scope_value,
                            "campaign_id": campaign_id,
                            "access_level": str(meta.get("access_level", "player_visible")),
                            "text": chunk_text,
                        },
                    )
        except Exception as exc:
            raise ProviderUnavailableError(f"knowledge_lexical upsert failed: {exc}") from exc

    async def query(
        self,
        query_text: str,
        scope: str,
        role: str,
        top_k: int,
    ) -> list[tuple[str, dict[str, Any], str]]:
        """Return [(chunk_id, metadata, text), ...] ordered best-first (BM25).

        Returns [] for zero query terms or zero matching rows — not an error.
        """
        match_query = _tokenize_to_match_query(query_text)
        _log.debug(
            "[lexical_store] query_text=%r match_query=%r scope=%s role=%s",
            query_text, match_query, scope, role,
        )
        if not match_query:
            return []
        try:
            async with self._engine.connect() as conn:
                result = await conn.execute(
                    text(
                        "SELECT chunk_id, doc_id, scope, campaign_id, access_level, text, "
                        "bm25(knowledge_lexical) AS score "
                        "FROM knowledge_lexical "
                        "WHERE knowledge_lexical MATCH :q "
                        "AND scope = :scope "
                        "AND (:role != 'player' OR access_level = 'player_visible') "
                        "ORDER BY score ASC "
                        "LIMIT :top_k"
                    ),
                    {"q": match_query, "scope": scope, "role": role, "top_k": top_k},
                )
                rows = result.fetchall()
        except Exception as exc:
            raise ProviderUnavailableError(f"knowledge_lexical query failed: {exc}") from exc

        ranked: list[tuple[str, dict[str, Any], str]] = []
        for row in rows:
            meta: dict[str, Any] = {
                "doc_id": row.doc_id,
                "scope": row.scope,
                "campaign_id": row.campaign_id,
                "access_level": row.access_level,
                "original_text": row.text,
            }
            ranked.append((str(row.chunk_id), meta, str(row.text)))
        return ranked

    async def delete_by_doc(self, doc_id: str) -> None:
        """Delete all rows for doc_id. No-op (no error) for an unknown doc_id."""
        try:
            async with self._engine.begin() as conn:
                await conn.execute(
                    text("DELETE FROM knowledge_lexical WHERE doc_id = :doc_id"),
                    {"doc_id": doc_id},
                )
        except Exception as exc:
            raise ProviderUnavailableError(f"knowledge_lexical delete_by_doc failed: {exc}") from exc

    async def get_all(self, scope: str) -> list[tuple[str, dict[str, Any], str]]:
        """Return all rows for a scope. Used only by backfill verification/debugging."""
        try:
            async with self._engine.connect() as conn:
                result = await conn.execute(
                    text(
                        "SELECT chunk_id, doc_id, scope, campaign_id, access_level, text "
                        "FROM knowledge_lexical WHERE scope = :scope"
                    ),
                    {"scope": scope},
                )
                rows = result.fetchall()
        except Exception as exc:
            raise ProviderUnavailableError(f"knowledge_lexical get_all failed: {exc}") from exc

        all_rows: list[tuple[str, dict[str, Any], str]] = []
        for row in rows:
            meta: dict[str, Any] = {
                "doc_id": row.doc_id,
                "scope": row.scope,
                "campaign_id": row.campaign_id,
                "access_level": row.access_level,
                "original_text": row.text,
            }
            all_rows.append((str(row.chunk_id), meta, str(row.text)))
        return all_rows
