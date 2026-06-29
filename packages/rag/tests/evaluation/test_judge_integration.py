"""Integration tests for JudgeEvaluator using a real Ollama instance.

These tests require:
    JUDGE_PROVIDER=ollama
    JUDGE_MODEL=<model name>
    OLLAMA_BASE_URL (default: http://localhost:11434)

They are auto-skipped when Ollama is unreachable.
"""

from __future__ import annotations

import os
import urllib.error
import urllib.request

import pytest
from rag.evaluation.factory import get_judge_provider
from rag.evaluation.judge import JudgeEvaluator
from rag.evaluation.models import EvaluationInput, JudgeStatus


def _ollama_reachable() -> bool:
    base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    try:
        with urllib.request.urlopen(f"{base_url}/api/tags", timeout=5):
            return True
    except (urllib.error.URLError, OSError):
        return False


def _judge_env_configured() -> bool:
    return bool(os.environ.get("JUDGE_PROVIDER")) and bool(os.environ.get("JUDGE_MODEL"))


pytestmark = pytest.mark.skipif(
    not _ollama_reachable() or not _judge_env_configured(),
    reason="Ollama unreachable or JUDGE_PROVIDER/JUDGE_MODEL not set",
)


def _make_evaluator() -> JudgeEvaluator:
    provider_name = os.environ.get("JUDGE_PROVIDER", "ollama")
    model_name = os.environ.get("JUDGE_MODEL", "llama3.1")
    provider = get_judge_provider(provider_name, model_name)
    return JudgeEvaluator(
        provider=provider,
        judge_provider_name=provider_name,
        judge_model_name=model_name,
    )


def _make_input(record_id: int = 1, response: str = "") -> EvaluationInput:
    return EvaluationInput(
        record_id=record_id,
        run_id="integration-test",
        question="What is a dwarf in Earthdawn 4th Edition?",
        reference_answer="A dwarf is one of the eight Name-giver races in Earthdawn 4E with a Strength bonus.",
        generated_response=response,
        context_chunks=[
            "Dwarfs are one of the eight Name-giver races in Earthdawn. "
            "They receive a +3 bonus to Strength and -1 to Charisma.",
        ],
        context_truncated=False,
    )


@pytest.mark.asyncio
async def test_real_judge_returns_scored_status() -> None:
    evaluator = _make_evaluator()
    response = "A dwarf is a Name-giver race in Earthdawn 4E with a Strength bonus."
    result = await evaluator.evaluate(_make_input(response=response))
    assert result.status == JudgeStatus.scored
    assert result.score is not None
    assert 0.0 <= result.score.faithfulness.score <= 1.0
    assert 0.0 <= result.score.relevance.score <= 1.0
    assert 0.0 <= result.score.context_utilization.score <= 1.0
    assert 0.0 <= result.score.answer_correctness.score <= 1.0
    assert 0.0 <= result.score.aggregate <= 1.0


@pytest.mark.asyncio
async def test_real_judge_empty_response_no_response_status() -> None:
    evaluator = _make_evaluator()
    result = await evaluator.evaluate(_make_input(response=""))
    assert result.status == JudgeStatus.no_response


@pytest.mark.asyncio
async def test_real_judge_rationales_are_nonempty() -> None:
    evaluator = _make_evaluator()
    response = "Dwarfs have a Strength bonus and are Name-givers."
    result = await evaluator.evaluate(_make_input(response=response))
    if result.status == JudgeStatus.scored and result.score is not None:
        assert result.score.faithfulness.rationale.strip()
        assert result.score.relevance.rationale.strip()
        assert result.score.context_utilization.rationale.strip()
        assert result.score.answer_correctness.rationale.strip()
