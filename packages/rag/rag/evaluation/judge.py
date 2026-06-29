"""JudgeEvaluator — calls the judge LLM and parses structured scores."""

from __future__ import annotations

import logging
from pathlib import Path

from pydantic import ValidationError

from rag.evaluation.models import (
    EvaluationInput,
    JudgeResult,
    JudgeScore,
    JudgeStatus,
)

_log = logging.getLogger(__name__)

_DEFAULT_PROMPT_PATH = Path(__file__).parent / "prompts" / "judge_prompt.txt"
_DEFAULT_MAX_CONTEXT_CHARS = 8_000


class JudgeEvaluator:
    """Evaluates a generated response against three quality dimensions.

    Calls the judge LLM with a structured prompt and parses the JSON response
    into a JudgeScore. Two-step error handling distinguishes provider failures
    (status=error) from JSON/schema failures (status=parse_error).
    """

    def __init__(
        self,
        provider: object,
        judge_provider_name: str,
        judge_model_name: str,
        prompt_path: Path | None = None,
        max_context_chars: int = _DEFAULT_MAX_CONTEXT_CHARS,
    ) -> None:
        self._provider = provider
        self._judge_provider_name = judge_provider_name
        self._judge_model_name = judge_model_name
        self._max_context_chars = max_context_chars
        path = prompt_path or _DEFAULT_PROMPT_PATH
        self._prompt_template = path.read_text(encoding="utf-8")

    async def evaluate(self, inp: EvaluationInput) -> JudgeResult:
        """Score one question/response pair and return a JudgeResult."""
        if not inp.generated_response.strip():
            _log.debug("record_id=%d empty response → no_response", inp.record_id)
            return JudgeResult(
                record_id=inp.record_id,
                status=JudgeStatus.no_response,
                judge_provider=self._judge_provider_name,
                judge_model=self._judge_model_name,
            )

        context = "\n\n".join(inp.context_chunks)
        context_truncated = len(context) > self._max_context_chars
        if context_truncated:
            context = context[: self._max_context_chars]
            _log.debug(
                "record_id=%d context truncated to %d chars",
                inp.record_id,
                self._max_context_chars,
            )

        prompt = self._prompt_template.format(
            question=inp.question,
            reference_answer=inp.reference_answer,
            context=context,
            response=inp.generated_response,
        )

        try:
            score = await self._provider.generate_structured(prompt, JudgeScore)  # type: ignore[attr-defined]
        except ValidationError as exc:
            _log.warning("record_id=%d judge parse error: %s", inp.record_id, exc)
            return JudgeResult(
                record_id=inp.record_id,
                status=JudgeStatus.parse_error,
                error=str(exc),
                judge_provider=self._judge_provider_name,
                judge_model=self._judge_model_name,
            )
        except Exception as exc:
            _log.warning("record_id=%d judge provider error: %s", inp.record_id, exc)
            return JudgeResult(
                record_id=inp.record_id,
                status=JudgeStatus.error,
                error=str(exc),
                judge_provider=self._judge_provider_name,
                judge_model=self._judge_model_name,
            )

        _log.info(
            "record_id=%d scored faithfulness=%.3f relevance=%.3f "
            "context_util=%.3f correctness=%.3f agg=%.3f",
            inp.record_id,
            score.faithfulness.score,
            score.relevance.score,
            score.context_utilization.score,
            score.answer_correctness.score,
            score.aggregate,
        )
        return JudgeResult(
            record_id=inp.record_id,
            status=JudgeStatus.scored,
            score=score,
            judge_provider=self._judge_provider_name,
            judge_model=self._judge_model_name,
        )
