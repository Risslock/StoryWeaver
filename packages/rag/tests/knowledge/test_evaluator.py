"""Unit tests for the exact-term subset aggregation in evaluator.py (feature 014, SC-002)."""

from __future__ import annotations

import pytest
from rag.knowledge.evaluator import aggregate_results, evaluate_question
from rag.knowledge.interface import KnowledgeChunk
from rag.knowledge.test_questions import TestQuestion


def _make_chunk(text: str, chunk_id: str = "c1") -> KnowledgeChunk:
    return KnowledgeChunk(
        chunk_id=chunk_id,
        doc_id="d1",
        doc_title="Test Doc",
        headline="Headline",
        summary="Summary",
        topic="Topic",
        access_level="player_visible",
        scope="global",
        text=text,
        rrf_score=1.0,
    )


class TestIsExactTermPropagation:
    def test_evaluate_question_propagates_exact_term_true(self) -> None:
        q = TestQuestion(
            question="Q?", keywords=["dragon"], reference_answer="A",
            category="direct_fact", exact_term=True,
        )
        result = evaluate_question(q, [_make_chunk("dragon lair")], k=5)
        assert result.is_exact_term is True

    def test_evaluate_question_propagates_exact_term_false_default(self) -> None:
        q = TestQuestion(question="Q?", keywords=["dragon"], reference_answer="A", category="direct_fact")
        result = evaluate_question(q, [_make_chunk("dragon lair")], k=5)
        assert result.is_exact_term is False

    def test_evaluate_question_empty_keywords_still_propagates_exact_term(self) -> None:
        q = TestQuestion(question="Q?", keywords=[], reference_answer="A", category="direct_fact", exact_term=True)
        result = evaluate_question(q, [], k=5)
        assert result.is_exact_term is True


class TestExactTermScoresAggregation:
    def test_mixed_results_computed_only_over_exact_term_subset(self) -> None:
        q_exact = TestQuestion(
            question="Q1?", keywords=["dragon"], reference_answer="A",
            category="direct_fact", exact_term=True,
        )
        q_other = TestQuestion(
            question="Q2?", keywords=["elf"], reference_answer="B",
            category="direct_fact", exact_term=False,
        )
        r_exact = evaluate_question(q_exact, [_make_chunk("dragon lair")], k=5)
        r_other = evaluate_question(q_other, [], k=5)

        summary = aggregate_results([r_exact, r_other])

        assert summary.exact_term_scores is not None
        assert summary.exact_term_scores.question_count == 1
        assert summary.exact_term_scores.mean_mrr == pytest.approx(r_exact.mrr)
        assert summary.exact_term_scores.mean_recall_at_k == pytest.approx(r_exact.recall_at_k)

    def test_all_false_produces_none(self) -> None:
        q = TestQuestion(question="Q?", keywords=["elf"], reference_answer="A", category="direct_fact")
        result = evaluate_question(q, [_make_chunk("elf territory")], k=5)
        summary = aggregate_results([result])
        assert summary.exact_term_scores is None

    def test_all_true_averages_across_all(self) -> None:
        q1 = TestQuestion(question="Q1?", keywords=["dragon"], reference_answer="A", category="direct_fact", exact_term=True)
        q2 = TestQuestion(question="Q2?", keywords=["dwarf"], reference_answer="B", category="direct_fact", exact_term=True)
        r1 = evaluate_question(q1, [_make_chunk("dragon lair")], k=5)
        r2 = evaluate_question(q2, [], k=5)
        summary = aggregate_results([r1, r2])

        assert summary.exact_term_scores is not None
        assert summary.exact_term_scores.question_count == 2
        assert summary.exact_term_scores.mean_mrr == pytest.approx((r1.mrr + r2.mrr) / 2)
