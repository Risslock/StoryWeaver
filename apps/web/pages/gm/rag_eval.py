"""GM-only RAG Evaluation tab — load JSONL, run eval, inspect results."""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING

import gradio as gr
from core.errors import ProviderUnavailableError
from core.schemas import CampaignSession
from rag.knowledge.evaluator import EvalSummary, RetrievalEvalResult

if TYPE_CHECKING:
    from services.response_eval import ResponseEvalRow


def _judge_env_available() -> bool:
    """Return True if JUDGE_PROVIDER and JUDGE_MODEL are set in the environment."""
    return bool(os.environ.get("JUDGE_PROVIDER", "").strip()) and bool(
        os.environ.get("JUDGE_MODEL", "").strip()
    )


def build_rag_eval_page(session_state: gr.State) -> None:
    """Build the GM RAG Evaluation tab. Must be called inside a gr.Blocks context."""

    _judge_ready = _judge_env_available()

    with gr.Tab("RAG Evaluation"):
        gr.Markdown("## RAG Retrieval Evaluation")

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

        # ── Status ────────────────────────────────────────────────────────
        placeholder_md = gr.Markdown(
            "Load a JSONL file to begin evaluation.",
            visible=True,
            elem_id="rag-eval-placeholder",
        )
        progress_md = gr.Markdown("", elem_id="rag-eval-progress")

        # ── Aggregate summary ─────────────────────────────────────────────
        summary_md = gr.Markdown("", elem_id="rag-eval-summary")

        # ── Per-question results table ─────────────────────────────────────
        _headers = [
            "#", "Question", "Category", "MRR", "nDCG", "Recall@k", "Found/Total"
        ]
        _dtypes = ["number", "str", "str", "number", "number", "number", "str"]
        results_table = gr.Dataframe(
            headers=_headers,
            datatype=_dtypes,  # type: ignore[arg-type]
            interactive=False,
            elem_id="rag-eval-table",
        )

        # ── Drill-down detail panel ────────────────────────────────────────
        detail_md = gr.Markdown("", elem_id="rag-eval-detail")

        # ── State ─────────────────────────────────────────────────────────
        eval_results_state: gr.State = gr.State(value=None)
        selected_idx_state: gr.State = gr.State(value=None)

        # ── Response Quality section ──────────────────────────────────────
        with gr.Accordion("Response Quality (LLM Judge)", open=False):
            if not _judge_ready:
                gr.Markdown(
                    "> **JUDGE_PROVIDER / JUDGE_MODEL not set** — "
                    "set these environment variables and restart to enable "
                    "response quality evaluation."
                )

            run_judge_btn = gr.Button(
                "Run Response Quality Eval",
                variant="secondary",
                interactive=False,
                elem_id="rag-eval-judge-btn",
            )

            judge_progress_md = gr.Markdown("", elem_id="rag-eval-judge-progress")
            judge_summary_md = gr.Markdown(
                "_Load a JSONL file and click Run to evaluate response quality._"
                if _judge_ready
                else "_JUDGE_PROVIDER / JUDGE_MODEL not configured._",
                elem_id="rag-eval-judge-summary",
            )

            _judge_headers = [
                "#", "Question", "Faithfulness", "Relevance",
                "Context Util", "Aggregate", "Status",
            ]
            _judge_dtypes = [
                "number", "str", "number", "number", "number", "number", "str"
            ]
            judge_results_table = gr.Dataframe(
                headers=_judge_headers,
                datatype=_judge_dtypes,  # type: ignore[arg-type]
                interactive=False,
                elem_id="rag-eval-judge-table",
            )

            judge_detail_md = gr.Markdown("", elem_id="rag-eval-judge-detail")
            judge_results_state: gr.State = gr.State(value=None)

        # ── Event handlers ────────────────────────────────────────────────

        def on_file_change(f: object) -> tuple[dict, dict, dict, dict]:  # type: ignore[type-arg]
            has_file = f is not None
            return (
                gr.update(interactive=has_file),
                gr.update(visible=not has_file),
                gr.update(value=""),
                gr.update(interactive=has_file and _judge_ready),
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

            yield (
                gr.update(value="Loading questions…"),
                gr.update(value=""),
                gr.update(value=[]),
                None,
            )

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

            total = len(questions)
            if total == 0:
                yield (
                    gr.update(value="JSONL file is empty."),
                    gr.update(value=""),
                    gr.update(value=[]),
                    None,
                )
                return

            from rag.knowledge.evaluator import aggregate_results, evaluate_question
            from rag.knowledge.retriever import ChromaKnowledgeRetriever

            retriever = ChromaKnowledgeRetriever()
            campaign_id_str = str(state.campaign_id).replace("-", "")
            accumulated: list[RetrievalEvalResult] = []

            for idx, q in enumerate(questions, start=1):
                yield (
                    gr.update(value=f"Evaluating question {idx} / {total}…"),
                    gr.update(value=""),
                    gr.update(value=_results_to_rows(accumulated)),
                    accumulated if accumulated else None,
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
                        gr.update(value=_results_to_rows(accumulated)),
                        accumulated if accumulated else None,
                    )
                    return
                except Exception:
                    chunks = []

                result = evaluate_question(q, chunks, k)
                accumulated.append(result)

            summary = aggregate_results(accumulated)
            yield (
                gr.update(value="Evaluation complete."),
                gr.update(value=_format_summary(summary)),
                gr.update(value=_results_to_rows(accumulated)),
                accumulated,
            )

        async def on_run_judge(
            state: CampaignSession | None,
            f: object,
        ) -> AsyncGenerator[tuple[object, ...], None]:
            import uuid as _uuid
            from datetime import UTC, datetime

            from rag.evaluation.factory import get_judge_provider
            from rag.evaluation.judge import JudgeEvaluator
            from rag.evaluation.store import EvaluationStore
            from rag.knowledge.test_questions import load_test_questions
            from services.response_eval import (
                ResponseEvalRow,
                build_judge_summary,
                run_response_eval_question,
            )

            _blank = (
                gr.update(value=""),
                gr.update(value=""),
                gr.update(value=[]),
                None,
            )

            if state is None:
                yield (gr.update(value="Error: not in a campaign session."),
                       *_blank[1:])
                return
            if f is None:
                yield (gr.update(value="No file selected."), *_blank[1:])
                return
            if not _judge_ready:
                yield (
                    gr.update(value="JUDGE_PROVIDER / JUDGE_MODEL not configured."),
                    *_blank[1:],
                )
                return

            file_path: str = f.name if hasattr(f, "name") else str(f)  # type: ignore[union-attr]

            try:
                questions = load_test_questions(file_path)
            except Exception as exc:
                yield (gr.update(value=f"Failed to load JSONL: {exc}"), *_blank[1:])
                return

            if not questions:
                yield (gr.update(value="JSONL file is empty."), *_blank[1:])
                return

            judge_provider_name = os.environ.get("JUDGE_PROVIDER", "").strip()
            judge_model_name = os.environ.get("JUDGE_MODEL", "").strip()

            try:
                provider = get_judge_provider(judge_provider_name, judge_model_name)
            except OSError as exc:
                yield (
                    gr.update(value=f"Judge configuration error: {exc}"),
                    *_blank[1:],
                )
                return

            evaluator = JudgeEvaluator(
                provider=provider,
                judge_provider_name=judge_provider_name,
                judge_model_name=judge_model_name,
            )

            now = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
            uid8 = str(_uuid.uuid4()).replace("-", "")[:8]
            run_id = f"{now}-{uid8}"

            store = EvaluationStore()
            await store.initialize()

            campaign_id = state.campaign_id
            role = state.role
            total = len(questions)
            accumulated: list[ResponseEvalRow] = []

            yield (
                gr.update(value=f"Starting judge run `{run_id}` — {total} questions…"),
                gr.update(value=""),
                gr.update(value=[]),
                None,
            )

            for idx, q in enumerate(questions, start=1):
                yield (
                    gr.update(value=f"Scoring question {idx} / {total}…"),
                    gr.update(value=""),
                    gr.update(value=[r.to_list() for r in accumulated]),
                    accumulated if accumulated else None,
                )
                try:
                    row = await run_response_eval_question(
                        question=q.question,
                        category=q.category,
                        campaign_id=campaign_id,
                        role=role,
                        judge_evaluator=evaluator,
                        store=store,
                        run_id=run_id,
                        index=idx,
                    )
                except Exception as exc:
                    row = ResponseEvalRow(
                        index=idx,
                        question=q.question,
                        faithfulness="—",
                        relevance="—",
                        context_utilization="—",
                        aggregate="—",
                        status=f"error: {exc}",
                    )
                accumulated.append(row)

            summary = build_judge_summary(accumulated, run_id)
            yield (
                gr.update(value=f"Complete — run_id: `{run_id}`"),
                gr.update(value=_format_judge_summary(summary)),
                gr.update(value=[r.to_list() for r in accumulated]),
                accumulated,
            )

        def on_judge_row_select(
            evt: gr.SelectData,
            results: list[ResponseEvalRow] | None,
        ) -> str:
            if results is None or evt.index is None:
                return ""
            row_idx = evt.index[0]
            if row_idx >= len(results):
                return ""
            r = results[row_idx]
            lines = [f"### {r.question}\n\n"]
            lines.append(f"**Status:** {r.status}\n\n")
            if r.status == "scored":
                lines.append("| Dimension | Score |\n|---|---|\n")
                lines.append(f"| Faithfulness | {r.faithfulness} |\n")
                lines.append(f"| Relevance | {r.relevance} |\n")
                lines.append(f"| Context Utilization | {r.context_utilization} |\n")
                lines.append(f"| **Aggregate** | **{r.aggregate}** |\n")
            return "".join(lines)

        def on_row_select(
            evt: gr.SelectData,
            results: list[RetrievalEvalResult] | None,
        ) -> tuple[str, int | None]:
            if results is None or evt.index is None:
                return "", None
            row_idx = evt.index[0]
            if row_idx >= len(results):
                return "", None
            r = results[row_idx]
            lines = [f"### {r.question}\n"]
            lines.append("**Keyword ranks:**\n")
            lines.append("| Keyword | Rank |\n|---|---|\n")
            for kw, rank in r.keyword_ranks.items():
                rank_str = str(rank) if rank is not None else "not found"
                lines.append(f"| {kw} | {rank_str} |\n")
            lines.append("\n**Retrieved chunks:**\n")
            for i, chunk in enumerate(r.retrieved_chunks, start=1):
                title_line = (
                    f"\n**{i}. {chunk.doc_title} — {chunk.headline}**"
                    f" *({chunk.topic})*\n"
                )
                lines.append(title_line + f"> {chunk.text}\n")
            return "".join(lines), row_idx

        # ── Wire events ───────────────────────────────────────────────────

        file_input.change(
            on_file_change,
            inputs=[file_input],
            outputs=[run_btn, placeholder_md, detail_md, run_judge_btn],
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

        run_judge_btn.click(
            on_run_judge,
            inputs=[session_state, file_input],
            outputs=[
                judge_progress_md,
                judge_summary_md,
                judge_results_table,
                judge_results_state,
            ],
        )

        judge_results_table.select(
            on_judge_row_select,
            inputs=[judge_results_state],
            outputs=[judge_detail_md],
        )

        session_state.change(
            lambda _s: ("", "", [], None, None, "", "", [], None),
            inputs=[session_state],
            outputs=[
                progress_md,
                summary_md,
                results_table,
                eval_results_state,
                selected_idx_state,
                judge_progress_md,
                judge_summary_md,
                judge_results_table,
                judge_results_state,
            ],
        )


# ── Formatters ────────────────────────────────────────────────────────────────


def _results_to_rows(results: list[RetrievalEvalResult]) -> list[list]:  # type: ignore[type-arg]
    rows = []
    for i, r in enumerate(results, start=1):
        rows.append([
            i,
            r.question,
            r.category,
            round(r.mrr, 4),
            round(r.ndcg, 4),
            round(r.recall_at_k, 4),
            f"{r.keywords_found}/{r.total_keywords}",
        ])
    return rows


def _format_judge_summary(summary: object) -> str:
    from services.response_eval import ResponseEvalSummary

    s: ResponseEvalSummary = summary  # type: ignore[assignment]
    pct = 100 * s.scored / s.total if s.total else 0.0
    lines = [
        f"### Response Quality Summary\n\n"
        f"**Run ID:** `{s.run_id}`\n\n"
        "| Metric | Value |\n|---|---|\n"
        f"| Total questions | {s.total} |\n"
        f"| Scored | {s.scored} ({pct:.1f}%) |\n"
        f"| Errors | {s.error} |\n"
        f"| Parse errors | {s.parse_error} |\n"
        f"| No response | {s.no_response} |\n"
    ]
    if s.mean_aggregate is not None:
        lines.append(
            "\n| Dimension | Mean Score |\n|---|---|\n"
            f"| Faithfulness | {s.mean_faithfulness:.3f} |\n"
            f"| Relevance | {s.mean_relevance:.3f} |\n"
            f"| Context Utilization | {s.mean_context_utilization:.3f} |\n"
            f"| **Aggregate** | **{s.mean_aggregate:.3f}** |\n"
        )
    return "".join(lines)


def _format_summary(summary: EvalSummary) -> str:
    lines = [
        "### Aggregate Summary\n\n"
        "| Metric | Score |\n|---|---|\n"
        f"| Mean MRR | {summary.mean_mrr:.4f} |\n"
        f"| Mean nDCG | {summary.mean_ndcg:.4f} |\n"
        f"| Mean Recall@{summary.k} | {summary.mean_recall_at_k:.4f} |\n"
        f"| Questions | {summary.total_questions} |\n"
    ]

    if summary.category_scores:
        lines.append(
            "\n### Per-Category Results\n\n"
            "| Category | Questions | MRR | nDCG | Recall@"
            + str(summary.k)
            + " |\n|---|---|---|---|---|\n"
        )
        for cat, m in summary.category_scores.items():
            lines.append(
                f"| {cat} | {m.question_count} |"
                f" {m.mean_mrr:.4f} | {m.mean_ndcg:.4f} | {m.mean_recall_at_k:.4f} |\n"
            )

    return "".join(lines)
