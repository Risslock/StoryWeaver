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

    strategy = create_chunker().strategy_name
    record = {
        "strategy": strategy,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "gold_standard_path": GOLD_STANDARD_PATH,
        "k": k,
        "total_questions": summary.total_questions,
        "mean_mrr": summary.mean_mrr,
        "mean_ndcg": summary.mean_ndcg,
        "mean_recall_at_k": summary.mean_recall_at_k,
        "notes": "",
    }
    with open(BENCHMARK_RESULTS_PATH, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")

    return summary


@pytest.mark.asyncio
async def test_gold_standard_recall_sanity() -> None:
    """Sanity gate: Recall@10 must be ≥ 0.40 (corpus populated, retriever working)."""
    summary = await run_gold_standard_benchmark()
    assert summary.mean_recall_at_k >= 0.40, (
        f"Gold standard Recall@10 = {summary.mean_recall_at_k:.3f} is below 0.40. "
        "Ensure the knowledge base is populated with the Earthdawn rulebook PDF "
        "before running this benchmark."
    )
