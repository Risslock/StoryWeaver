"""Pure metric functions for RAG retrieval evaluation: MRR, nDCG, Recall@k."""

from __future__ import annotations

import math

from pydantic import BaseModel

from rag.knowledge.interface import KnowledgeChunk
from rag.knowledge.test_questions import TestQuestion

# ── Result models ─────────────────────────────────────────────────────────────

_STANDARD_CATEGORIES = ("direct_fact", "comparison", "holistic", "numeric", "relationship")


class CategoryMetrics(BaseModel):
    mean_mrr: float
    mean_ndcg: float
    mean_recall_at_k: float
    question_count: int


class RetrievalEvalResult(BaseModel):
    question: str
    category: str
    mrr: float
    ndcg: float
    recall_at_k: float
    keywords_found: int
    total_keywords: int
    k: int
    retrieved_chunks: list[KnowledgeChunk]
    keyword_ranks: dict[str, int | None]

    model_config = {"arbitrary_types_allowed": True}


class EvalSummary(BaseModel):
    mean_mrr: float
    mean_ndcg: float
    mean_recall_at_k: float
    total_questions: int
    k: int
    category_scores: dict[str, CategoryMetrics] = {}


# ── Metric functions ──────────────────────────────────────────────────────────


def calculate_mrr(keyword: str, chunks: list[KnowledgeChunk]) -> float:
    """Return 1/rank of the first chunk whose text contains `keyword` (case-insensitive), or 0.0."""
    kw = keyword.lower()
    for rank, chunk in enumerate(chunks, start=1):
        if kw in chunk.text.lower():
            return 1.0 / rank
    return 0.0


def calculate_ndcg(keyword: str, chunks: list[KnowledgeChunk], k: int) -> float:
    """Return nDCG@k using binary relevance and log2(i+2) discount. Returns 0.0 when IDCG is 0."""
    top_k = chunks[:k]
    kw = keyword.lower()
    relevance = [1 if kw in c.text.lower() else 0 for c in top_k]

    dcg = sum(rel / math.log2(i + 2) for i, rel in enumerate(relevance))

    ideal = sorted(relevance, reverse=True)
    idcg = sum(rel / math.log2(i + 2) for i, rel in enumerate(ideal))

    if idcg == 0.0:
        return 0.0
    return dcg / idcg


def calculate_recall_at_k(keyword: str, chunks: list[KnowledgeChunk], k: int) -> float:
    """Return 1.0 if `keyword` appears in any of the top-k chunks, else 0.0."""
    kw = keyword.lower()
    return 1.0 if any(kw in c.text.lower() for c in chunks[:k]) else 0.0


# ── Aggregate functions ───────────────────────────────────────────────────────


def evaluate_question(
    test: TestQuestion,
    chunks: list[KnowledgeChunk],
    k: int,
) -> RetrievalEvalResult:
    """Compute mean MRR/nDCG/Recall@k across all keywords for one test question."""
    keywords = test.keywords

    if not keywords:
        return RetrievalEvalResult(
            question=test.question,
            category=test.category,
            mrr=0.0,
            ndcg=0.0,
            recall_at_k=0.0,
            keywords_found=0,
            total_keywords=0,
            k=k,
            retrieved_chunks=chunks,
            keyword_ranks={},
        )

    mrr_scores = [calculate_mrr(kw, chunks) for kw in keywords]
    ndcg_scores = [calculate_ndcg(kw, chunks, k) for kw in keywords]
    recall_scores = [calculate_recall_at_k(kw, chunks, k) for kw in keywords]

    keyword_ranks: dict[str, int | None] = {}
    for kw in keywords:
        kw_lower = kw.lower()
        rank = None
        for i, chunk in enumerate(chunks, start=1):
            if kw_lower in chunk.text.lower():
                rank = i
                break
        keyword_ranks[kw] = rank

    keywords_found = sum(1 for r in keyword_ranks.values() if r is not None)

    return RetrievalEvalResult(
        question=test.question,
        category=test.category,
        mrr=sum(mrr_scores) / len(mrr_scores),
        ndcg=sum(ndcg_scores) / len(ndcg_scores),
        recall_at_k=sum(recall_scores) / len(recall_scores),
        keywords_found=keywords_found,
        total_keywords=len(keywords),
        k=k,
        retrieved_chunks=chunks,
        keyword_ranks=keyword_ranks,
    )


def aggregate_results(results: list[RetrievalEvalResult]) -> EvalSummary:
    """Aggregate a list of per-question results into a summary. Returns zeros for empty input."""
    if not results:
        return EvalSummary(
            mean_mrr=0.0,
            mean_ndcg=0.0,
            mean_recall_at_k=0.0,
            total_questions=0,
            k=0,
        )
    n = len(results)

    grouped: dict[str, list[RetrievalEvalResult]] = {}
    for r in results:
        cat = r.category.strip() if r.category else "uncategorized"
        if not cat:
            cat = "uncategorized"
        grouped.setdefault(cat, []).append(r)

    category_scores: dict[str, CategoryMetrics] = {}
    for cat in _STANDARD_CATEGORIES:
        group = grouped.get(cat, [])
        if group:
            gn = len(group)
            category_scores[cat] = CategoryMetrics(
                mean_mrr=sum(r.mrr for r in group) / gn,
                mean_ndcg=sum(r.ndcg for r in group) / gn,
                mean_recall_at_k=sum(r.recall_at_k for r in group) / gn,
                question_count=gn,
            )
        else:
            category_scores[cat] = CategoryMetrics(
                mean_mrr=0.0, mean_ndcg=0.0, mean_recall_at_k=0.0, question_count=0
            )

    uncategorized = grouped.get("uncategorized", [])
    if uncategorized:
        gn = len(uncategorized)
        category_scores["uncategorized"] = CategoryMetrics(
            mean_mrr=sum(r.mrr for r in uncategorized) / gn,
            mean_ndcg=sum(r.ndcg for r in uncategorized) / gn,
            mean_recall_at_k=sum(r.recall_at_k for r in uncategorized) / gn,
            question_count=gn,
        )

    return EvalSummary(
        mean_mrr=sum(r.mrr for r in results) / n,
        mean_ndcg=sum(r.ndcg for r in results) / n,
        mean_recall_at_k=sum(r.recall_at_k for r in results) / n,
        total_questions=n,
        k=results[0].k,
        category_scores=category_scores,
    )
