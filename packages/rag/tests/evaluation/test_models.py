"""Unit tests for evaluation Pydantic models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from rag.evaluation.models import DimensionScore, JudgeResult, JudgeScore, JudgeStatus


def test_dimension_score_valid() -> None:
    ds = DimensionScore(score=0.75, rationale="reasonable score")
    assert ds.score == 0.75
    assert ds.rationale == "reasonable score"


def test_dimension_score_clamped_above() -> None:
    ds = DimensionScore(score=1.5, rationale="too high")
    assert ds.score == 1.0


def test_dimension_score_clamped_below() -> None:
    ds = DimensionScore(score=-0.1, rationale="too low")
    assert ds.score == 0.0


def test_dimension_score_boundary_values() -> None:
    assert DimensionScore(score=0.0, rationale="zero").score == 0.0
    assert DimensionScore(score=1.0, rationale="one").score == 1.0


def test_dimension_score_empty_rationale_raises() -> None:
    with pytest.raises(ValidationError):
        DimensionScore(score=0.5, rationale="")


def test_dimension_score_whitespace_only_rationale_raises() -> None:
    with pytest.raises(ValidationError):
        DimensionScore(score=0.5, rationale="   ")


def test_judge_score_aggregate() -> None:
    score = JudgeScore(
        faithfulness=DimensionScore(score=0.8, rationale="good"),
        relevance=DimensionScore(score=0.6, rationale="ok"),
        context_utilization=DimensionScore(score=0.7, rationale="fine"),
    )
    expected = (0.8 + 0.6 + 0.7) / 3
    assert abs(score.aggregate - expected) < 1e-9


def test_judge_score_aggregate_all_ones() -> None:
    score = JudgeScore(
        faithfulness=DimensionScore(score=1.0, rationale="perfect"),
        relevance=DimensionScore(score=1.0, rationale="perfect"),
        context_utilization=DimensionScore(score=1.0, rationale="perfect"),
    )
    assert abs(score.aggregate - 1.0) < 1e-9


def test_judge_status_values() -> None:
    assert JudgeStatus.scored.value == "scored"
    assert JudgeStatus.error.value == "error"
    assert JudgeStatus.parse_error.value == "parse_error"
    assert JudgeStatus.no_response.value == "no_response"


def test_judge_result_scored() -> None:
    score = JudgeScore(
        faithfulness=DimensionScore(score=0.9, rationale="x"),
        relevance=DimensionScore(score=0.8, rationale="x"),
        context_utilization=DimensionScore(score=0.7, rationale="x"),
    )
    result = JudgeResult(
        record_id=1,
        status=JudgeStatus.scored,
        score=score,
        judge_provider="ollama",
        judge_model="llama3.1",
    )
    assert result.status == JudgeStatus.scored
    assert result.score is not None
    assert result.error is None
    assert result.raw_response is None


def test_judge_result_error() -> None:
    result = JudgeResult(
        record_id=2,
        status=JudgeStatus.error,
        error="Cannot reach Ollama",
        judge_provider="ollama",
        judge_model="llama3.1",
    )
    assert result.status == JudgeStatus.error
    assert result.score is None
    assert result.error == "Cannot reach Ollama"


def test_judge_result_parse_error() -> None:
    result = JudgeResult(
        record_id=3,
        status=JudgeStatus.parse_error,
        raw_response="not json",
        judge_provider="ollama",
        judge_model="llama3.1",
    )
    assert result.status == JudgeStatus.parse_error
    assert result.raw_response == "not json"
