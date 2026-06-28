"""EvaluationStore — SQLite persistence for ResponseEvalRecord."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import Float, Index, Integer, String, Text, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

_log = logging.getLogger(__name__)


class _EvalBase(DeclarativeBase):
    pass


class ResponseEvalRecord(_EvalBase):
    """One row per question per eval run in data/eval.db."""

    __tablename__ = "response_eval_records"
    __table_args__ = (
        Index("ix_eval_run_id", "run_id"),
        Index("ix_eval_campaign_id", "campaign_id"),
        Index("ix_eval_judge_status", "judge_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String, nullable=False)
    campaign_id: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    question_source: Mapped[str] = mapped_column(String, nullable=False, default="gold_standard")
    question_category: Mapped[str | None] = mapped_column(String, nullable=True)
    generated_response: Mapped[str] = mapped_column(Text, nullable=False, default="")
    context_chunks_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    judge_status: Mapped[str] = mapped_column(String, nullable=False, default="unscored")
    judge_provider: Mapped[str | None] = mapped_column(String, nullable=True)
    judge_model: Mapped[str | None] = mapped_column(String, nullable=True)
    judge_faithfulness: Mapped[float | None] = mapped_column(Float, nullable=True)
    judge_faithfulness_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    judge_relevance: Mapped[float | None] = mapped_column(Float, nullable=True)
    judge_relevance_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    judge_context_utilization: Mapped[float | None] = mapped_column(Float, nullable=True)
    judge_context_utilization_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    judge_aggregate: Mapped[float | None] = mapped_column(Float, nullable=True)
    judge_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    judge_raw_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    judge_context_truncated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    scored_at: Mapped[str | None] = mapped_column(String, nullable=True)


class EvaluationStore:
    """Async SQLite store for ResponseEvalRecord rows."""

    def __init__(self, db_path: str = "data/eval.db") -> None:
        url = f"sqlite+aiosqlite:///{db_path}"
        self._engine = create_async_engine(url, echo=False)
        self._session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
            self._engine, expire_on_commit=False
        )

    async def initialize(self) -> None:
        """Create tables if they don't exist."""
        async with self._engine.begin() as conn:
            await conn.run_sync(_EvalBase.metadata.create_all)
        _log.info("EvaluationStore initialized")

    async def write_record(
        self,
        *,
        run_id: str,
        campaign_id: str,
        role: str,
        question: str,
        question_source: str = "gold_standard",
        question_category: str | None = None,
        generated_response: str = "",
        context_chunks_json: str = "[]",
    ) -> ResponseEvalRecord:
        """Insert a new unscored EvaluationRecord and return it with its assigned id."""
        now = datetime.now(UTC).isoformat()
        record = ResponseEvalRecord(
            run_id=run_id,
            campaign_id=campaign_id,
            role=role,
            question=question,
            question_source=question_source,
            question_category=question_category,
            generated_response=generated_response,
            context_chunks_json=context_chunks_json,
            judge_status="unscored",
            created_at=now,
        )
        async with self._session_factory() as session:
            session.add(record)
            await session.commit()
            await session.refresh(record)
        _log.debug("Wrote EvaluationRecord id=%d run_id=%s", record.id, run_id)
        return record

    async def get_unscored_by_run(
        self,
        run_id: str | None = None,
        force: bool = False,
    ) -> Sequence[ResponseEvalRecord]:
        """Return records to process.

        Without force: only records with judge_status in ('unscored', 'error', 'parse_error').
        With force: all records in scope (used with --force to re-score already-scored rows).
        """
        async with self._session_factory() as session:
            stmt = select(ResponseEvalRecord)
            if run_id is not None:
                stmt = stmt.where(ResponseEvalRecord.run_id == run_id)
            if not force:
                stmt = stmt.where(
                    ResponseEvalRecord.judge_status.in_(["unscored", "error", "parse_error"])
                )
            result = await session.execute(stmt)
            return result.scalars().all()

    async def get_by_run_id(self, run_id: str) -> Sequence[ResponseEvalRecord]:
        """Return all records for a given run_id regardless of status."""
        async with self._session_factory() as session:
            stmt = select(ResponseEvalRecord).where(ResponseEvalRecord.run_id == run_id)
            result = await session.execute(stmt)
            return result.scalars().all()

    async def update_judge_result(
        self,
        record_id: int,
        *,
        judge_status: str,
        judge_provider: str | None = None,
        judge_model: str | None = None,
        judge_faithfulness: float | None = None,
        judge_faithfulness_rationale: str | None = None,
        judge_relevance: float | None = None,
        judge_relevance_rationale: str | None = None,
        judge_context_utilization: float | None = None,
        judge_context_utilization_rationale: str | None = None,
        judge_aggregate: float | None = None,
        judge_error: str | None = None,
        judge_raw_response: str | None = None,
        judge_context_truncated: bool = False,
    ) -> None:
        """Write judge outcome fields back to an existing record."""
        now = datetime.now(UTC).isoformat()
        values: dict[str, object] = {
            "judge_status": judge_status,
            "judge_provider": judge_provider,
            "judge_model": judge_model,
            "judge_faithfulness": judge_faithfulness,
            "judge_faithfulness_rationale": judge_faithfulness_rationale,
            "judge_relevance": judge_relevance,
            "judge_relevance_rationale": judge_relevance_rationale,
            "judge_context_utilization": judge_context_utilization,
            "judge_context_utilization_rationale": judge_context_utilization_rationale,
            "judge_aggregate": judge_aggregate,
            "judge_error": judge_error,
            "judge_raw_response": judge_raw_response,
            "judge_context_truncated": 1 if judge_context_truncated else 0,
            "scored_at": now,
        }
        async with self._session_factory() as session:
            stmt = (
                update(ResponseEvalRecord)
                .where(ResponseEvalRecord.id == record_id)
                .values(**values)
            )
            await session.execute(stmt)
            await session.commit()
        _log.debug("Updated judge result for record id=%d status=%s", record_id, judge_status)

    async def count_by_status(self, run_id: str | None = None) -> dict[str, int]:
        """Return {judge_status: count} for scoped or all records."""
        async with self._session_factory() as session:
            stmt = select(ResponseEvalRecord.judge_status, func.count().label("cnt"))
            if run_id is not None:
                stmt = stmt.where(ResponseEvalRecord.run_id == run_id)
            stmt = stmt.group_by(ResponseEvalRecord.judge_status)
            result = await session.execute(stmt)
            return {str(row[0]): int(row[1]) for row in result}
