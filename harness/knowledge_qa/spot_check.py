"""spot_check.py — Sample chunks for human fidelity classification (feature 015, US4).

Read-only. Samples chapter-opening and table-bearing chunks from the current
knowledge_global collection so a human can classify drop-cap completeness and
table coherence, comparing vision extraction against Docling extraction.

Usage:
    python harness/knowledge_qa/spot_check.py --extraction-mode docling
    python harness/knowledge_qa/spot_check.py --extraction-mode vision --doc-title ED4_Players_Guide

Classification is manual: read each printed sample and record your verdict
(complete_opening/drop_cap_gap for chapter openings; coherent_table/mangled_table
for tables) in specs/015-vision-extraction-benchmark/results.md.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "packages" / "rag"))
sys.path.insert(0, str(_REPO_ROOT / "packages" / "core"))

_log = logging.getLogger(__name__)

_TABLE_ROW_RE = re.compile(r"^\s*\|.+\|.*\|\s*$", re.MULTILINE)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sample chunks for fidelity spot-check")
    parser.add_argument(
        "--extraction-mode",
        required=True,
        choices=["docling", "vision", "text", "docling_text"],
        help="Extraction path the operator believes is currently loaded (cross-checked against metadata)",
    )
    parser.add_argument(
        "--doc-title",
        default="ED4_Players_Guide",
        help="KnowledgeDocument.title to resolve doc_id from (default: ED4_Players_Guide)",
    )
    parser.add_argument(
        "--min-openings",
        type=int,
        default=10,
        help="Minimum chapter-opening samples to print (default: 10, SC-006)",
    )
    parser.add_argument(
        "--min-tables",
        type=int,
        default=5,
        help="Minimum table-bearing samples to print (default: 5, SC-006)",
    )
    parser.add_argument(
        "--preview-chars",
        type=int,
        default=400,
        help="Characters of chunk text to print per sample (default: 400)",
    )
    return parser.parse_args()


async def _resolve_doc_id(title: str) -> str:
    from core.models import KnowledgeDocument
    from sqlalchemy import select
    from storage.sqlite.adapter import SQLiteBackend

    from core.config import settings

    backend = SQLiteBackend(settings.database_url)
    async with await backend.get_session() as db:
        result = await db.execute(
            select(KnowledgeDocument).where(KnowledgeDocument.title == title)
        )
        doc = result.scalar_one_or_none()
        if doc is None:
            raise SystemExit(f"No KnowledgeDocument found with title={title!r}")
        return str(doc.id)


def _is_chapter_opening(idx: int, breadcrumbs: list[str]) -> bool:
    """A chunk is a section-opening candidate if its breadcrumb differs from the previous chunk's."""
    if idx == 0:
        return bool(breadcrumbs[0])
    return breadcrumbs[idx] != breadcrumbs[idx - 1] and bool(breadcrumbs[idx])


def _has_table(text: str) -> bool:
    return bool(_TABLE_ROW_RE.search(text))


async def _run(args: argparse.Namespace) -> None:
    from rag.knowledge.vector_store import GLOBAL_COLLECTION, ChromaVectorStore

    doc_id = await _resolve_doc_id(args.doc_title)
    store = ChromaVectorStore()
    result = await store.get_all(GLOBAL_COLLECTION)

    ids = result.get("ids", [])
    metadatas = result.get("metadatas", [])

    rows = [
        (cid, meta)
        for cid, meta in zip(ids, metadatas, strict=False)
        if meta.get("doc_id") == doc_id
    ]
    if not rows:
        raise SystemExit(
            f"No chunks found for doc_id={doc_id} (title={args.doc_title!r}) "
            f"in collection {GLOBAL_COLLECTION!r}. Has the document been ingested?"
        )
    rows.sort(key=lambda r: r[1].get("chunk_index", 0))

    observed_modes = {meta.get("extraction_mode", "unknown") for _, meta in rows}
    print(f"\nspot_check  doc_title={args.doc_title}  doc_id={doc_id}  chunks={len(rows)}")
    print(f"            claimed extraction_mode={args.extraction_mode}  observed in metadata={sorted(observed_modes)}")
    if observed_modes != {args.extraction_mode}:
        _log.warning(
            "Observed extraction_mode(s) in collection metadata %s do not match "
            "the claimed --extraction-mode=%s. The collection may be stale or mixed — "
            "verify a clean-slate re-ingest happened before trusting this spot-check.",
            sorted(observed_modes), args.extraction_mode,
        )

    breadcrumbs = [meta.get("breadcrumb", "") for _, meta in rows]

    opening_samples = [
        (cid, meta) for i, (cid, meta) in enumerate(rows) if _is_chapter_opening(i, breadcrumbs)
    ][: max(args.min_openings, 10)]
    table_samples = [
        (cid, meta) for cid, meta in rows if _has_table(str(meta.get("original_text", "")))
    ][: max(args.min_tables, 5)]

    print(f"\n=== Chapter-opening candidates ({len(opening_samples)}, target >= {args.min_openings}) ===")
    for cid, meta in opening_samples:
        text = str(meta.get("original_text", ""))[: args.preview_chars]
        print(f"\n--- chunk_id={cid}  chunk_index={meta.get('chunk_index')}  breadcrumb={meta.get('breadcrumb')!r}")
        print(text)
        print("[Classify: complete_opening | drop_cap_gap]")

    print(f"\n=== Table-bearing candidates ({len(table_samples)}, target >= {args.min_tables}) ===")
    for cid, meta in table_samples:
        text = str(meta.get("original_text", ""))[: args.preview_chars]
        print(f"\n--- chunk_id={cid}  chunk_index={meta.get('chunk_index')}  breadcrumb={meta.get('breadcrumb')!r}")
        print(text)
        print("[Classify: coherent_table | mangled_table]")

    if len(opening_samples) < args.min_openings:
        _log.warning(
            "Only found %d chapter-opening candidates, target was %d (SC-006). "
            "Breadcrumb coverage may be sparse for this document.",
            len(opening_samples), args.min_openings,
        )
    if len(table_samples) < args.min_tables:
        _log.warning(
            "Only found %d table-bearing candidates, target was %d (SC-006).",
            len(table_samples), args.min_tables,
        )

    print(
        f"\nDone. Record classifications in specs/015-vision-extraction-benchmark/results.md "
        f"for extraction_mode={args.extraction_mode}."
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    args = _parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
