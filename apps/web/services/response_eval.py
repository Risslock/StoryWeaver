"""Response quality evaluation service — bridge between UI and judge pipeline."""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass

from rag.evaluation.models import EvaluationInput, JudgeStatus

_log = logging.getLogger(__name__)


@dataclass
class ResponseEvalRow:
    """One row in the judge results table."""

    index: int
    question: str
    faithfulness: float | str
    relevance: float | str
    context_utilization: float | str
    answer_correctness: float | str
    aggregate: float | str
    status: str

    def to_list(self) -> list:
        """Return values in table column order."""
        return [
            self.index,
            self.question,
            self.faithfulness,
            self.relevance,
            self.context_utilization,
            self.answer_correctness,
            self.aggregate,
            self.status,
        ]


@dataclass
class ResponseEvalSummary:
    """Aggregate statistics for a completed judge run."""

    total: int
    scored: int
    error: int
    parse_error: int
    no_response: int
    mean_faithfulness: float | None
    mean_relevance: float | None
    mean_context_utilization: float | None
    mean_answer_correctness: float | None
    mean_aggregate: float | None
    run_id: str


async def run_response_eval_question(
    question: str,
    category: str | None,
    campaign_id: uuid.UUID,
    role: str,
    judge_evaluator: object,
    store: object,
    run_id: str,
    index: int,
    reference_answer: str = "",
) -> ResponseEvalRow:
    """Run one question through the full eval pipeline and return a result row.

    1. Call ask_question() to generate an answer + retrieve context chunks.
    2. Write an unscored ResponseEvalRecord to the store.
    3. Call judge_evaluator.evaluate() to score the response.
    4. Update the store record with judge results.
    5. Return a ResponseEvalRow for the UI table.
    """
    from rag.evaluation.judge import JudgeEvaluator
    from rag.evaluation.store import EvaluationStore

    from services.knowledge import ask_question

    _store: EvaluationStore = store  # type: ignore[assignment]
    _evaluator: JudgeEvaluator = judge_evaluator  # type: ignore[assignment]

    # Step 1: generate answer
    try:
        answer, chunks = await ask_question(question, campaign_id, role)
    except Exception as exc:
        _log.error("ask_question failed for %r: %s", question[:60], exc)
        answer = ""
        chunks = []

    context_chunks_json = json.dumps([c.text for c in chunks] if chunks else [])

    # Step 2: persist unscored record
    record = await _store.write_record(
        run_id=run_id,
        campaign_id=str(campaign_id),
        role=role,
        question=question,
        reference_answer=reference_answer,
        question_source="ui",
        question_category=category,
        generated_response=answer,
        context_chunks_json=context_chunks_json,
    )

    # Step 3: judge
    context_chunks_list: list[str] = [c.text for c in chunks] if chunks else []
    inp = EvaluationInput(
        record_id=record.id,
        run_id=run_id,
        question=question,
        reference_answer=reference_answer,
        generated_response=answer,
        context_chunks=context_chunks_list,
        context_truncated=False,
    )
    result = await _evaluator.evaluate(inp)

    # Step 4: update store
    update_kwargs: dict = {
        "judge_status": result.status.value,
        "judge_provider": result.judge_provider,
        "judge_model": result.judge_model,
    }
    if result.status == JudgeStatus.scored and result.score is not None:
        s = result.score
        update_kwargs.update(
            judge_faithfulness=s.faithfulness.score,
            judge_faithfulness_rationale=s.faithfulness.rationale,
            judge_relevance=s.relevance.score,
            judge_relevance_rationale=s.relevance.rationale,
            judge_context_utilization=s.context_utilization.score,
            judge_context_utilization_rationale=s.context_utilization.rationale,
            judge_answer_correctness=s.answer_correctness.score,
            judge_answer_correctness_rationale=s.answer_correctness.rationale,
            judge_aggregate=s.aggregate,
        )
    elif result.error:
        update_kwargs["judge_error"] = result.error
        update_kwargs["judge_raw_response"] = result.raw_response
    await _store.update_judge_result(record.id, **update_kwargs)

    # Step 5: build row
    if result.status == JudgeStatus.scored and result.score is not None:
        s = result.score
        return ResponseEvalRow(
            index=index,
            question=question,
            faithfulness=round(s.faithfulness.score, 3),
            relevance=round(s.relevance.score, 3),
            context_utilization=round(s.context_utilization.score, 3),
            answer_correctness=round(s.answer_correctness.score, 3),
            aggregate=round(s.aggregate, 3),
            status="scored",
        )

    status_label = result.status.value
    return ResponseEvalRow(
        index=index,
        question=question,
        faithfulness="—",
        relevance="—",
        context_utilization="—",
        answer_correctness="—",
        aggregate="—",
        status=status_label,
    )


def build_judge_summary(
    rows: list[ResponseEvalRow], run_id: str
) -> ResponseEvalSummary:
    """Compute aggregate statistics from a list of ResponseEvalRows."""
    scored_rows = [r for r in rows if r.status == "scored"]
    error_rows = [r for r in rows if r.status == "error"]
    parse_error_rows = [r for r in rows if r.status == "parse_error"]
    no_response_rows = [r for r in rows if r.status == "no_response"]

    def _mean(values: list[float | str]) -> float | None:
        nums = [v for v in values if isinstance(v, (int, float))]
        return sum(nums) / len(nums) if nums else None

    return ResponseEvalSummary(
        total=len(rows),
        scored=len(scored_rows),
        error=len(error_rows),
        parse_error=len(parse_error_rows),
        no_response=len(no_response_rows),
        mean_faithfulness=_mean([r.faithfulness for r in scored_rows]),
        mean_relevance=_mean([r.relevance for r in scored_rows]),
        mean_context_utilization=_mean([r.context_utilization for r in scored_rows]),
        mean_answer_correctness=_mean([r.answer_correctness for r in scored_rows]),
        mean_aggregate=_mean([r.aggregate for r in scored_rows]),
        run_id=run_id,
    )
