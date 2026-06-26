"""GM-only RAG Evaluation tab — load JSONL, run eval, inspect results."""

from __future__ import annotations

from collections.abc import AsyncGenerator

import gradio as gr
from core.errors import ProviderUnavailableError
from core.schemas import CampaignSession
from rag.knowledge.evaluator import EvalSummary, RetrievalEvalResult


def build_rag_eval_page(session_state: gr.State) -> None:
    """Build the GM RAG Evaluation tab. Must be called inside a gr.Blocks context."""

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

        # ── Event handlers ────────────────────────────────────────────────

        def on_file_change(f: object) -> tuple[dict, dict, dict]:  # type: ignore[type-arg]
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
