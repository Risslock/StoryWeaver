"""Unit tests for JudgeEvaluator (mocked provider — no real LLM calls)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError
from rag.evaluation.judge import JudgeEvaluator
from rag.evaluation.models import DimensionScore, EvaluationInput, JudgeScore, JudgeStatus


def _make_input(
    record_id: int = 1,
    question: str = "What is a dwarf?",
    reference_answer: str = "A dwarf is a Name-giver race with a Strength bonus.",
    generated_response: str = "A dwarf is a Name-giver race with a Strength bonus.",
    context_chunks: list[str] | None = None,
) -> EvaluationInput:
    return EvaluationInput(
        record_id=record_id,
        run_id="20260628-000000-testjudge",
        question=question,
        reference_answer=reference_answer,
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


def _valid_score() -> JudgeScore:
    return JudgeScore(
        faithfulness=DimensionScore(score=0.9, rationale="All claims supported"),
        relevance=DimensionScore(score=0.8, rationale="Directly addresses question"),
        context_utilization=DimensionScore(score=0.7, rationale="Good use of context"),
        answer_correctness=DimensionScore(score=0.85, rationale="Matches reference answer"),
    )


def _make_mock(return_value: object = None, side_effect: object = None) -> AsyncMock:
    """Return an AsyncMock with generate_structured pre-configured."""
    mock = AsyncMock()
    if side_effect is not None:
        mock.generate_structured = AsyncMock(side_effect=side_effect)
    else:
        mock.generate_structured = AsyncMock(return_value=return_value or _valid_score())
    return mock


@pytest.mark.asyncio
async def test_happy_path_returns_scored_result() -> None:
    evaluator = _make_evaluator(_make_mock())

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
    evaluator = _make_evaluator(_make_mock())

    result = await evaluator.evaluate(_make_input())

    assert result.score is not None
    expected = (0.9 + 0.8 + 0.7 + 0.85) / 4
    assert abs(result.score.aggregate - expected) < 1e-9


@pytest.mark.asyncio
async def test_empty_response_returns_no_response() -> None:
    mock_provider = _make_mock()
    evaluator = _make_evaluator(mock_provider)

    result = await evaluator.evaluate(_make_input(generated_response="   "))

    assert result.status == JudgeStatus.no_response
    assert result.score is None
    mock_provider.generate_structured.assert_not_called()


@pytest.mark.asyncio
async def test_whitespace_only_response_returns_no_response() -> None:
    evaluator = _make_evaluator(_make_mock())

    result = await evaluator.evaluate(_make_input(generated_response="\n\t\n"))

    assert result.status == JudgeStatus.no_response


@pytest.mark.asyncio
async def test_provider_exception_returns_error_status() -> None:
    evaluator = _make_evaluator(_make_mock(side_effect=ConnectionError("Ollama unreachable")))

    result = await evaluator.evaluate(_make_input())

    assert result.status == JudgeStatus.error
    assert result.score is None
    assert "Ollama unreachable" in (result.error or "")


@pytest.mark.asyncio
async def test_provider_exception_preserves_provider_fields() -> None:
    evaluator = _make_evaluator(_make_mock(side_effect=RuntimeError("timeout")))

    result = await evaluator.evaluate(_make_input())

    assert result.judge_provider == "ollama"
    assert result.judge_model == "llama3.1"


@pytest.mark.asyncio
async def test_validation_error_returns_parse_error() -> None:
    """generate_structured raises ValidationError on schema mismatch → parse_error."""
    try:
        # Force a real ValidationError from pydantic
        JudgeScore.model_validate({"unexpected_key": "value"})
    except ValidationError as exc:
        ve = exc

    evaluator = _make_evaluator(_make_mock(side_effect=ve))

    result = await evaluator.evaluate(_make_input())

    assert result.status == JudgeStatus.parse_error
    assert result.score is None
    assert result.error is not None


@pytest.mark.asyncio
async def test_context_truncated_when_exceeds_max_chars() -> None:
    mock_provider = _make_mock()

    evaluator = JudgeEvaluator(
        provider=mock_provider,
        judge_provider_name="ollama",
        judge_model_name="llama3.1",
        max_context_chars=10,
    )

    result = await evaluator.evaluate(_make_input(context_chunks=["A" * 100]))

    assert result.status == JudgeStatus.scored
    call_args = mock_provider.generate_structured.call_args
    prompt_sent = call_args[0][0] if call_args[0] else call_args[1].get("prompt", "")
    assert "A" * 100 not in prompt_sent


@pytest.mark.asyncio
async def test_multiple_context_chunks_joined() -> None:
    mock_provider = _make_mock()
    evaluator = _make_evaluator(mock_provider)

    chunks = ["Chunk one.", "Chunk two.", "Chunk three."]
    await evaluator.evaluate(_make_input(context_chunks=chunks))

    call_args = mock_provider.generate_structured.call_args
    prompt_sent = call_args[0][0] if call_args[0] else call_args[1].get("prompt", "")
    assert "Chunk one." in prompt_sent
    assert "Chunk two." in prompt_sent
    assert "Chunk three." in prompt_sent


@pytest.mark.asyncio
async def test_record_id_preserved_in_result() -> None:
    evaluator = _make_evaluator(_make_mock())

    result = await evaluator.evaluate(_make_input(record_id=42))

    assert result.record_id == 42
