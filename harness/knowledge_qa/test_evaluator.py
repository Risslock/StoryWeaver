"""Unit tests for RAG evaluation metric functions."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from rag.knowledge.evaluator import (
    EvalSummary,
    RetrievalEvalResult,
    aggregate_results,
    calculate_mrr,
    calculate_ndcg,
    calculate_recall_at_k,
    evaluate_question,
)
from rag.knowledge.test_questions import TestQuestion


def _make_chunk(text: str, chunk_id: str = "c1") -> object:
    from rag.knowledge.interface import KnowledgeChunk
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


# ── calculate_mrr ─────────────────────────────────────────────────────────────


class TestCalculateMrr:
    def test_empty_chunks_returns_zero(self):
        assert calculate_mrr("dragon", []) == 0.0

    def test_keyword_at_rank_1(self):
        chunks = [_make_chunk("A dragon roams here")]
        assert calculate_mrr("dragon", chunks) == pytest.approx(1.0)

    def test_keyword_at_rank_2(self):
        chunks = [_make_chunk("No match"), _make_chunk("dragon appears")]
        assert calculate_mrr("dragon", chunks) == pytest.approx(0.5)

    def test_keyword_not_found(self):
        chunks = [_make_chunk("nothing relevant")]
        assert calculate_mrr("dragon", chunks) == 0.0

    def test_case_insensitive(self):
        chunks = [_make_chunk("The DRAGON flies")]
        assert calculate_mrr("dragon", chunks) == pytest.approx(1.0)


# ── calculate_ndcg ────────────────────────────────────────────────────────────


class TestCalculateNdcg:
    def test_empty_chunks_returns_zero(self):
        assert calculate_ndcg("elf", [], k=5) == 0.0

    def test_keyword_not_found_returns_zero(self):
        chunks = [_make_chunk("No elf here") for _ in range(3)]
        assert calculate_ndcg("goblin", chunks, k=3) == 0.0

    def test_perfect_rank_1_match(self):
        chunks = [_make_chunk("goblin caves", f"c{i}") for i in range(3)]
        score = calculate_ndcg("goblin", chunks, k=3)
        assert score == pytest.approx(1.0)

    def test_k_larger_than_chunk_count(self):
        chunks = [_make_chunk("goblin caves")]
        score = calculate_ndcg("goblin", chunks, k=10)
        assert 0.0 <= score <= 1.0

    def test_case_insensitive(self):
        chunks = [_make_chunk("GOBLIN lair")]
        assert calculate_ndcg("goblin", chunks, k=5) == pytest.approx(1.0)


# ── calculate_recall_at_k ─────────────────────────────────────────────────────


class TestCalculateRecallAtK:
    def test_empty_chunks_returns_zero(self):
        assert calculate_recall_at_k("elf", [], k=5) == 0.0

    def test_keyword_found_returns_one(self):
        chunks = [_make_chunk("The elf archer")]
        assert calculate_recall_at_k("elf", chunks, k=5) == 1.0

    def test_keyword_not_found_returns_zero(self):
        chunks = [_make_chunk("dwarf miner")]
        assert calculate_recall_at_k("elf", chunks, k=5) == 0.0

    def test_k_larger_than_chunk_count(self):
        chunks = [_make_chunk("elf camp")]
        assert calculate_recall_at_k("elf", chunks, k=100) == 1.0

    def test_keyword_beyond_k_not_counted(self):
        chunks = [_make_chunk("dwarf") for _ in range(3)] + [_make_chunk("elf guard")]
        assert calculate_recall_at_k("elf", chunks, k=3) == 0.0

    def test_case_insensitive(self):
        chunks = [_make_chunk("ELF ranger")]
        assert calculate_recall_at_k("elf", chunks, k=5) == 1.0


# ── evaluate_question ─────────────────────────────────────────────────────────


class TestEvaluateQuestion:
    def test_empty_keywords_returns_zeros(self):
        q = TestQuestion(question="Q?", keywords=[], reference_answer="A", category="C")
        result = evaluate_question(q, [], k=5)
        assert result.mrr == 0.0
        assert result.ndcg == 0.0
        assert result.recall_at_k == 0.0
        assert result.keywords_found == 0
        assert result.total_keywords == 0

    def test_keyword_found_at_rank_1(self):
        q = TestQuestion(question="Q?", keywords=["dragon"], reference_answer="A", category="C")
        chunks = [_make_chunk("dragon lair")]
        result = evaluate_question(q, chunks, k=5)
        assert result.mrr == pytest.approx(1.0)
        assert result.keywords_found == 1
        assert result.keyword_ranks == {"dragon": 1}

    def test_keyword_not_found(self):
        q = TestQuestion(question="Q?", keywords=["unicorn"], reference_answer="A", category="C")
        chunks = [_make_chunk("dragon territory")]
        result = evaluate_question(q, chunks, k=5)
        assert result.mrr == 0.0
        assert result.recall_at_k == 0.0
        assert result.keyword_ranks == {"unicorn": None}
        assert result.keywords_found == 0

    def test_multiple_keywords_averaged(self):
        q = TestQuestion(
            question="Q?",
            keywords=["dragon", "elf"],
            reference_answer="A",
            category="C",
        )
        chunks = [_make_chunk("dragon lair"), _make_chunk("nothing")]
        result = evaluate_question(q, chunks, k=5)
        assert result.mrr == pytest.approx(0.5)

    def test_k_larger_than_chunks_no_crash(self):
        q = TestQuestion(question="Q?", keywords=["goblin"], reference_answer="A", category="C")
        chunks = [_make_chunk("goblin cave")]
        result = evaluate_question(q, chunks, k=100)
        assert 0.0 <= result.mrr <= 1.0


# ── aggregate_results ─────────────────────────────────────────────────────────


class TestAggregateResults:
    def test_empty_list_returns_zero_summary(self):
        summary = aggregate_results([])
        assert summary == EvalSummary(
            mean_mrr=0.0,
            mean_ndcg=0.0,
            mean_recall_at_k=0.0,
            total_questions=0,
            k=0,
        )

    def test_single_result(self):
        q = TestQuestion(question="Q?", keywords=["elf"], reference_answer="A", category="C")
        chunks = [_make_chunk("elf territory")]
        result = evaluate_question(q, chunks, k=5)
        summary = aggregate_results([result])
        assert summary.total_questions == 1
        assert summary.mean_mrr == pytest.approx(result.mrr)

    def test_mean_is_averaged_across_questions(self):
        q1 = TestQuestion(question="Q1?", keywords=["elf"], reference_answer="A", category="C")
        q2 = TestQuestion(question="Q2?", keywords=["dwarf"], reference_answer="B", category="C")
        chunks1 = [_make_chunk("elf territory")]
        chunks2 = []
        r1 = evaluate_question(q1, chunks1, k=5)
        r2 = evaluate_question(q2, chunks2, k=5)
        summary = aggregate_results([r1, r2])
        assert summary.total_questions == 2
        assert summary.mean_mrr == pytest.approx((r1.mrr + r2.mrr) / 2)
