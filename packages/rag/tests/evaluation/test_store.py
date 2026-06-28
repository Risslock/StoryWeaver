"""Unit tests for EvaluationStore."""

from __future__ import annotations

import json

import pytest
import pytest_asyncio
from rag.evaluation.store import EvaluationStore


@pytest_asyncio.fixture
async def store(tmp_path: object) -> EvaluationStore:  # type: ignore[type-arg]
    db_path = str(tmp_path / "test_eval.db")  # type: ignore[operator]
    s = EvaluationStore(db_path)
    await s.initialize()
    return s


@pytest.mark.asyncio
async def test_write_record_creates_unscored_record(store: EvaluationStore) -> None:
    run_id = "20260628-000000-test1234"
    record = await store.write_record(
        run_id=run_id,
        campaign_id="a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        role="gm",
        question="What is a dwarf?",
        question_source="gold_standard",
        question_category="direct_fact",
        generated_response="A dwarf is a Name-giver race.",
        context_chunks_json=json.dumps(["chunk text"]),
    )
    assert record.id is not None
    assert record.judge_status == "unscored"
    assert record.campaign_id == "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
    assert record.role == "gm"
    assert record.run_id == run_id


@pytest.mark.asyncio
async def test_get_unscored_by_run_returns_all_unscored(store: EvaluationStore) -> None:
    run_id = "20260628-000000-testrun1"
    for i in range(3):
        await store.write_record(
            run_id=run_id,
            campaign_id="campaign-1",
            role="gm",
            question=f"Question {i}",
            generated_response=f"Answer {i}",
        )
    records = await store.get_unscored_by_run(run_id=run_id)
    assert len(records) == 3


@pytest.mark.asyncio
async def test_update_judge_result_scored(store: EvaluationStore) -> None:
    run_id = "20260628-000000-testrun2"
    record = await store.write_record(
        run_id=run_id,
        campaign_id="c1",
        role="gm",
        question="Q",
        generated_response="A",
    )
    await store.update_judge_result(
        record.id,
        judge_status="scored",
        judge_provider="ollama",
        judge_model="llama3.1",
        judge_faithfulness=0.8,
        judge_faithfulness_rationale="Good",
        judge_relevance=0.9,
        judge_relevance_rationale="Very relevant",
        judge_context_utilization=0.7,
        judge_context_utilization_rationale="Used well",
        judge_aggregate=0.8,
    )
    all_records = await store.get_by_run_id(run_id)
    assert len(all_records) == 1
    r = all_records[0]
    assert r.judge_status == "scored"
    assert r.judge_faithfulness == pytest.approx(0.8)
    assert r.judge_relevance == pytest.approx(0.9)
    assert r.judge_provider == "ollama"
    assert r.scored_at is not None


@pytest.mark.asyncio
async def test_skip_already_scored_without_force(store: EvaluationStore) -> None:
    run_id = "20260628-000000-testrun3"
    record = await store.write_record(
        run_id=run_id, campaign_id="c1", role="gm",
        question="Q", generated_response="A",
    )
    await store.update_judge_result(
        record.id,
        judge_status="scored",
        judge_provider="ollama",
        judge_model="m",
    )
    unscored = await store.get_unscored_by_run(run_id=run_id, force=False)
    assert len(unscored) == 0


@pytest.mark.asyncio
async def test_force_returns_scored_records(store: EvaluationStore) -> None:
    run_id = "20260628-000000-testrun4"
    record = await store.write_record(
        run_id=run_id, campaign_id="c1", role="gm",
        question="Q", generated_response="A",
    )
    await store.update_judge_result(record.id, judge_status="scored", judge_provider="ollama", judge_model="m")
    forced = await store.get_unscored_by_run(run_id=run_id, force=True)
    assert len(forced) == 1


@pytest.mark.asyncio
async def test_retry_error_records(store: EvaluationStore) -> None:
    run_id = "20260628-000000-testrun5"
    record = await store.write_record(
        run_id=run_id, campaign_id="c1", role="gm",
        question="Q", generated_response="A",
    )
    await store.update_judge_result(
        record.id, judge_status="error",
        judge_provider="ollama", judge_model="m", judge_error="timeout",
    )
    retryable = await store.get_unscored_by_run(run_id=run_id, force=False)
    assert len(retryable) == 1


@pytest.mark.asyncio
async def test_run_id_filtering(store: EvaluationStore) -> None:
    for run in ["run-A", "run-B"]:
        for i in range(2):
            await store.write_record(
                run_id=run, campaign_id="c1", role="gm",
                question=f"{run}-Q{i}", generated_response="A",
            )
    run_a_records = await store.get_unscored_by_run(run_id="run-A")
    assert len(run_a_records) == 2
    all_records = await store.get_unscored_by_run()
    assert len(all_records) == 4


@pytest.mark.asyncio
async def test_count_by_status(store: EvaluationStore) -> None:
    run_id = "20260628-000000-testrun6"
    await store.write_record(run_id=run_id, campaign_id="c1", role="gm", question="Q1", generated_response="A1")
    r2 = await store.write_record(run_id=run_id, campaign_id="c1", role="gm", question="Q2", generated_response="A2")
    await store.update_judge_result(r2.id, judge_status="scored", judge_provider="ollama", judge_model="m")
    counts = await store.count_by_status(run_id=run_id)
    assert counts.get("unscored", 0) == 1
    assert counts.get("scored", 0) == 1
