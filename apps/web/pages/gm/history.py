"""GM story history tab — all events, log event form, generate session summary."""

from __future__ import annotations

import uuid
from typing import Any, Literal

import gradio as gr

from core.config import settings
from core.schemas import CampaignSession
from story.history import create_event, list_events
from story.session import list_sessions
from storage.sqlite.adapter import SQLiteBackend
from components.image_display import build_portrait_display

_backend = SQLiteBackend(settings.database_url)

_EVENT_TYPES = [
    "dialogue",
    "decision",
    "discovery",
    "combat_outcome",
    "npc_state_change",
    "world_change",
    "plot_thread_opened",
    "plot_thread_closed",
]

EventType = Literal[
    "dialogue", "decision", "discovery", "combat_outcome",
    "npc_state_change", "world_change", "plot_thread_opened", "plot_thread_closed",
]


def build_gm_history_page(session_state: gr.State) -> None:
    """Build the GM story history tab. Must be called inside a gr.Blocks context."""

    with gr.Tab("Story History"):
        gr.Markdown("## Campaign Story History (GM)")
        gr.Markdown(
            "Full event timeline including GM-only entries. "
            "Log new events and generate session summaries."
        )

        # ── Log Event Form ────────────────────────────────────────────────────
        with gr.Group():
            gr.Markdown("### Log Event")

            with gr.Row():
                log_session_selector = gr.Dropdown(
                    label="Session (optional)",
                    choices=["None (campaign-wide)"],
                    value="None (campaign-wide)",
                    interactive=True,
                    scale=3,
                )

            with gr.Row():
                event_type_input = gr.Dropdown(
                    label="Event Type",
                    choices=_EVENT_TYPES,
                    value="dialogue",
                    interactive=True,
                    scale=2,
                )
                is_public_checkbox = gr.Checkbox(
                    label="Public (visible to players)",
                    value=True,
                    scale=1,
                )

            event_content_input = gr.Textbox(
                label="Event Description",
                placeholder="Describe what happened…",
                lines=3,
            )

            participants_input = gr.Textbox(
                label="Participants (comma-separated names, optional)",
                placeholder="Kira Shadowstep, Lord Vane",
                lines=1,
            )

            with gr.Row():
                log_event_btn = gr.Button("Log Event", variant="primary")
                log_status = gr.Markdown("")

        # ── History Browser ───────────────────────────────────────────────────
        gr.Markdown("---")
        gr.Markdown("### Event Timeline")

        with gr.Row():
            view_session_selector = gr.Dropdown(
                label="Filter by Session",
                choices=["All Sessions"],
                value="All Sessions",
                interactive=True,
                scale=3,
            )
            refresh_btn = gr.Button("↻ Refresh", scale=1, min_width=100)

        history_display = gr.Dataframe(
            headers=["Session", "Type", "Public", "Event"],
            datatype=["str", "str", "str", "str"],
            label="Story Events",
            interactive=False,
            col_count=(4, "fixed"),
            wrap=True,
        )

        event_detail = gr.Markdown("")

        # ── Session Summary ───────────────────────────────────────────────────
        gr.Markdown("---")
        gr.Markdown("### Session Summary")

        summary_session_selector = gr.Dropdown(
            label="Select Session",
            choices=[],
            value=None,
            interactive=True,
        )
        generate_summary_btn = gr.Button(
            "Generate Session Summary",
            interactive=True,  # updated to False by session_state.change when ai_available=False
        )
        summary_display = gr.Markdown("")

        # ── Scene Illustration (T052) ─────────────────────────────────────────
        gr.Markdown("---")
        gr.Markdown("### Scene Illustration")
        gr.Markdown(
            "Generate an image from a scene description. "
            "Requires `HF_API_KEY` and `IMAGE_PROVIDER=huggingface` (or ComfyUI)."
        )

        scene_description_input = gr.Textbox(
            label="Scene Description",
            placeholder="Describe the scene you want to illustrate…",
            lines=3,
        )
        with gr.Row():
            generate_scene_btn = gr.Button(
                "Generate Scene Art",
                variant="secondary",
                interactive=False,  # enabled when ai_available=True
            )
            scene_status = gr.Markdown("")

        scene_image = build_portrait_display("Scene Illustration")

        # ── Internal state ────────────────────────────────────────────────────
        event_ids_state: gr.State = gr.State(value=[])
        session_map_state: gr.State = gr.State(value={})

        # ── Helpers ───────────────────────────────────────────────────────────
        async def _load_session_data(
            state: CampaignSession | None,
        ) -> tuple[dict[str, str], list[str]]:
            """Returns (session_map, session_label_list) for the current campaign."""
            if state is None:
                return {}, []
            async with await _backend.get_session() as db:
                sessions = await list_sessions(db, state.campaign_id)
            session_map = {
                f"Session {s.session_number}: {s.title}": str(s.id) for s in sessions
            }
            return session_map, list(session_map.keys())

        async def load_page(
            state: CampaignSession | None,
        ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, str], list[list[Any]], list[str], dict[str, Any], dict[str, Any]]:
            session_map, session_labels = await _load_session_data(state)
            log_choices = ["None (campaign-wide)"] + session_labels
            view_choices = ["All Sessions"] + session_labels
            summary_choices = session_labels
            ai_ok = state.ai_available if state is not None else False

            rows, ids = await _fetch_event_rows(state, "All Sessions", session_map)

            return (
                gr.update(choices=log_choices, value="None (campaign-wide)"),
                gr.update(choices=view_choices, value="All Sessions"),
                gr.update(choices=summary_choices, value=summary_choices[0] if summary_choices else None),
                session_map,
                rows,
                ids,
                gr.update(interactive=ai_ok),
                gr.update(interactive=ai_ok),
            )

        async def _fetch_event_rows(
            state: CampaignSession | None,
            selected_session: str,
            session_map: dict[str, str],
        ) -> tuple[list[list[Any]], list[str]]:
            if state is None:
                return [], []

            filter_session_id: uuid.UUID | None = None
            if selected_session and selected_session != "All Sessions":
                raw_id = session_map.get(selected_session)
                if raw_id:
                    filter_session_id = uuid.UUID(raw_id)

            async with await _backend.get_session() as db:
                sessions = await list_sessions(db, state.campaign_id)
                session_num_by_id = {str(s.id): s.session_number for s in sessions}
                events = await list_events(
                    db,
                    campaign_id=state.campaign_id,
                    role="gm",
                    session_id=filter_session_id,
                )

            rows: list[list[Any]] = []
            ids: list[str] = []
            for e in events:
                session_label = (
                    f"Session {session_num_by_id[str(e.session_id)]}"
                    if e.session_id and str(e.session_id) in session_num_by_id
                    else "—"
                )
                public_label = "Yes" if e.is_public else "GM only"
                preview = (e.content[:90] + "…") if len(e.content) > 90 else e.content
                rows.append([
                    session_label,
                    e.event_type.replace("_", " ").title(),
                    public_label,
                    preview,
                ])
                ids.append(str(e.id))

            return rows, ids

        async def on_refresh(
            state: CampaignSession | None,
            selected_session: str,
            session_map: dict[str, str],
        ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, str], list[list[Any]], list[str], dict[str, Any], dict[str, Any]]:
            return await load_page(state)

        async def on_view_session_change(
            state: CampaignSession | None,
            selected_session: str,
            session_map: dict[str, str],
        ) -> tuple[list[list[Any]], list[str]]:
            return await _fetch_event_rows(state, selected_session, session_map)

        async def on_log_event(
            state: CampaignSession | None,
            log_session: str,
            event_type: str,
            content: str,
            participants_raw: str,
            is_public: bool,
            session_map: dict[str, str],
        ) -> tuple[str, str, dict[str, Any], dict[str, str], list[list[Any]], list[str], dict[str, Any], dict[str, Any]]:
            if state is None:
                return "Error: not in a campaign session.", "", gr.update(), session_map, [], [], gr.update(), gr.update()
            if not content.strip():
                return "Event description cannot be empty.", "", gr.update(), session_map, [], [], gr.update(), gr.update()

            log_session_id: uuid.UUID | None = None
            if log_session and log_session != "None (campaign-wide)":
                raw_id = session_map.get(log_session)
                if raw_id:
                    log_session_id = uuid.UUID(raw_id)

            participants: list[dict] = []
            if participants_raw.strip():
                for name in participants_raw.split(","):
                    n = name.strip()
                    if n:
                        participants.append({"entity_type": "character", "entity_id": None, "name": n})

            async with await _backend.get_session() as db:
                await create_event(
                    db,
                    campaign_id=state.campaign_id,
                    event_type=event_type,
                    content=content.strip(),
                    is_public=is_public,
                    session_id=log_session_id,
                    participants=participants,
                )

            page = await load_page(state)
            _, new_session_map, view_update, updated_session_map, rows, ids, summary_btn_update, scene_btn_update = page
            return "✓ Event logged.", "", view_update, updated_session_map, rows, ids, summary_btn_update, scene_btn_update

        async def on_select_row(evt: gr.SelectData, ids: list[str]) -> str:
            if not ids or evt.index[0] >= len(ids):
                return ""
            from core.models import StoryEvent
            from sqlalchemy import select as sa_select
            event_id = uuid.UUID(ids[evt.index[0]])
            async with await _backend.get_session() as db:
                result = await db.execute(
                    sa_select(StoryEvent).where(StoryEvent.id == event_id)
                )
                event = result.scalar_one_or_none()
            if event is None:
                return "*Event not found.*"
            visibility = "**Public**" if event.is_public else "**GM only**"
            participants = ", ".join(p.get("name", "") for p in (event.participants or []))
            lines = [
                f"**{event.event_type.replace('_', ' ').title()}** · {visibility}",
                "",
                event.content,
            ]
            if participants:
                lines += ["", f"*Participants: {participants}*"]
            return "\n".join(lines)

        async def on_generate_scene(
            state: CampaignSession | None,
            description: str,
        ) -> tuple[str | None, str]:
            if state is None:
                return None, "Not in a campaign session."
            if not description.strip():
                return None, "Enter a scene description first."
            if not state.ai_available:
                return None, "AI features unavailable in degraded mode."

            from imagegen.factory import get_image_provider
            from imagegen.interface import ImageGenRequest

            scene_entity_id = uuid.uuid4()
            request = ImageGenRequest(
                prompt=description.strip(),
                style_hints=[
                    "fantasy scene",
                    "detailed",
                    "atmospheric illustration",
                    "Earthdawn tabletop RPG",
                ],
                entity_id=scene_entity_id,
            )

            provider = get_image_provider()
            response = await provider.generate(request)

            if response.error:
                return None, f"Scene generation failed: {response.error}"

            return response.image_url, "Scene illustration generated!"

        async def on_generate_summary(
            state: CampaignSession | None,
            selected_label: str,
            session_map: dict[str, str],
        ) -> str:
            if state is None:
                return "*Not in a campaign session.*"
            if not selected_label:
                return "*Select a session to summarise.*"
            raw_id = session_map.get(selected_label)
            if not raw_id:
                return "*Session not found.*"
            session_id = uuid.UUID(raw_id)

            async with await _backend.get_session() as db:
                events = await list_events(
                    db,
                    campaign_id=state.campaign_id,
                    role="gm",
                    session_id=session_id,
                )
            if not events:
                return "*No events recorded for this session yet.*"

            # Scene illustration wiring added in T052; for now render a text summary.
            lines = [f"**{selected_label} — Summary**", ""]
            for e in events:
                prefix = "📖" if e.is_public else "🔒"
                lines.append(f"{prefix} *{e.event_type.replace('_', ' ').title()}*: {e.content}")
            return "\n".join(lines)

        # ── Wire events ───────────────────────────────────────────────────────
        _page_outputs = [
            log_session_selector,
            view_session_selector,
            summary_session_selector,
            session_map_state,
            history_display,
            event_ids_state,
            generate_summary_btn,
            generate_scene_btn,
        ]

        session_state.change(load_page, inputs=[session_state], outputs=_page_outputs)
        refresh_btn.click(
            on_refresh,
            inputs=[session_state, view_session_selector, session_map_state],
            outputs=_page_outputs,
        )
        view_session_selector.change(
            on_view_session_change,
            inputs=[session_state, view_session_selector, session_map_state],
            outputs=[history_display, event_ids_state],
        )
        log_event_btn.click(
            on_log_event,
            inputs=[
                session_state,
                log_session_selector,
                event_type_input,
                event_content_input,
                participants_input,
                is_public_checkbox,
                session_map_state,
            ],
            outputs=[
                log_status,
                event_content_input,
                view_session_selector,
                session_map_state,
                history_display,
                event_ids_state,
                generate_summary_btn,
                generate_scene_btn,
            ],
        )
        history_display.select(
            on_select_row,
            inputs=[event_ids_state],
            outputs=[event_detail],
        )
        generate_summary_btn.click(
            on_generate_summary,
            inputs=[session_state, summary_session_selector, session_map_state],
            outputs=[summary_display],
        )
        generate_scene_btn.click(
            on_generate_scene,
            inputs=[session_state, scene_description_input],
            outputs=[scene_image, scene_status],
        )