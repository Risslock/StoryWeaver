"""Integration tests for services.eval.run_evaluation."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from rag.knowledge.evaluator import EvalSummary, RetrievalEvalResult
from rag.knowledge.interface import KnowledgeChunk


def _make_chunk(text: str) -> KnowledgeChunk:
    return KnowledgeChunk(
        chunk_id="c1",
        doc_id="d1",
        doc_title="Doc",
        headline="H",
        summary="S",
        topic="T",
        access_level="player_visible",
        scope="global",
        text=text,
        rrf_score=1.0,
    )


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")


@pytest.fixture()
def tmp_jsonl(tmp_path: Path) -> Path:
    p = tmp_path / "tests.jsonl"
    _write_jsonl(p, [
        {"question": "What is a dragon?", "keywords": ["dragon"], "reference_answer": "A big lizard.", "category": "lore"},
        {"question": "Where do elves live?", "keywords": ["elf", "forest"], "reference_answer": "In forests.", "category": "lore"},
    ])
    return p


@pytest.fixture()
def campaign_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.mark.asyncio
async def test_result_count_matches_question_count(tmp_jsonl: Path, campaign_id: uuid.UUID) -> None:
    """Number of RetrievalEvalResults equals number of questions in the JSONL."""
    mock_chunks = [_make_chunk("dragon roams")]
    with patch("services.eval.ChromaKnowledgeRetriever") as MockRetriever:
        instance = MockRetriever.return_value
        instance.search = AsyncMock(return_value=mock_chunks)
        from services.eval import run_evaluation
        results, summary = await run_evaluation(str(tmp_jsonl), campaign_id, k=5)

    assert len(results) == 2
    assert summary.total_questions == 2


@pytest.mark.asyncio
async def test_eval_summary_k_matches_argument(tmp_jsonl: Path, campaign_id: uuid.UUID) -> None:
    mock_chunks = [_make_chunk("dragon")]
    with patch("services.eval.ChromaKnowledgeRetriever") as MockRetriever:
        instance = MockRetriever.return_value
        instance.search = AsyncMock(return_value=mock_chunks)
        from services.eval import run_evaluation
        _, summary = await run_evaluation(str(tmp_jsonl), campaign_id, k=10)

    assert summary.k == 10


@pytest.mark.asyncio
async def test_provider_unavailable_error_propagates(tmp_jsonl: Path, campaign_id: uuid.UUID) -> None:
    """ProviderUnavailableError from retriever propagates out of run_evaluation."""
    from core.errors import ProviderUnavailableError
    with patch("services.eval.ChromaKnowledgeRetriever") as MockRetriever:
        instance = MockRetriever.return_value
        instance.search = AsyncMock(side_effect=ProviderUnavailableError("Ollama down"))
        from services.eval import run_evaluation
        with pytest.raises(ProviderUnavailableError):
            await run_evaluation(str(tmp_jsonl), campaign_id, k=5)


@pytest.mark.asyncio
async def test_malformed_jsonl_raises_value_error(tmp_path: Path, campaign_id: uuid.UUID) -> None:
    bad_jsonl = tmp_path / "bad.jsonl"
    bad_jsonl.write_text('{"question": "Q?"}\n', encoding="utf-8")  # missing keywords etc.
    with patch("services.eval.ChromaKnowledgeRetriever"):
        from services.eval import run_evaluation
        with pytest.raises(ValueError, match="missing field"):
            await run_evaluation(str(bad_jsonl), campaign_id, k=5)


@pytest.mark.asyncio
async def test_all_metrics_are_floats(tmp_jsonl: Path, campaign_id: uuid.UUID) -> None:
    mock_chunks = [_make_chunk("dragon"), _make_chunk("elf lives in forest")]
    with patch("services.eval.ChromaKnowledgeRetriever") as MockRetriever:
        instance = MockRetriever.return_value
        instance.search = AsyncMock(return_value=mock_chunks)
        from services.eval import run_evaluation
        results, summary = await run_evaluation(str(tmp_jsonl), campaign_id, k=5)

    for r in results:
        assert isinstance(r.mrr, float)
        assert isinstance(r.ndcg, float)
        assert isinstance(r.recall_at_k, float)
        assert 0.0 <= r.mrr <= 1.0
        assert 0.0 <= r.ndcg <= 1.0
        assert 0.0 <= r.recall_at_k <= 1.0
