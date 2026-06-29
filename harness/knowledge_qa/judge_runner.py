"""judge_runner.py — Score unscored eval records using an LLM judge.

Usage:
    python harness/knowledge_qa/judge_runner.py \\
        --run-id <RUN_ID> \\
        [--db-path data/eval.db] \\
        [--force] \\
        [--limit N]

Required env vars:
    JUDGE_PROVIDER  (ollama | claude)
    JUDGE_MODEL     (e.g. llama3.1, claude-sonnet-4-6)

Optional env vars:
    OLLAMA_BASE_URL         (default: http://localhost:11434)
    ANTHROPIC_API_KEY       (required when JUDGE_PROVIDER=claude)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "packages" / "rag"))
sys.path.insert(0, str(_REPO_ROOT / "packages" / "core"))

_log = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Score eval records with an LLM judge")
    parser.add_argument(
        "--run-id",
        required=True,
        help="Run ID produced by eval_runner.py",
    )
    parser.add_argument(
        "--db-path",
        default="data/eval.db",
        help="Path to SQLite eval database (default: data/eval.db)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Re-score already-scored records",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Score at most N records (for smoke tests)",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        default=False,
        help="Print mean scores per dimension after scoring",
    )
    return parser.parse_args()


async def _run(args: argparse.Namespace) -> None:
    from rag.evaluation.factory import get_judge_provider
    from rag.evaluation.judge import JudgeEvaluator
    from rag.evaluation.models import EvaluationInput, JudgeStatus
    from rag.evaluation.store import EvaluationStore

    judge_provider_name = os.environ.get("JUDGE_PROVIDER", "").strip()
    judge_model_name = os.environ.get("JUDGE_MODEL", "").strip()

    try:
        provider = get_judge_provider(judge_provider_name, judge_model_name)
    except OSError as exc:
        _log.error("Environment error: %s", exc)
        sys.exit(1)

    evaluator = JudgeEvaluator(
        provider=provider,
        judge_provider_name=judge_provider_name,
        judge_model_name=judge_model_name,
    )

    store = EvaluationStore(args.db_path)
    await store.initialize()

    records = await store.get_unscored_by_run(run_id=args.run_id, force=args.force)
    if args.limit:
        records = list(records)[: args.limit]

    total = len(records)
    _log.info("run_id=%s records_to_score=%d force=%s", args.run_id, total, args.force)
    print(f"\njudge_runner  run_id={args.run_id}  records={total}  force={args.force}")
    print(f"              judge={judge_provider_name}/{judge_model_name}\n")

    scored = 0
    errors = 0
    parse_errors = 0
    no_response = 0

    for i, record in enumerate(records, 1):
        context_chunks: list[str] = json.loads(record.context_chunks_json or "[]")
        inp = EvaluationInput(
            record_id=record.id,
            run_id=record.run_id,
            question=record.question,
            reference_answer=record.reference_answer or "",
            generated_response=record.generated_response or "",
            context_chunks=context_chunks,
            context_truncated=bool(record.judge_context_truncated),
        )

        result = await evaluator.evaluate(inp)

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
            scored += 1
            status_char = "✓"
        elif result.status == JudgeStatus.error:
            update_kwargs["judge_error"] = result.error
            update_kwargs["judge_raw_response"] = result.raw_response
            errors += 1
            status_char = "E"
        elif result.status == JudgeStatus.parse_error:
            update_kwargs["judge_error"] = result.error
            update_kwargs["judge_raw_response"] = result.raw_response
            parse_errors += 1
            status_char = "P"
        else:  # no_response
            no_response += 1
            status_char = "N"

        await store.update_judge_result(record.id, **update_kwargs)

        agg_str = ""
        if result.score:
            agg_str = f"  agg={result.score.aggregate:.3f}"
        print(f"  [{i:3d}/{total}] {status_char}{agg_str}  {record.question[:55]}")

    counts = await store.count_by_status(run_id=args.run_id)
    print(f"\nDone.  run_id={args.run_id}")
    print(f"  scored={scored}  errors={errors}  parse_errors={parse_errors}  no_response={no_response}")
    print(f"  store counts: {counts}")

    # Coverage summary
    total_in_run = sum(counts.values())
    total_scored = counts.get("scored", 0)
    pct = 100 * total_scored / total_in_run if total_in_run else 0.0
    print(f"\nCoverage: {total_scored}/{total_in_run} scored ({pct:.1f}%)")

    # Per-dimension summary for scored records
    scored_records = await store.get_by_run_id(args.run_id)
    scored_rows = [r for r in scored_records if r.judge_status == "scored"]
    if scored_rows:

        def _mean_field(rows: list, attr: str) -> float:
            vals = [getattr(r, attr) for r in rows if getattr(r, attr) is not None]
            return sum(vals) / len(vals) if vals else 0.0

        print("\nMean scores (scored records):")
        print(f"  faithfulness:      {_mean_field(scored_rows, 'judge_faithfulness'):.3f}")
        print(f"  relevance:         {_mean_field(scored_rows, 'judge_relevance'):.3f}")
        print(f"  context_util:      {_mean_field(scored_rows, 'judge_context_utilization'):.3f}")
        print(f"  answer_correctness:{_mean_field(scored_rows, 'judge_answer_correctness'):.3f}")
        print(f"  aggregate:         {_mean_field(scored_rows, 'judge_aggregate'):.3f}")


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s %(message)s",
    )
    args = _parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
