"""GM-only RAG Evaluation tab — retrieval metrics + LLM-as-judge response quality."""

from __future__ import annotations

import json
import uuid as _uuid_mod
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from datetime import UTC, datetime

import gradio as gr
from core.config import settings
from core.errors import ProviderUnavailableError
from core.schemas import CampaignSession
from rag.knowledge.evaluator import EvalSummary, RetrievalEvalResult


def _judge_env_available() -> bool:
    return bool(settings.judge_provider) and bool(settings.judge_model)


@dataclass
class EvalRow:
    """Combined retrieval + judge result for one question, used as UI state."""

    index: int
    question: str
    category: str

    # Retrieval metrics
    mrr: float
    ndcg: float
    recall_at_k: float
    keywords_found: int
    total_keywords: int
    keyword_ranks: dict = field(default_factory=dict)
    retrieved_chunks: list = field(default_factory=list)

    # Judge metrics (None when judge not run or question skipped)
    faithfulness: float | None = None
    faithfulness_rationale: str | None = None
    relevance: float | None = None
    relevance_rationale: str | None = None
    context_utilization: float | None = None
    context_utilization_rationale: str | None = None
    answer_correctness: float | None = None
    answer_correctness_rationale: str | None = None
    aggregate: float | None = None
    judge_status: str = "skipped"
    judge_error: str | None = None
    generated_response: str | None = None

    def to_table_row(self) -> list:
        def _f(v: float | None) -> str:
            return f"{v:.3f}" if v is not None else "—"

        return [
            self.index,
            self.question,
            self.category or "",
            round(self.mrr, 4),
            round(self.ndcg, 4),
            round(self.recall_at_k, 4),
            f"{self.keywords_found}/{self.total_keywords}",
            _f(self.faithfulness),
            _f(self.relevance),
            _f(self.context_utilization),
            _f(self.answer_correctness),
            _f(self.aggregate),
            self.judge_status,
        ]


_HEADERS = [
    "#", "Question", "Category",
    "MRR", "nDCG", "Recall@k", "Found/Total",
    "Faithfulness", "Relevance", "Ctx Util", "Correctness", "Aggregate", "Judge",
]
_DTYPES: list[str] = [
    "number", "str", "str",
    "number", "number", "number", "str",
    "str", "str", "str", "str", "str", "str",
]


def build_rag_eval_page(session_state: gr.State) -> None:
    """Build the GM RAG Evaluation tab. Must be called inside a gr.Blocks context."""

    _judge_ready = _judge_env_available()
    _judge_provider = settings.judge_provider
    _judge_model = settings.judge_model

    with gr.Tab("RAG Evaluation"):
        gr.Markdown("## RAG Evaluation")

        if _judge_ready:
            gr.Markdown(
                f"> **Response quality scoring enabled** — "
                f"judge: `{_judge_provider}/{_judge_model}` · "
                "scores persist to `data/eval.db`"
            )
        else:
            gr.Markdown(
                "> **Response quality scoring disabled** — "
                "set `JUDGE_PROVIDER` and `JUDGE_MODEL` env vars and restart to enable."
            )

        # ── Controls ──────────────────────────────────────────────────────
        with gr.Row():
            file_input = gr.File(
                file_types=[".jsonl"],
                label="Test questions (JSONL)",
                scale=4,
                elem_id="rag-eval-file",
            )
            k_slider = gr.Slider(
                minimum=1,
                maximum=20,
                value=10,
                step=1,
                label="k (retrieval depth)",
                scale=2,
                elem_id="rag-eval-k",
            )
            run_btn = gr.Button(
                "Run Evaluation",
                variant="primary",
                interactive=False,
                scale=1,
                elem_id="rag-eval-run-btn",
            )

        # ── Status & results ───────────────────────────────────────────────
        placeholder_md = gr.Markdown(
            "Load a JSONL file to begin.",
            elem_id="rag-eval-placeholder",
        )
        progress_md = gr.Markdown("", elem_id="rag-eval-progress")
        summary_md = gr.Markdown("", elem_id="rag-eval-summary")

        results_table = gr.Dataframe(
            headers=_HEADERS,
            datatype=_DTYPES,  # type: ignore[arg-type]
            interactive=False,
            wrap=True,
            elem_id="rag-eval-table",
        )

        detail_md = gr.Markdown("", elem_id="rag-eval-detail")

        # ── State ─────────────────────────────────────────────────────────
        eval_results_state: gr.State = gr.State(value=None)
        selected_idx_state: gr.State = gr.State(value=None)

        # ── Event handlers ────────────────────────────────────────────────

        def on_file_change(f: object) -> tuple:  # type: ignore[type-arg]
            has_file = f is not None
            return (
                gr.update(interactive=has_file),
                gr.update(visible=not has_file),
                gr.update(value=""),
            )

        async def on_run_eval(
            state: CampaignSession | None,
            f: object,
            k: int,
        ) -> AsyncGenerator[tuple[object, ...], None]:

            if state is None:
                yield (
                    gr.update(value="Error: not in a campaign session."),
                    gr.update(value=""),
                    gr.update(value=[]),
                    None,
                )
                return
            if f is None:
                yield (
                    gr.update(value="No file selected."),
                    gr.update(value=""),
                    gr.update(value=[]),
                    None,
                )
                return

            file_path: str = f.name if hasattr(f, "name") else str(f)  # type: ignore[union-attr]

            try:
                from rag.knowledge.test_questions import load_test_questions

                questions = load_test_questions(file_path)
            except Exception as exc:
                yield (
                    gr.update(value=f"Failed to load JSONL: {exc}"),
                    gr.update(value=""),
                    gr.update(value=[]),
                    None,
                )
                return

            if not questions:
                yield (
                    gr.update(value="JSONL file is empty."),
                    gr.update(value=""),
                    gr.update(value=[]),
                    None,
                )
                return

            total = len(questions)

            # ── Set up judge (optional) ────────────────────────────────────
            judge_ok = _judge_ready
            evaluator = None
            store = None
            run_id: str | None = None

            if judge_ok:
                from rag.evaluation.factory import get_judge_provider
                from rag.evaluation.judge import JudgeEvaluator
                from rag.evaluation.store import EvaluationStore

                try:
                    _prov = get_judge_provider(_judge_provider, _judge_model)
                    evaluator = JudgeEvaluator(
                        provider=_prov,
                        judge_provider_name=_judge_provider,
                        judge_model_name=_judge_model,
                    )
                    store = EvaluationStore()
                    await store.initialize()
                    _now = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
                    _uid = str(_uuid_mod.uuid4()).replace("-", "")[:8]
                    run_id = f"{_now}-{_uid}"
                except OSError as exc:
                    judge_ok = False
                    yield (
                        gr.update(
                            value=f"Judge config error: {exc} — running retrieval only."
                        ),
                        gr.update(value=""),
                        gr.update(value=[]),
                        None,
                    )

            # ── Main eval loop ─────────────────────────────────────────────
            from rag.knowledge.evaluator import aggregate_results, evaluate_question
            from rag.knowledge.retriever import ChromaKnowledgeRetriever

            retriever = ChromaKnowledgeRetriever()
            campaign_id_str = str(state.campaign_id).replace("-", "")
            accumulated: list[EvalRow] = []
            retrieval_results: list[RetrievalEvalResult] = []

            _mode = (
                f"retrieval + judge ({_judge_provider}/{_judge_model})"
                if judge_ok
                else "retrieval only"
            )
            yield (
                gr.update(value=f"Starting — {total} questions · {_mode}…"),
                gr.update(value=""),
                gr.update(value=[]),
                None,
            )

            for idx, q in enumerate(questions, start=1):
                # ── Phase 1: retrieval (fast) ──────────────────────────────
                yield (
                    gr.update(value=f"[{idx}/{total}] Retrieving…"),
                    gr.update(value=""),
                    gr.update(value=[r.to_table_row() for r in accumulated]),
                    list(accumulated) or None,
                )

                try:
                    chunks = await retriever.search(
                        query=q.question,
                        campaign_id=campaign_id_str,
                        role="gm",
                        top_k=k,
                    )
                except ProviderUnavailableError as exc:
                    yield (
                        gr.update(value=f"Provider unavailable: {exc}"),
                        gr.update(value=""),
                        gr.update(value=[r.to_table_row() for r in accumulated]),
                        list(accumulated) or None,
                    )
                    return
                except Exception:
                    chunks = []

                retrieval_result = evaluate_question(q, chunks, k)
                retrieval_results.append(retrieval_result)

                row = EvalRow(
                    index=idx,
                    question=q.question,
                    category=retrieval_result.category,
                    mrr=retrieval_result.mrr,
                    ndcg=retrieval_result.ndcg,
                    recall_at_k=retrieval_result.recall_at_k,
                    keywords_found=retrieval_result.keywords_found,
                    total_keywords=retrieval_result.total_keywords,
                    keyword_ranks=dict(retrieval_result.keyword_ranks),
                    retrieved_chunks=list(retrieval_result.retrieved_chunks),
                )
                accumulated.append(row)

                # Show retrieval metrics immediately; note if judge follows
                yield (
                    gr.update(
                        value=f"[{idx}/{total}] Retrieved"
                        + (" — scoring…" if judge_ok else "")
                    ),
                    gr.update(value=""),
                    gr.update(value=[r.to_table_row() for r in accumulated]),
                    list(accumulated),
                )

                # ── Phase 2: judge (slow, optional) ───────────────────────
                if judge_ok and evaluator and store and run_id:
                    try:
                        from services.knowledge import ask_question

                        answer, answer_chunks = await ask_question(
                            q.question, state.campaign_id, state.role
                        )
                    except Exception:
                        answer = ""
                        answer_chunks = []

                    row.generated_response = answer

                    record = await store.write_record(
                        run_id=run_id,
                        campaign_id=str(state.campaign_id),
                        role=state.role,
                        question=q.question,
                        reference_answer=q.reference_answer,
                        question_source="ui",
                        question_category=q.category,
                        generated_response=answer,
                        context_chunks_json=json.dumps(
                            [c.text for c in answer_chunks] if answer_chunks else []
                        ),
                    )

                    from rag.evaluation.models import EvaluationInput, JudgeStatus

                    judge_result = await evaluator.evaluate(
                        EvaluationInput(
                            record_id=record.id,
                            run_id=run_id,
                            question=q.question,
                            reference_answer=q.reference_answer,
                            generated_response=answer,
                            context_chunks=(
                                [c.text for c in answer_chunks] if answer_chunks else []
                            ),
                            context_truncated=False,
                        )
                    )

                    _upd: dict = {
                        "judge_status": judge_result.status.value,
                        "judge_provider": judge_result.judge_provider,
                        "judge_model": judge_result.judge_model,
                    }
                    if (
                        judge_result.status == JudgeStatus.scored
                        and judge_result.score is not None
                    ):
                        s = judge_result.score
                        _upd.update(
                            judge_faithfulness=s.faithfulness.score,
                            judge_faithfulness_rationale=s.faithfulness.rationale,
                            judge_relevance=s.relevance.score,
                            judge_relevance_rationale=s.relevance.rationale,
                            judge_context_utilization=s.context_utilization.score,
                            judge_context_utilization_rationale=(
                                s.context_utilization.rationale
                            ),
                            judge_answer_correctness=s.answer_correctness.score,
                            judge_answer_correctness_rationale=(
                                s.answer_correctness.rationale
                            ),
                            judge_aggregate=s.aggregate,
                        )
                        row.faithfulness = s.faithfulness.score
                        row.faithfulness_rationale = s.faithfulness.rationale
                        row.relevance = s.relevance.score
                        row.relevance_rationale = s.relevance.rationale
                        row.context_utilization = s.context_utilization.score
                        row.context_utilization_rationale = (
                            s.context_utilization.rationale
                        )
                        row.answer_correctness = s.answer_correctness.score
                        row.answer_correctness_rationale = s.answer_correctness.rationale
                        row.aggregate = s.aggregate
                        row.judge_status = "scored"
                    elif judge_result.status in (
                        JudgeStatus.error,
                        JudgeStatus.parse_error,
                    ):
                        _upd["judge_error"] = judge_result.error
                        _upd["judge_raw_response"] = judge_result.raw_response
                        row.judge_status = judge_result.status.value
                        row.judge_error = judge_result.error
                    else:
                        row.judge_status = "no_response"

                    await store.update_judge_result(record.id, **_upd)

            # ── Final summary ──────────────────────────────────────────────
            ret_summary = aggregate_results(retrieval_results)
            yield (
                gr.update(
                    value="Complete."
                    + (f" run_id: `{run_id}`" if run_id else "")
                ),
                gr.update(
                    value=_format_summary(accumulated, ret_summary, run_id, judge_ok)
                ),
                gr.update(value=[r.to_table_row() for r in accumulated]),
                list(accumulated),
            )

        def on_row_select(
            evt: gr.SelectData,
            results: list[EvalRow] | None,
        ) -> tuple[str, int | None]:
            if results is None or evt.index is None:
                return "", None
            row_idx = evt.index[0]
            if row_idx >= len(results):
                return "", None
            r = results[row_idx]

            lines: list[str] = [f"### {r.question}\n"]

            # Retrieval section
            lines.append("\n#### Retrieval\n\n")
            lines.append("| Keyword | Rank |\n|---|---|\n")
            for kw, rank in r.keyword_ranks.items():
                lines.append(
                    f"| {kw} | {rank if rank is not None else 'not found'} |\n"
                )
            if r.retrieved_chunks:
                lines.append("\n**Top chunks:**\n")
                for i, chunk in enumerate(r.retrieved_chunks, start=1):
                    lines.append(
                        f"\n**{i}. {chunk.doc_title} — {chunk.headline}**"
                        f" *({chunk.topic})*\n> {chunk.text}\n"
                    )

            # Judge section
            if r.judge_status != "skipped":
                lines.append("\n---\n#### Response Quality\n")
                if r.generated_response:
                    preview = r.generated_response[:400]
                    if len(r.generated_response) > 400:
                        preview += "…"
                    lines.append(f"\n*Response:*\n> {preview}\n")
                if r.judge_status == "scored":
                    lines.append(
                        "\n| Dimension | Score | Rationale |\n|---|---|---|\n"
                        f"| Faithfulness | {r.faithfulness:.3f}"
                        f" | {r.faithfulness_rationale} |\n"
                        f"| Relevance | {r.relevance:.3f}"
                        f" | {r.relevance_rationale} |\n"
                        f"| Context Util | {r.context_utilization:.3f}"
                        f" | {r.context_utilization_rationale} |\n"
                        f"| Correctness | {r.answer_correctness:.3f}"
                        f" | {r.answer_correctness_rationale} |\n"
                        f"| **Aggregate** | **{r.aggregate:.3f}** | — |\n"
                    )
                elif r.judge_error:
                    lines.append(f"\n*Error:* {r.judge_error}\n")

            return "".join(lines), row_idx

        # ── Wire events ───────────────────────────────────────────────────

        file_input.change(
            on_file_change,
            inputs=[file_input],
            outputs=[run_btn, placeholder_md, detail_md],
        )
        run_btn.click(
            on_run_eval,
            inputs=[session_state, file_input, k_slider],
            outputs=[progress_md, summary_md, results_table, eval_results_state],
        )
        results_table.select(
            on_row_select,
            inputs=[eval_results_state],
            outputs=[detail_md, selected_idx_state],
        )
        session_state.change(
            lambda _s: ("", "", [], None, None),
            inputs=[session_state],
            outputs=[
                progress_md,
                summary_md,
                results_table,
                eval_results_state,
                selected_idx_state,
            ],
        )


# ── Formatters ────────────────────────────────────────────────────────────────


def _format_summary(
    rows: list[EvalRow],
    ret: EvalSummary,
    run_id: str | None,
    judge_ran: bool,
) -> str:
    lines: list[str] = []

    # Retrieval section
    lines.append(
        "### Retrieval Metrics\n\n"
        "| Metric | Score |\n|---|---|\n"
        f"| Mean MRR | {ret.mean_mrr:.4f} |\n"
        f"| Mean nDCG | {ret.mean_ndcg:.4f} |\n"
        f"| Mean Recall@{ret.k} | {ret.mean_recall_at_k:.4f} |\n"
        f"| Questions | {ret.total_questions} |\n"
    )

    if ret.category_scores:
        lines.append(
            "\n**Per-category:**\n\n"
            "| Category | N | MRR | nDCG | Recall@"
            + str(ret.k)
            + " |\n|---|---|---|---|---|\n"
        )
        for cat, m in ret.category_scores.items():
            lines.append(
                f"| {cat} | {m.question_count} |"
                f" {m.mean_mrr:.4f} | {m.mean_ndcg:.4f}"
                f" | {m.mean_recall_at_k:.4f} |\n"
            )

    # Response quality section
    if judge_ran:
        scored = [r for r in rows if r.judge_status == "scored"]
        n = len(rows)
        n_scored = len(scored)
        n_err = sum(1 for r in rows if r.judge_status == "error")
        n_parse = sum(1 for r in rows if r.judge_status == "parse_error")
        n_noresponse = sum(1 for r in rows if r.judge_status == "no_response")
        pct = 100 * n_scored / n if n else 0.0

        lines.append("\n---\n### Response Quality\n")
        if run_id:
            lines.append(f"\n**Run ID:** `{run_id}`\n")
        lines.append(
            f"\n| Status | Count |\n|---|---|\n"
            f"| Scored | {n_scored} ({pct:.1f}%) |\n"
            f"| Error | {n_err} |\n"
            f"| Parse error | {n_parse} |\n"
            f"| No response | {n_noresponse} |\n"
        )

        if scored:

            def _mean(vals: list) -> float:
                nums = [v for v in vals if v is not None]
                return sum(nums) / len(nums) if nums else 0.0

            lines.append(
                "\n| Dimension | Mean |\n|---|---|\n"
                f"| Faithfulness | {_mean([r.faithfulness for r in scored]):.3f} |\n"
                f"| Relevance | {_mean([r.relevance for r in scored]):.3f} |\n"
                f"| Context Util"
                f" | {_mean([r.context_utilization for r in scored]):.3f} |\n"
                f"| Correctness"
                f" | {_mean([r.answer_correctness for r in scored]):.3f} |\n"
                f"| **Aggregate**"
                f" | **{_mean([r.aggregate for r in scored]):.3f}** |\n"
            )
    else:
        lines.append(
            "\n---\n*Response quality not run — "
            "set `JUDGE_PROVIDER` and `JUDGE_MODEL` to enable.*\n"
        )

    return "".join(lines)
