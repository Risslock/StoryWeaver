"""Live-Ollama integration test for hybrid search (feature 014).

Ingests a small fixture document containing a literal exact term, then confirms
that with HYBRID_SEARCH_ENABLED=true the chunk containing that term is returned
with "lexical" in matched_signals. Auto-skips when Ollama is unreachable, mirroring
harness/knowledge_qa/test_integration.py's pattern.
"""

from __future__ import annotations

import os
import urllib.error
import urllib.request
import uuid
from unittest.mock import AsyncMock, patch

import pytest

_EXACT_TERM = "Grimoire of Xanthus"

_FIXTURE_TEXT = f"""# Arcane Lore

## The {_EXACT_TERM}

The {_EXACT_TERM} is a legendary spellbook said to contain the first
recorded incantations of the elder magi. Only three copies are known to exist.

## Unrelated Section

This section discusses mundane trade goods and caravan routes, with no
connection to spellbooks or magical artifacts.
"""


@pytest.fixture(scope="module")
def ollama_available() -> None:
    base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    try:
        with urllib.request.urlopen(f"{base_url}/api/tags", timeout=5):
            pass
    except (urllib.error.URLError, OSError):
        pytest.skip(f"Ollama not reachable at {base_url} — skipping hybrid integration test")


@pytest.mark.asyncio
async def test_exact_term_surfaced_via_lexical_signal(
    ollama_available: None, tmp_path: object
) -> None:
    from core.config import settings as _cfg
    from rag.knowledge.pipeline import IngestionPipeline
    from rag.knowledge.retriever import ChromaKnowledgeRetriever

    tmp_chroma = str(tmp_path / "chroma")
    tmp_db_url = f"sqlite+aiosqlite:///{tmp_path}/{uuid.uuid4().hex}.db"
    fixture_path = tmp_path / "arcane_lore.md"
    fixture_path.write_text(_FIXTURE_TEXT, encoding="utf-8")

    doc_id = str(uuid.uuid4())

    with (
        patch("core.config.settings.database_url", tmp_db_url),
        patch(
            "rag.knowledge.pipeline.IngestionPipeline._get_doc_title",
            new=AsyncMock(return_value="Arcane Lore"),
        ),
        patch(
            "rag.knowledge.pipeline.IngestionPipeline._set_status",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "rag.knowledge.pipeline.IngestionPipeline._set_progress",
            new=AsyncMock(return_value=None),
        ),
    ):
        pipeline = IngestionPipeline(chroma_path=tmp_chroma)
        await pipeline.run(
            doc_id=doc_id,
            file_path=str(fixture_path),
            format="markdown",
            scope="global",
            campaign_id=None,
        )

        with patch.object(_cfg, "hybrid_search_enabled", True):
            retriever = ChromaKnowledgeRetriever(chroma_path=tmp_chroma)
            chunks = await retriever.search(
                query=f"What does the {_EXACT_TERM} do?",
                campaign_id="",
                role="gm",
                top_k=10,
            )

    matching = [c for c in chunks if _EXACT_TERM in c.text]
    assert matching, (
        f"Expected a chunk containing {_EXACT_TERM!r} in results, "
        f"got: {[c.text[:60] for c in chunks]}"
    )
    assert "lexical" in matching[0].matched_signals, (
        f"Expected 'lexical' in matched_signals, got: {matching[0].matched_signals}"
    )
