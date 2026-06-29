"""eval_runner.py — Generate answers for a JSONL question set and store unscored records.

Usage:
    python harness/knowledge_qa/eval_runner.py \\
        --questions harness/knowledge_qa/rag_gold_standard.jsonl \\
        --campaign-id <UUID> \\
        --role gm \\
        [--run-id <RUN_ID>] \\
        [--db-path data/eval.db] \\
        [--limit N]

Required env vars (same as knowledge Q&A service):
    KNOWLEDGE_EMBED_PROVIDER, KNOWLEDGE_EMBED_MODEL, KNOWLEDGE_LLM_MODEL

Writes one ResponseEvalRecord per question with judge_status="unscored".
Run judge_runner.py next to score the records.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

# Allow imports from apps/web (ask_question) and packages/rag
_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "apps" / "web"))
sys.path.insert(0, str(_REPO_ROOT / "packages" / "rag"))
sys.path.insert(0, str(_REPO_ROOT / "packages" / "core"))

_log = logging.getLogger(__name__)


def _make_run_id() -> str:
    now = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    uid8 = str(uuid.uuid4()).replace("-", "")[:8]
    return f"{now}-{uid8}"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate answers and write unscored eval records")
    parser.add_argument(
        "--questions",
        required=True,
        help="Path to JSONL file with question records",
    )
    parser.add_argument(
        "--campaign-id",
        required=True,
        help="Campaign UUID to scope the knowledge retrieval",
    )
    parser.add_argument(
        "--role",
        required=True,
        help="Player role (e.g. 'gm', 'player')",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="Optional run ID (auto-generated if omitted)",
    )
    parser.add_argument(
        "--db-path",
        default="data/eval.db",
        help="Path to SQLite eval database (default: data/eval.db)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Process at most N questions (for quick smoke tests)",
    )
    return parser.parse_args()


def _load_questions(path: str) -> list[dict]:
    questions = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                questions.append(json.loads(line))
    return questions


async def _run(args: argparse.Namespace) -> None:
    from rag.evaluation.store import EvaluationStore
    from services.knowledge import ask_question  # type: ignore[import-untyped]

    run_id = args.run_id or _make_run_id()
    campaign_id_str = args.campaign_id
    # Validate UUID
    try:
        campaign_uuid = uuid.UUID(campaign_id_str)
    except ValueError:
        _log.error("--campaign-id %r is not a valid UUID", campaign_id_str)
        sys.exit(1)

    questions = _load_questions(args.questions)
    if args.limit:
        questions = questions[: args.limit]

    store = EvaluationStore(args.db_path)
    await store.initialize()

    _log.info("run_id=%s questions=%d campaign_id=%s role=%s", run_id, len(questions), campaign_id_str, args.role)
    print(f"\neval_runner  run_id={run_id}  questions={len(questions)}")
    print(f"             campaign_id={campaign_id_str}  role={args.role}\n")

    ok = 0
    empty = 0
    errors = 0

    for i, q in enumerate(questions, 1):
        question_text = q.get("question", "")
        category = q.get("category")
        reference_answer = q.get("reference_answer", "")

        try:
            answer, chunks = await ask_question(question_text, campaign_uuid, args.role)
        except Exception as exc:
            _log.warning("[%d/%d] ask_question failed: %s", i, len(questions), exc)
            answer = ""
            chunks = []
            errors += 1

        if not answer.strip():
            empty += 1

        context_chunks_json = json.dumps([c.text for c in chunks] if chunks else [])

        await store.write_record(
            run_id=run_id,
            campaign_id=campaign_id_str,
            role=args.role,
            question=question_text,
            reference_answer=reference_answer,
            question_source="gold_standard",
            question_category=category,
            generated_response=answer,
            context_chunks_json=context_chunks_json,
        )

        status_char = "." if answer.strip() else "E"
        print(f"  [{i:3d}/{len(questions)}] {status_char}  {question_text[:60]}")
        ok += 1

    counts = await store.count_by_status(run_id=run_id)
    print(f"\nDone.  run_id={run_id}")
    print(f"  written={ok}  empty_responses={empty}  ask_errors={errors}")
    print(f"  store counts: {counts}")
    print(f"\nNext step:  python harness/knowledge_qa/judge_runner.py --run-id {run_id}")


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s %(message)s",
    )
    args = _parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
