"""Unit tests for JudgeEvaluator (mocked provider — no real LLM calls)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest
from rag.evaluation.judge import JudgeEvaluator
from rag.evaluation.models import EvaluationInput, JudgeStatus


def _make_input(
    record_id: int = 1,
    question: str = "What is a dwarf?",
    generated_response: str = "A dwarf is a Name-giver race with a Strength bonus.",
    context_chunks: list[str] | None = None,
) -> EvaluationInput:
    return EvaluationInput(
        record_id=record_id,
        run_id="20260628-000000-testjudge",
        question=question,
        generated_response=generated_response,
        context_chunks=context_chunks or ["Dwarfs are a Name-giver race with STR bonus."],
        context_truncated=False,
    )


def _make_evaluator(provider: object) -> JudgeEvaluator:
    return JudgeEvaluator(
        provider=provider,
        judge_provider_name="ollama",
        judge_model_name="llama3.1",
    )


_VALID_JSON = json.dumps(
    {
        "faithfulness": {"score": 0.9, "rationale": "All claims supported"},
        "relevance": {"score": 0.8, "rationale": "Directly addresses question"},
        "context_utilization": {"score": 0.7, "rationale": "Good use of context"},
    }
)


@pytest.mark.asyncio
async def test_happy_path_returns_scored_result() -> None:
    mock_provider = AsyncMock()
    mock_provider.generate = AsyncMock(return_value=_VALID_JSON)
    evaluator = _make_evaluator(mock_provider)

    result = await evaluator.evaluate(_make_input())

    assert result.status == JudgeStatus.scored
    assert result.score is not None
    assert abs(result.score.faithfulness.score - 0.9) < 1e-9
    assert abs(result.score.relevance.score - 0.8) < 1e-9
    assert abs(result.score.context_utilization.score - 0.7) < 1e-9
    assert result.error is None
    assert result.raw_response is None
    assert result.judge_provider == "ollama"
    assert result.judge_model == "llama3.1"


@pytest.mark.asyncio
async def test_aggregate_computed_correctly() -> None:
    mock_provider = AsyncMock()
    mock_provider.generate = AsyncMock(return_value=_VALID_JSON)
    evaluator = _make_evaluator(mock_provider)

    result = await evaluator.evaluate(_make_input())

    assert result.score is not None
    expected = (0.9 + 0.8 + 0.7) / 3
    assert abs(result.score.aggregate - expected) < 1e-9


@pytest.mark.asyncio
async def test_empty_response_returns_no_response() -> None:
    mock_provider = AsyncMock()
    evaluator = _make_evaluator(mock_provider)

    result = await evaluator.evaluate(_make_input(generated_response="   "))

    assert result.status == JudgeStatus.no_response
    assert result.score is None
    mock_provider.generate.assert_not_called()


@pytest.mark.asyncio
async def test_whitespace_only_response_returns_no_response() -> None:
    mock_provider = AsyncMock()
    evaluator = _make_evaluator(mock_provider)

    result = await evaluator.evaluate(_make_input(generated_response="\n\t\n"))

    assert result.status == JudgeStatus.no_response


@pytest.mark.asyncio
async def test_provider_exception_returns_error_status() -> None:
    mock_provider = AsyncMock()
    mock_provider.generate = AsyncMock(side_effect=ConnectionError("Ollama unreachable"))
    evaluator = _make_evaluator(mock_provider)

    result = await evaluator.evaluate(_make_input())

    assert result.status == JudgeStatus.error
    assert result.score is None
    assert "Ollama unreachable" in (result.error or "")


@pytest.mark.asyncio
async def test_provider_exception_preserves_provider_fields() -> None:
    mock_provider = AsyncMock()
    mock_provider.generate = AsyncMock(side_effect=RuntimeError("timeout"))
    evaluator = _make_evaluator(mock_provider)

    result = await evaluator.evaluate(_make_input())

    assert result.judge_provider == "ollama"
    assert result.judge_model == "llama3.1"


@pytest.mark.asyncio
async def test_invalid_json_returns_parse_error() -> None:
    mock_provider = AsyncMock()
    mock_provider.generate = AsyncMock(return_value="not valid json at all")
    evaluator = _make_evaluator(mock_provider)

    result = await evaluator.evaluate(_make_input())

    assert result.status == JudgeStatus.parse_error
    assert result.raw_response == "not valid json at all"
    assert result.score is None


@pytest.mark.asyncio
async def test_json_wrong_schema_returns_parse_error() -> None:
    wrong_schema = json.dumps({"unexpected_key": "value"})
    mock_provider = AsyncMock()
    mock_provider.generate = AsyncMock(return_value=wrong_schema)
    evaluator = _make_evaluator(mock_provider)

    result = await evaluator.evaluate(_make_input())

    assert result.status == JudgeStatus.parse_error
    assert result.raw_response == wrong_schema


@pytest.mark.asyncio
async def test_context_truncated_when_exceeds_max_chars() -> None:
    mock_provider = AsyncMock()
    mock_provider.generate = AsyncMock(return_value=_VALID_JSON)

    evaluator = JudgeEvaluator(
        provider=mock_provider,
        judge_provider_name="ollama",
        judge_model_name="llama3.1",
        max_context_chars=10,
    )

    result = await evaluator.evaluate(
        _make_input(context_chunks=["A" * 100])
    )

    assert result.status == JudgeStatus.scored
    # Verify the prompt sent to provider used truncated context
    call_args = mock_provider.generate.call_args
    prompt_sent = call_args[0][0] if call_args[0] else call_args[1].get("prompt", "")
    assert "A" * 100 not in prompt_sent


@pytest.mark.asyncio
async def test_multiple_context_chunks_joined() -> None:
    mock_provider = AsyncMock()
    mock_provider.generate = AsyncMock(return_value=_VALID_JSON)
    evaluator = _make_evaluator(mock_provider)

    chunks = ["Chunk one.", "Chunk two.", "Chunk three."]
    await evaluator.evaluate(_make_input(context_chunks=chunks))

    call_args = mock_provider.generate.call_args
    prompt_sent = call_args[0][0] if call_args[0] else call_args[1].get("prompt", "")
    assert "Chunk one." in prompt_sent
    assert "Chunk two." in prompt_sent
    assert "Chunk three." in prompt_sent


@pytest.mark.asyncio
async def test_record_id_preserved_in_result() -> None:
    mock_provider = AsyncMock()
    mock_provider.generate = AsyncMock(return_value=_VALID_JSON)
    evaluator = _make_evaluator(mock_provider)

    result = await evaluator.evaluate(_make_input(record_id=42))

    assert result.record_id == 42
