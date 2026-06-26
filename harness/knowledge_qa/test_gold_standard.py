"""Gold standard benchmark harness for chunking strategy evaluation.

Loads rag_gold_standard.jsonl (118 questions), runs each through ChromaKnowledgeRetriever
with scope="global" and role="gm", computes MRR / nDCG / Recall@10, and appends a
ChunkBenchmarkResult record to benchmark_results.jsonl.

Auto-skips when Ollama is unreachable (same pattern as test_integration.py).
"""

from __future__ import annotations

import datetime
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from rag.knowledge.evaluator import EvalSummary, aggregate_results, evaluate_question
from rag.knowledge.test_questions import TestQuestion, load_test_questions

GOLD_STANDARD_PATH = os.environ.get(
    "GOLD_STANDARD_PATH",
    str(Path(__file__).parent / "rag_gold_standard.jsonl"),
)
BENCHMARK_RESULTS_PATH = Path(__file__).parent / "benchmark_results.jsonl"


def _ollama_reachable() -> bool:
    base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    try:
        with urllib.request.urlopen(f"{base_url}/api/tags", timeout=5):
            return True
    except (urllib.error.URLError, OSError):
        return False


async def run_gold_standard_benchmark(k: int = 10) -> EvalSummary:
    """Run all gold standard questions through the retriever and return aggregate metrics.

    Appends a ChunkBenchmarkResult JSON line to benchmark_results.jsonl.
    Skips via pytest.skip() if Ollama is unreachable.
    """
    if not _ollama_reachable():
        pytest.skip("Ollama not reachable — skipping gold standard benchmark")

    from rag.knowledge.chunker import create_chunker
    from rag.knowledge.retriever import ChromaKnowledgeRetriever

    questions: list[TestQuestion] = load_test_questions(GOLD_STANDARD_PATH)
    retriever = ChromaKnowledgeRetriever()

    eval_results = []
    for test in questions:
        chunks = await retriever.search(
            query=test.question,
            campaign_id="",
            role="gm",
            top_k=k,
        )
        result = evaluate_question(test, chunks, k)
        eval_results.append(result)

    summary = aggregate_results(eval_results)

    print("\n=== Per-Category Results ===")
    print(f"{'Category':<16}{'Questions':<11}{'MRR':<8}{'nDCG':<8}{'Recall@' + str(k)}")
    for cat, metrics in summary.category_scores.items():
        print(
            f"{cat:<16}{metrics.question_count:<11}"
            f"{metrics.mean_mrr:<8.3f}{metrics.mean_ndcg:<8.3f}{metrics.mean_recall_at_k:.3f}"
        )
    print("=== Global ===")
    print(
        f"Total: {summary.total_questions}   "
        f"MRR: {summary.mean_mrr:.3f}   "
        f"nDCG: {summary.mean_ndcg:.3f}   "
        f"Recall@{k}: {summary.mean_recall_at_k:.3f}"
    )

    strategy = create_chunker().strategy_name
    category_scores_serialized = {
        cat: metrics.model_dump()
        for cat, metrics in summary.category_scores.items()
    }
    record = {
        "strategy": strategy,
        "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
        "gold_standard_path": GOLD_STANDARD_PATH,
        "k": k,
        "total_questions": summary.total_questions,
        "mean_mrr": summary.mean_mrr,
        "mean_ndcg": summary.mean_ndcg,
        "mean_recall_at_k": summary.mean_recall_at_k,
        "notes": "",
        "category_scores": category_scores_serialized,
    }
    with open(BENCHMARK_RESULTS_PATH, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")

    return summary


def _load_benchmark_records(jsonl_path: str | None = None) -> list[dict]:
    """Load all benchmark records from the JSONL file."""
    path = Path(jsonl_path) if jsonl_path else BENCHMARK_RESULTS_PATH
    if not path.exists():
        return []
    records: list[dict] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def _resolve_selector(records: list[dict], selector: int | str) -> dict:
    """Resolve a selector (integer index or timestamp prefix) to a benchmark record."""
    if not records:
        raise ValueError("No benchmark records found")
    if isinstance(selector, int):
        try:
            return records[selector]
        except IndexError:
            available = [r.get("timestamp", "?") for r in records]
            raise ValueError(
                f"Selector {selector} out of range. Available records: {available}"
            )
    # String: match timestamp prefix
    for record in records:
        if record.get("timestamp", "").startswith(selector):
            return record
    available = [r.get("timestamp", "?") for r in records]
    raise ValueError(
        f"Selector '{selector}' did not match any record timestamp. Available records: {available}"
    )


def compare_benchmark_runs(
    selector_a: int | str,
    selector_b: int | str,
    jsonl_path: str | None = None,
) -> None:
    """Print a per-category diff table comparing two benchmark runs.

    Selectors can be integer indices (negative supported) or timestamp prefix strings.
    """
    records = _load_benchmark_records(jsonl_path)
    rec_a = _resolve_selector(records, selector_a)
    rec_b = _resolve_selector(records, selector_b)

    cats_a: dict = rec_a.get("category_scores", {})
    cats_b: dict = rec_b.get("category_scores", {})
    all_cats = sorted(set(cats_a) | set(cats_b))

    def _fmt(val: object) -> str:
        return f"{val:.4f}" if isinstance(val, float | int) else "N/A"

    def _delta(a: object, b: object) -> str:
        if not isinstance(a, float | int) or not isinstance(b, float | int):
            return "N/A"
        d = b - a
        return f"+{d:.4f}" if d >= 0 else f"{d:.4f}"

    header = (
        f"{'Category':<16} {'MRR-A':>7} {'MRR-B':>7} {'ΔMRR':>8}"
        f" {'nDCG-A':>7} {'nDCG-B':>7} {'ΔnDCG':>8}"
        f" {'Rcl-A':>7} {'Rcl-B':>7} {'ΔRecall':>8}"
    )
    separator = "-" * len(header)
    print(f"\nRun A: {rec_a.get('timestamp', '?')}  |  Run B: {rec_b.get('timestamp', '?')}")
    print(separator)
    print(header)
    print(separator)

    def _row(label: str, a_scores: dict, b_scores: dict) -> None:
        mrr_a = a_scores.get("mean_mrr", "N/A")
        mrr_b = b_scores.get("mean_mrr", "N/A")
        ndcg_a = a_scores.get("mean_ndcg", "N/A")
        ndcg_b = b_scores.get("mean_ndcg", "N/A")
        rcl_a = a_scores.get("mean_recall_at_k", "N/A")
        rcl_b = b_scores.get("mean_recall_at_k", "N/A")
        print(
            f"{label:<16} {_fmt(mrr_a):>7} {_fmt(mrr_b):>7} {_delta(mrr_a, mrr_b):>8}"
            f" {_fmt(ndcg_a):>7} {_fmt(ndcg_b):>7} {_delta(ndcg_a, ndcg_b):>8}"
            f" {_fmt(rcl_a):>7} {_fmt(rcl_b):>7} {_delta(rcl_a, rcl_b):>8}"
        )

    for cat in all_cats:
        _row(cat, cats_a.get(cat, {}), cats_b.get(cat, {}))

    print(separator)
    _row(
        "global",
        {"mean_mrr": rec_a.get("mean_mrr"), "mean_ndcg": rec_a.get("mean_ndcg"), "mean_recall_at_k": rec_a.get("mean_recall_at_k")},
        {"mean_mrr": rec_b.get("mean_mrr"), "mean_ndcg": rec_b.get("mean_ndcg"), "mean_recall_at_k": rec_b.get("mean_recall_at_k")},
    )
    print(separator)


@pytest.mark.asyncio
async def test_gold_standard_recall_sanity() -> None:
    """Sanity gate: Recall@10 must be ≥ 0.40 (corpus populated, retriever working)."""
    summary = await run_gold_standard_benchmark()
    assert summary.mean_recall_at_k >= 0.40, (
        f"Gold standard Recall@10 = {summary.mean_recall_at_k:.3f} is below 0.40. "
        "Ensure the knowledge base is populated with the Earthdawn rulebook PDF "
        "before running this benchmark."
    )
