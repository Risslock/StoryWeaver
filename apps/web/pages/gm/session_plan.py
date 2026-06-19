"""GM session planning tab — generate, edit, and persist session plans."""

from __future__ import annotations

import uuid
from typing import Any

import gradio as gr
from sqlalchemy import select

from core.config import settings
from core.models import SessionPlan
from core.schemas import CampaignSession
from story.session import list_sessions
from storage.sqlite.adapter import SQLiteBackend

_backend = SQLiteBackend(settings.database_url)


def build_session_plan_page(session_state: gr.State) -> None:
    """Build the GM session planning tab. Must be called inside a gr.Blocks context."""

    with gr.Tab("Session Plan"):
        gr.Markdown("## Session Planning")
        gr.Markdown(
            "Generate an AI-assisted plan drawing on campaign history, "
            "then edit and save it for future reference."
        )

        # ── Session Selection ─────────────────────────────────────────────
        with gr.Row():
            session_selector = gr.Dropdown(
                label="Plan for Session",
                choices=["Next Session"],
                value="Next Session",
                interactive=True,
                scale=3,
            )
            refresh_btn = gr.Button("↻ Refresh", scale=1, min_width=100)

        # ── Focus Hints ───────────────────────────────────────────────────
        focus_hints_input = gr.Textbox(
            label="Focus Areas (optional, one per line)",
            placeholder="e.g.\nResolve the plot thread about the missing merchant\nIntroduce the Brotherhood faction",
            lines=3,
        )

        # ── Generate Button ───────────────────────────────────────────────
        with gr.Row():
            generate_btn = gr.Button(
                "Generate Plan",
                variant="primary",
                interactive=False,  # enabled when ai_available=True
            )
            plan_status = gr.Markdown("")

        # ── Plan Editor ───────────────────────────────────────────────────
        gr.Markdown("### Plan Editor")
        gr.Markdown("*Edit the plan below, then save. The preview updates on save.*")

        plan_editor = gr.Code(
            label="Plan (Markdown)",
            language="markdown",
            lines=20,
            interactive=True,
        )

        with gr.Row():
            save_btn = gr.Button("Save Plan", variant="secondary")
            save_status = gr.Markdown("")

        # ── Live Preview ──────────────────────────────────────────────────
        gr.Markdown("### Preview")
        plan_preview = gr.Markdown("")

        # ── Internal state ────────────────────────────────────────────────
        session_map_state: gr.State = gr.State(value={})
        plan_id_state: gr.State = gr.State(value=None)

        # ── Helpers ───────────────────────────────────────────────────────

        async def _load_sessions(
            state: CampaignSession | None,
        ) -> tuple[dict[str, str], list[str]]:
            if state is None:
                return {}, ["Next Session"]
            async with await _backend.get_session() as db:
                sessions = await list_sessions(db, state.campaign_id)
            session_map = {
                f"Session {s.session_number}: {s.title}": str(s.id)
                for s in sessions
            }
            choices = ["Next Session"] + list(session_map.keys())
            return session_map, choices

        async def _next_session_number(state: CampaignSession) -> int:
            async with await _backend.get_session() as db:
                sessions = await list_sessions(db, state.campaign_id)
            return (max(s.session_number for s in sessions) + 1) if sessions else 1

        async def load_page(
            state: CampaignSession | None,
        ) -> tuple[Any, dict, Any, str, str, str, None, str]:
            session_map, choices = await _load_sessions(state)
            ai_ok = state.ai_available if state is not None else False
            return (
                gr.update(choices=choices, value="Next Session"),
                session_map,
                gr.update(interactive=ai_ok),
                "",
                "",
                "",
                None,
                "",
            )

        async def on_session_change(
            state: CampaignSession | None,
            selected: str,
            session_map: dict[str, str],
        ) -> tuple[str, str, str | None, str]:
            """Load an existing plan for the selected session when available."""
            if state is None or not selected:
                return "", "", None, ""

            session_id: uuid.UUID | None = None
            if selected != "Next Session":
                raw = session_map.get(selected)
                if raw:
                    session_id = uuid.UUID(raw)

            async with await _backend.get_session() as db:
                stmt = select(SessionPlan).where(
                    SessionPlan.campaign_id == state.campaign_id
                )
                if session_id is not None:
                    stmt = stmt.where(SessionPlan.session_id == session_id)
                else:
                    stmt = stmt.where(SessionPlan.session_id.is_(None))
                result = await db.execute(stmt)
                existing = result.scalar_one_or_none()

            if existing is not None:
                return existing.content, existing.content, str(existing.id), "✓ Existing plan loaded."
            return "", "", None, ""

        async def on_generate(
            state: CampaignSession | None,
            selected: str,
            session_map: dict[str, str],
            focus_raw: str,
        ) -> tuple[str, str, str]:
            if state is None:
                return "", "*Not in a campaign session.*", ""
            if not state.ai_available:
                return "", "*AI features unavailable in degraded mode.*", ""

            focus_hints = [line.strip() for line in focus_raw.splitlines() if line.strip()]

            if selected == "Next Session":
                session_number = await _next_session_number(state)
            else:
                try:
                    session_number = int(selected.split(":")[0].replace("Session", "").strip())
                except (ValueError, IndexError):
                    session_number = await _next_session_number(state)

            from agents.gm_agent.gm_agent import GenerateSessionPlanInput, build_gm_agent_tools

            try:
                async with await _backend.get_session() as db:
                    tools = build_gm_agent_tools(state.campaign_id, db)
                    inp = GenerateSessionPlanInput(
                        campaign_id=state.campaign_id,
                        session_number=session_number,
                        focus_hints=focus_hints,
                    )
                    result = await tools["generate_session_plan"](inp)
            except Exception as exc:
                return "", f"*Plan generation failed: {exc}*", ""

            return result.plan_markdown, "✓ Plan generated — review and save below.", result.plan_markdown

        async def on_save(
            state: CampaignSession | None,
            selected: str,
            session_map: dict[str, str],
            plan_content: str,
            plan_id: str | None,
        ) -> tuple[str | None, str, str]:
            if state is None:
                return None, "*Not in a campaign session.*", ""
            if not plan_content or not plan_content.strip():
                return plan_id, "*Cannot save an empty plan.*", ""

            session_id: uuid.UUID | None = None
            if selected != "Next Session":
                raw = session_map.get(selected)
                if raw:
                    session_id = uuid.UUID(raw)

            async with await _backend.get_session() as db:
                if plan_id is not None:
                    result = await db.execute(
                        select(SessionPlan).where(SessionPlan.id == uuid.UUID(plan_id))
                    )
                    plan = result.scalar_one_or_none()
                    if plan is not None:
                        plan.content = plan_content.strip()
                        await db.commit()
                        await db.refresh(plan)
                        return str(plan.id), "✓ Plan saved.", plan_content

                plan = SessionPlan(
                    campaign_id=state.campaign_id,
                    session_id=session_id,
                    content=plan_content.strip(),
                )
                db.add(plan)
                await db.commit()
                await db.refresh(plan)
                return str(plan.id), "✓ Plan saved.", plan_content

        # ── Wire events ───────────────────────────────────────────────────

        _page_outputs = [
            session_selector,
            session_map_state,
            generate_btn,
            plan_status,
            plan_editor,
            plan_preview,
            plan_id_state,
            save_status,
        ]

        session_state.change(load_page, inputs=[session_state], outputs=_page_outputs)
        refresh_btn.click(load_page, inputs=[session_state], outputs=_page_outputs)

        session_selector.change(
            on_session_change,
            inputs=[session_state, session_selector, session_map_state],
            outputs=[plan_editor, plan_preview, plan_id_state, save_status],
        )

        generate_btn.click(
            on_generate,
            inputs=[session_state, session_selector, session_map_state, focus_hints_input],
            outputs=[plan_editor, plan_status, plan_preview],
        )

        save_btn.click(
            on_save,
            inputs=[session_state, session_selector, session_map_state, plan_editor, plan_id_state],
            outputs=[plan_id_state, save_status, plan_preview],
        )