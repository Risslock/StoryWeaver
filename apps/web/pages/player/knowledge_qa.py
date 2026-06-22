"""Player Knowledge Q&A tab — RAG-powered chat over player-visible content."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import gradio as gr
from core.config import settings
from core.models import KnowledgeDocument
from core.schemas import CampaignSession
from sqlalchemy import select
from storage.sqlite.adapter import SQLiteBackend

_backend = SQLiteBackend(settings.database_url)

_STALE_MINUTES = 15


def _progress_bar(done: int, total: int, width: int = 10) -> str:
    pct = int(done * 100 / total) if total > 0 else 0
    filled = round(done * width / total) if total > 0 else 0
    bar = "▓" * filled + "░" * (width - filled)
    return f"{bar} {pct}%"


def _format_status(doc: KnowledgeDocument) -> str:
    if doc.ingestion_status == "ready":
        return "✅ ready"
    if doc.ingestion_status == "processing":
        age = datetime.now(UTC) - doc.updated_at.replace(tzinfo=UTC)
        if age > timedelta(minutes=_STALE_MINUTES):
            return "⚠️ stalled"
        total = doc.chunk_count
        done = doc.chunks_processed
        if total is not None and done is not None and done > 0:
            return f"⏳ {done}/{total} {_progress_bar(done, total)}"
        if total is not None:
            return f"⏳ enriching ({total} chunks)…"
        return "⏳ processing"
    if doc.ingestion_status == "failed":
        return f"❌ {doc.error_message or 'unknown error'}"
    return doc.ingestion_status


def _docs_to_rows(docs: list[KnowledgeDocument]) -> list[list[str]]:
    return [
        [
            d.title,
            _format_status(d),
            str(d.chunk_count) if d.chunk_count is not None else "—",
            d.created_at.strftime("%Y-%m-%d %H:%M") if d.created_at else "—",
        ]
        for d in docs
    ]


def build_knowledge_qa_page(session_state: gr.State) -> None:
    """Build the Player Knowledge Q&A tab. Must be called inside a gr.Blocks context."""

    with gr.Tab("Knowledge Q&A"):
        gr.Markdown("## Knowledge Q&A")

        # ── Q&A Chat ─────────────────────────────────────────────────────
        with gr.Group():
            gr.Markdown("### Ask a Question")
            chatbot = gr.Chatbot(
                label="Knowledge Q&A",
                elem_id="player-knowledge-chatbot",
                height=380,
                value=[],
            )
            with gr.Row():
                ask_input = gr.Textbox(
                    label="",
                    placeholder="Ask about rules, lore, or world…",
                    lines=1,
                    scale=5,
                    elem_id="player-knowledge-input",
                )
                ask_btn = gr.Button(
                    "Ask",
                    variant="primary",
                    scale=1,
                    min_width=80,
                    elem_id="player-knowledge-ask-btn",
                )

        # ── My Contributions ──────────────────────────────────────────────
        with gr.Group():
            gr.Markdown("### My Contributions")
            gr.Markdown(
                "Upload Markdown files (session notes, lore summaries, faction overviews). "
                "PDF upload is not available for players."
            )

            file_upload = gr.File(
                label="Select Markdown file (.md)",
                file_types=[".md"],
                elem_id="player-knowledge-file-upload",
            )
            access_dd = gr.Dropdown(
                choices=["Player-visible", "GM-only"],
                value="Player-visible",
                label="Access",
                elem_id="player-knowledge-access",
            )
            upload_btn = gr.Button(
                "Upload & Ingest",
                variant="secondary",
                interactive=False,
                elem_id="player-knowledge-upload-btn",
            )
            upload_status = gr.Markdown(
                "",
                elem_id="player-knowledge-upload-status",
            )
            with gr.Row(visible=False) as overwrite_row:
                confirm_btn = gr.Button(
                    "Confirm — replace existing",
                    variant="stop",
                    elem_id="player-knowledge-confirm-overwrite",
                )
                cancel_btn = gr.Button(
                    "Cancel",
                    variant="secondary",
                    elem_id="player-knowledge-cancel-overwrite",
                )

            gr.Markdown("#### My Uploaded Files")
            doc_table = gr.Dataframe(
                headers=["Title", "Status", "Chunks", "Uploaded"],
                datatype=["str", "str", "str", "str"],
                value=[],
                interactive=False,
                elem_id="player-knowledge-doc-table",
            )
            timer = gr.Timer(value=5)

        # ── Pending overwrite state ───────────────────────────────────────
        pending_file: gr.State = gr.State(value=None)

        # ── Helpers ───────────────────────────────────────────────────────

        async def _load_my_docs(state: CampaignSession | None) -> list[list[str]]:
            if state is None:
                return []
            try:
                async with await _backend.get_session() as db:
                    result = await db.execute(
                        select(KnowledgeDocument).where(
                            KnowledgeDocument.campaign_id == state.campaign_id,
                            KnowledgeDocument.scope == "campaign",
                        ).order_by(KnowledgeDocument.created_at.desc())
                    )
                    docs = list(result.scalars().all())
                return _docs_to_rows(docs)
            except Exception:
                return []

        # ── Event: ask question ───────────────────────────────────────────

        async def on_ask(
            state: CampaignSession | None,
            history: list[dict[str, Any]],
            question: str,
        ) -> tuple[list[dict[str, Any]], str]:
            if state is None:
                return history, question
            if not question.strip():
                return history, ""
            try:
                from services.knowledge import ask_question
                answer, chunks = await ask_question(
                    question=question.strip(),
                    campaign_id=state.campaign_id,
                    role="player",
                )
            except Exception as exc:
                from core.errors import ProviderUnavailableError
                if isinstance(exc, ProviderUnavailableError):
                    msg = f"Knowledge service unavailable: {exc}"
                else:
                    msg = f"Error: {exc}"
                history = list(history) + [
                    {"role": "user", "content": question.strip()},
                    {"role": "assistant", "content": msg},
                ]
                return history, ""

            if not chunks:
                full = "I couldn't find relevant information for your question in the current knowledge base."
            else:
                citation_lines = ["\n\n**Sources:**"]
                for c in chunks[:5]:
                    excerpt = c.text[:200].rstrip()
                    if len(c.text) > 200:
                        excerpt += "…"
                    citation_lines.append(
                        f"\n> **{c.doc_title} — {c.headline}** *({c.topic})*\n> {excerpt}"
                    )
                full = answer + "".join(citation_lines)

            history = list(history) + [
                {"role": "user", "content": question.strip()},
                {"role": "assistant", "content": full},
            ]
            return history, ""

        # ── Event: file selected ──────────────────────────────────────────

        def on_file_change(f: Any) -> dict[str, Any]:
            return gr.update(interactive=f is not None)

        # ── Event: upload ─────────────────────────────────────────────────

        async def on_upload(
            state: CampaignSession | None,
            f: Any,
            access_val: str,
        ) -> tuple[str, Any, Any, Any, Any]:
            hidden_row = gr.update(visible=False)
            if state is None:
                return "Error: not in a campaign session.", hidden_row, gr.update(), gr.update(), None
            if f is None:
                return "No file selected.", hidden_row, gr.update(), gr.update(), None
            try:
                from services.knowledge import check_duplicate, submit_document
                file_path: str = f.name if hasattr(f, "name") else str(f)
                filename = file_path.split("/")[-1].split("\\")[-1]
                title = filename.rsplit(".", 1)[0]
                access_map = {"Player-visible": "player_visible", "GM-only": "gm_only"}
                access_default = access_map.get(access_val, "player_visible")

                existing = await check_duplicate(title, "campaign", state.campaign_id)
                if existing is not None:
                    return (
                        f"⚠️ A document named **{title}** already exists. Confirm to replace it.",
                        gr.update(visible=True),
                        gr.update(),
                        gr.update(),
                        (file_path, filename, title, "campaign", state.campaign_id, access_default, "markdown"),
                    )

                await submit_document(
                    file_path=file_path,
                    filename=filename,
                    title=title,
                    scope="campaign",
                    campaign_id=state.campaign_id,
                    access_level_default=access_default,
                    format="markdown",
                )
                return "⏳ Ingestion started.", hidden_row, gr.update(), gr.update(), None
            except Exception as exc:
                return f"Upload failed: {exc}", hidden_row, gr.update(), gr.update(), None

        async def on_confirm_overwrite(
            state: CampaignSession | None,
            pf: Any,
        ) -> tuple[str, Any]:
            if pf is None or state is None:
                return "Nothing to confirm.", gr.update(visible=False)
            file_path, filename, title, scope, campaign_id_for_doc, access_default, fmt = pf
            try:
                from services.knowledge import check_duplicate, confirm_overwrite, submit_document
                existing = await check_duplicate(title, scope, campaign_id_for_doc)
                if existing is not None:
                    await confirm_overwrite(existing.id, file_path)
                else:
                    await submit_document(
                        file_path=file_path,
                        filename=filename,
                        title=title,
                        scope=scope,
                        campaign_id=campaign_id_for_doc,
                        access_level_default=access_default,
                        format=fmt,
                    )
                return "⏳ Re-ingestion started.", gr.update(visible=False)
            except Exception as exc:
                return f"Overwrite failed: {exc}", gr.update(visible=False)

        def on_cancel_overwrite() -> tuple[str, Any]:
            return "Upload cancelled.", gr.update(visible=False)

        # ── Event: refresh doc table ──────────────────────────────────────

        async def on_refresh(state: CampaignSession | None) -> list[list[str]]:
            return await _load_my_docs(state)

        # ── Wire events ───────────────────────────────────────────────────

        ask_btn.click(
            on_ask,
            inputs=[session_state, chatbot, ask_input],
            outputs=[chatbot, ask_input],
        )
        ask_input.submit(
            on_ask,
            inputs=[session_state, chatbot, ask_input],
            outputs=[chatbot, ask_input],
        )

        file_upload.change(on_file_change, inputs=[file_upload], outputs=[upload_btn])

        upload_btn.click(
            on_upload,
            inputs=[session_state, file_upload, access_dd],
            outputs=[upload_status, overwrite_row, confirm_btn, cancel_btn, pending_file],
        )
        confirm_btn.click(
            on_confirm_overwrite,
            inputs=[session_state, pending_file],
            outputs=[upload_status, overwrite_row],
        )
        cancel_btn.click(
            on_cancel_overwrite,
            outputs=[upload_status, overwrite_row],
        )

        refresh_btn = gr.Button("↻ Refresh", size="sm")
        refresh_btn.click(on_refresh, inputs=[session_state], outputs=[doc_table])
        timer.tick(on_refresh, inputs=[session_state], outputs=[doc_table])

        session_state.change(
            lambda s: ([], []),
            inputs=[session_state],
            outputs=[chatbot, doc_table],
        )
        session_state.change(
            on_refresh,
            inputs=[session_state],
            outputs=[doc_table],
        )
