"""Player story history tab — public events only, role-scoped and chronological."""

from __future__ import annotations

import uuid
from typing import Any

import gradio as gr
from core.config import settings
from core.schemas import CampaignSession
from storage.sqlite.adapter import SQLiteBackend
from story.history import list_events
from story.session import list_sessions

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


def build_player_history_page(session_state: gr.State) -> None:
    """Build the Player story history tab. Must be called inside a gr.Blocks context."""

    with gr.Tab("Story History"):
        gr.Markdown("## Campaign Story History")
        gr.Markdown(
            "Browse the shared campaign timeline. Only public events are shown."
        )

        with gr.Row():
            session_selector = gr.Dropdown(
                label="Filter by Session",
                choices=["All Sessions"],
                value="All Sessions",
                interactive=True,
                scale=3,
            )
            refresh_btn = gr.Button("↻ Refresh", scale=1, min_width=100)

        event_type_filter = gr.CheckboxGroup(
            label="Filter by Event Type",
            choices=_EVENT_TYPES,
            value=[],
        )

        history_display = gr.Dataframe(
            headers=["Session", "Type", "Event"],
            datatype=["str", "str", "str"],
            label="Story Events",
            interactive=False,
            column_count=(3, "fixed"),
            wrap=True,
        )

        event_detail = gr.Markdown("")

        event_ids_state: gr.State = gr.State(value=[])
        session_map_state: gr.State = gr.State(value={})

        async def load_sessions(
            state: CampaignSession | None,
        ) -> tuple[dict[str, Any], dict[str, str]]:
            if state is None:
                return gr.update(choices=["All Sessions"], value="All Sessions"), {}
            async with await _backend.get_session() as db:
                sessions = await list_sessions(db, state.campaign_id)
            session_map = {
                f"Session {s.session_number}: {s.title}": str(s.id) for s in sessions
            }
            choices = ["All Sessions"] + list(session_map.keys())
            return gr.update(choices=choices, value="All Sessions"), session_map

        async def load_events(
            state: CampaignSession | None,
            selected_session: str,
            type_filter: list[str],
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
                    role="player",
                    session_id=filter_session_id,
                )

            if type_filter:
                events = [e for e in events if e.event_type in type_filter]

            rows: list[list[Any]] = []
            ids: list[str] = []
            for e in events:
                session_label = (
                    f"Session {session_num_by_id[str(e.session_id)]}"
                    if e.session_id and str(e.session_id) in session_num_by_id
                    else "—"
                )
                preview = (e.content[:100] + "…") if len(e.content) > 100 else e.content
                rows.append([
                    session_label,
                    e.event_type.replace("_", " ").title(),
                    preview,
                ])
                ids.append(str(e.id))

            return rows, ids

        async def on_refresh(
            state: CampaignSession | None,
            selected_session: str,
            type_filter: list[str],
            session_map: dict[str, str],
        ) -> tuple[dict[str, Any], dict[str, str], list[list[Any]], list[str]]:
            session_dropdown_update, new_session_map = await load_sessions(state)
            rows, ids = await load_events(
                state, selected_session, type_filter, new_session_map
            )
            return session_dropdown_update, new_session_map, rows, ids

        async def on_session_or_filter_change(
            state: CampaignSession | None,
            selected_session: str,
            type_filter: list[str],
            session_map: dict[str, str],
        ) -> tuple[list[list[Any]], list[str]]:
            return await load_events(state, selected_session, type_filter, session_map)

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
            participants = ", ".join(
                p.get("name", "") for p in (event.participants or [])
            )
            event_type_label = event.event_type.replace("_", " ").title()
            lines = [f"**{event_type_label}**", "", event.content]
            if participants:
                lines += ["", f"*Participants: {participants}*"]
            return "\n".join(lines)

        session_state.change(
            on_refresh,
            inputs=[
                session_state, session_selector,
                event_type_filter, session_map_state,
            ],
            outputs=[
                session_selector, session_map_state,
                history_display, event_ids_state,
            ],
        )
        refresh_btn.click(
            on_refresh,
            inputs=[
                session_state, session_selector,
                event_type_filter, session_map_state,
            ],
            outputs=[
                session_selector, session_map_state,
                history_display, event_ids_state,
            ],
        )
        session_selector.change(
            on_session_or_filter_change,
            inputs=[
                session_state, session_selector,
                event_type_filter, session_map_state,
            ],
            outputs=[history_display, event_ids_state],
        )
        event_type_filter.change(
            on_session_or_filter_change,
            inputs=[
                session_state, session_selector,
                event_type_filter, session_map_state,
            ],
            outputs=[history_display, event_ids_state],
        )
        history_display.select(
            on_select_row,
            inputs=[event_ids_state],
            outputs=[event_detail],
        )