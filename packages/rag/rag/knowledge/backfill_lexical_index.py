"""backfill_lexical_index.py — One-time migration: populate knowledge_lexical from Chroma.

Usage:
    python -m rag.knowledge.backfill_lexical_index [OPTIONS]

Populates the SQLite FTS5 lexical index for chunks ingested before hybrid search
existed, using already-stored Chroma metadata/text — no re-embedding, no re-ingestion
(FR-011, SC-004, SC-005). Safe to re-run at any time (upsert is idempotent per chunk_id).

See specs/014-hybrid-search/contracts/backfill-cli.md for the full contract.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
import uuid

from core.config import settings as _cfg
from core.errors import ProviderUnavailableError

from rag.knowledge.lexical_store import SQLiteLexicalStore
from rag.knowledge.vector_store import (
    GLOBAL_COLLECTION,
    ChromaVectorStore,
    campaign_collection,
)

_log = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill the knowledge_lexical FTS5 index from existing ChromaDB collections"
    )
    parser.add_argument(
        "--campaign-id",
        default=None,
        help="Restrict backfill to one campaign's collection plus the global collection",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report chunk counts per collection without writing anything",
    )
    parser.add_argument(
        "--chroma-path",
        default="./data/chroma",
        help="Path to the ChromaDB persistent store (default: ./data/chroma)",
    )
    return parser.parse_args()


async def _resolve_collections(
    store: ChromaVectorStore, campaign_id: str | None
) -> list[str]:
    """Always includes knowledge_global; adds one campaign collection or discovers all."""
    collections = [GLOBAL_COLLECTION]
    if campaign_id:
        collections.append(campaign_collection(campaign_id))
        return collections

    all_names = await store.list_collection_names()
    for name in sorted(all_names):
        if name.startswith("knowledge_") and name != GLOBAL_COLLECTION:
            collections.append(name)
    return collections


async def _backfill_collection(
    vector_store: ChromaVectorStore,
    lexical_store: SQLiteLexicalStore,
    collection_name: str,
    dry_run: bool,
    batch_size: int,
) -> int:
    data = await vector_store.get_all(collection_name)
    ids: list[str] = list(data.get("ids", []))
    metadatas: list[dict[str, object]] = list(data.get("metadatas", []))
    found = len(ids)
    _log.info("Processing %s — %d chunks found", collection_name, found)

    if dry_run or found == 0:
        _log.info("Processing %s — %d chunks written", collection_name, 0)
        return 0

    written = 0
    for i in range(0, found, batch_size):
        batch_ids = ids[i : i + batch_size]
        batch_metas = metadatas[i : i + batch_size]
        batch_texts = [str(meta.get("original_text", "")) for meta in batch_metas]
        await lexical_store.upsert(batch_ids, batch_texts, batch_metas)
        written += len(batch_ids)

    _log.info("Processing %s — %d chunks written", collection_name, written)
    return written


async def _run(args: argparse.Namespace) -> None:
    start = time.monotonic()

    campaign_id = args.campaign_id
    if campaign_id:
        try:
            uuid.UUID(campaign_id)
        except ValueError:
            _log.error("--campaign-id %r is not a valid UUID", campaign_id)
            sys.exit(1)

    vector_store = ChromaVectorStore(args.chroma_path)
    lexical_store = SQLiteLexicalStore()

    try:
        await lexical_store.ensure_table()
        collections = await _resolve_collections(vector_store, campaign_id)

        total_chunks = 0
        for collection_name in collections:
            written = await _backfill_collection(
                vector_store,
                lexical_store,
                collection_name,
                args.dry_run,
                _cfg.knowledge_enrich_batch_size,
            )
            total_chunks += written
    except ProviderUnavailableError as exc:
        _log.error("Backfill failed: %s", exc)
        sys.exit(1)

    elapsed = time.monotonic() - start
    print(f"Done. {len(collections)} collections, {total_chunks} chunks backfilled in {elapsed:.1f}s")


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s %(message)s",
    )
    args = _parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
