"""Evaluation service — bridges the GM eval UI to the RAG evaluator and retriever."""

from __future__ import annotations

import logging
import uuid

from core.errors import ProviderUnavailableError
from rag.knowledge.evaluator import (
    EvalSummary,
    RetrievalEvalResult,
    aggregate_results,
    evaluate_question,
)
from rag.knowledge.retriever import ChromaKnowledgeRetriever
from rag.knowledge.test_questions import load_test_questions

_log = logging.getLogger(__name__)


async def run_evaluation(
    file_path: str,
    campaign_id: uuid.UUID,
    k: int,
) -> tuple[list[RetrievalEvalResult], EvalSummary]:
    """Load JSONL test questions, retrieve chunks, and compute retrieval metrics.

    Logs run start/end at INFO. Per-question retrieval errors are logged at ERROR
    and scored 0.0 rather than aborting the run.
    Raises ProviderUnavailableError if the retriever is unavailable.
    Raises ValueError for malformed JSONL input.
    """
    questions = load_test_questions(file_path)
    campaign_id_str = str(campaign_id).replace("-", "")

    _log.info(
        "RAG eval run started: %d questions, campaign=%s, k=%d",
        len(questions),
        campaign_id_str,
        k,
    )

    retriever = ChromaKnowledgeRetriever()
    results: list[RetrievalEvalResult] = []

    for q in questions:
        try:
            chunks = await retriever.search(
                query=q.question,
                campaign_id=campaign_id_str,
                role="gm",
                top_k=k,
            )
        except ProviderUnavailableError:
            raise
        except Exception as exc:
            _log.error("Error retrieving for question %r: %s", q.question, exc)
            chunks = []

        result = evaluate_question(q, chunks, k)
        results.append(result)

    summary = aggregate_results(results)
    _log.info(
        "RAG eval run complete: %d questions, mrr=%.3f ndcg=%.3f recall@%d=%.3f",
        summary.total_questions,
        summary.mean_mrr,
        summary.mean_ndcg,
        k,
        summary.mean_recall_at_k,
    )
    return results, summary
