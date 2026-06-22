"""GM Knowledge Q&A tab — RAG-powered chat over ingested rulebooks and lore."""

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
    rows = []
    for d in docs:
        rows.append([
            d.title,
            d.format.upper(),
            d.scope,
            _format_status(d),
            str(d.chunk_count) if d.chunk_count is not None else "—",
            d.created_at.strftime("%Y-%m-%d %H:%M") if d.created_at else "—",
        ])
    return rows


def build_knowledge_qa_page(session_state: gr.State) -> None:
    """Build the GM Knowledge Q&A tab. Must be called inside a gr.Blocks context."""

    with gr.Tab("Knowledge Q&A"):
        gr.Markdown("## Knowledge Q&A")

        # ── Q&A Chat ─────────────────────────────────────────────────────
        with gr.Group():
            gr.Markdown("### Ask a Question")
            chatbot = gr.Chatbot(
                label="Knowledge Q&A",
                elem_id="gm-knowledge-chatbot",
                height=380,
                value=[],
            )
            with gr.Row():
                ask_input = gr.Textbox(
                    label="",
                    placeholder="Ask about rules, lore, or world…",
                    lines=1,
                    scale=5,
                    elem_id="gm-knowledge-input",
                )
                ask_btn = gr.Button(
                    "Ask",
                    variant="primary",
                    scale=1,
                    min_width=80,
                    elem_id="gm-knowledge-ask-btn",
                )

        # ── Knowledge Base management ─────────────────────────────────────
        with gr.Group():
            gr.Markdown("### Knowledge Base")

            with gr.Accordion("Upload Document", open=True):
                file_upload = gr.File(
                    label="Select PDF or Markdown file",
                    file_types=[".pdf", ".md"],
                    elem_id="gm-knowledge-file-upload",
                )
                with gr.Row():
                    scope_dd = gr.Dropdown(
                        choices=["Global (shared)", "Campaign-specific"],
                        value="Global (shared)",
                        label="Scope",
                        elem_id="gm-knowledge-scope",
                    )
                    access_dd = gr.Dropdown(
                        choices=["Auto (LLM infers)", "Player-visible", "GM-only"],
                        value="Auto (LLM infers)",
                        label="Access default",
                        elem_id="gm-knowledge-access",
                    )
                upload_btn = gr.Button(
                    "Upload & Ingest",
                    variant="secondary",
                    interactive=False,
                    elem_id="gm-knowledge-upload-btn",
                )
                upload_status = gr.Markdown(
                    "",
                    elem_id="gm-knowledge-upload-status",
                )
                with gr.Row(visible=False) as overwrite_row:
                    confirm_btn = gr.Button(
                        "Confirm — replace existing",
                        variant="stop",
                        elem_id="gm-knowledge-confirm-overwrite",
                    )
                    cancel_btn = gr.Button(
                        "Cancel",
                        variant="secondary",
                        elem_id="gm-knowledge-cancel-overwrite",
                    )

            gr.Markdown("#### Ingested Documents")
            doc_table = gr.Dataframe(
                headers=["Title", "Format", "Scope", "Status", "Chunks", "Uploaded"],
                datatype=["str", "str", "str", "str", "str", "str"],
                value=[],
                interactive=False,
                elem_id="gm-knowledge-doc-table",
            )
            with gr.Row():
                refresh_btn = gr.Button(
                    "↻ Refresh",
                    size="sm",
                    elem_id="gm-knowledge-refresh-btn",
                )
            timer = gr.Timer(value=5)

        # ── Pending overwrite state ───────────────────────────────────────
        pending_file: gr.State = gr.State(value=None)

        # ── Helpers ───────────────────────────────────────────────────────

        async def _load_docs(state: CampaignSession | None) -> list[list[str]]:
            if state is None:
                return []
            try:
                from services.knowledge import list_documents
                docs = await list_documents(state.campaign_id)
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
                    role=state.role,
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

        def on_scope_auto(f: Any) -> dict[str, Any]:
            if f is None:
                return gr.update()
            name = getattr(f, "name", "") if not isinstance(f, str) else f
            if name.lower().endswith(".md"):
                return gr.update(value="Campaign-specific")
            return gr.update(value="Global (shared)")

        # ── Event: upload ─────────────────────────────────────────────────

        async def on_upload(
            state: CampaignSession | None,
            f: Any,
            scope_val: str,
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
                scope = "global" if "Global" in scope_val else "campaign"
                campaign_id_for_doc = None if scope == "global" else state.campaign_id
                access_map = {
                    "Auto (LLM infers)": None,
                    "Player-visible": "player_visible",
                    "GM-only": "gm_only",
                }
                access_default = access_map.get(access_val)
                fmt = "pdf" if file_path.lower().endswith(".pdf") else "markdown"

                existing = await check_duplicate(title, scope, campaign_id_for_doc)
                if existing is not None:
                    return (
                        f"⚠️ A document named **{title}** already exists. Confirm to replace it.",
                        gr.update(visible=True),
                        gr.update(),
                        gr.update(),
                        (file_path, filename, title, scope, campaign_id_for_doc, access_default, fmt),
                    )

                await submit_document(
                    file_path=file_path,
                    filename=filename,
                    title=title,
                    scope=scope,
                    campaign_id=campaign_id_for_doc,
                    access_level_default=access_default,
                    format=fmt,
                )
                return "⏳ Ingestion started. Document will appear in the table below.", hidden_row, gr.update(), gr.update(), None
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
            return await _load_docs(state)

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
        file_upload.change(on_scope_auto, inputs=[file_upload], outputs=[scope_dd])

        upload_btn.click(
            on_upload,
            inputs=[session_state, file_upload, scope_dd, access_dd],
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
