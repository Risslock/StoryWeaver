"""Pydantic models for LLM-as-judge response evaluation."""

from __future__ import annotations

import logging
from enum import StrEnum

from pydantic import BaseModel, field_validator

_log = logging.getLogger(__name__)


class DimensionScore(BaseModel):
    """Score + rationale for one evaluation dimension."""

    score: float
    rationale: str

    @field_validator("score")
    @classmethod
    def clamp_score(cls, v: float) -> float:
        clamped = max(0.0, min(1.0, v))
        if clamped != v:
            _log.warning("DimensionScore.score %r clamped to %r", v, clamped)
        return clamped

    @field_validator("rationale")
    @classmethod
    def require_rationale(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("rationale must be a non-empty string")
        return v


class JudgeScore(BaseModel):
    """Structured output parsed from the judge LLM response."""

    faithfulness: DimensionScore
    relevance: DimensionScore
    context_utilization: DimensionScore
    answer_correctness: DimensionScore

    @property
    def aggregate(self) -> float:
        return (
            self.faithfulness.score
            + self.relevance.score
            + self.context_utilization.score
            + self.answer_correctness.score
        ) / 4


class JudgeStatus(StrEnum):
    scored = "scored"
    error = "error"
    parse_error = "parse_error"
    no_response = "no_response"


class EvaluationInput(BaseModel):
    """In-memory representation passed to JudgeEvaluator."""

    record_id: int
    run_id: str
    question: str
    reference_answer: str
    generated_response: str
    context_chunks: list[str]
    context_truncated: bool


class JudgeResult(BaseModel):
    """Complete judge output for one EvaluationRecord."""

    record_id: int
    status: JudgeStatus
    score: JudgeScore | None = None
    error: str | None = None
    raw_response: str | None = None
    judge_provider: str
    judge_model: str
