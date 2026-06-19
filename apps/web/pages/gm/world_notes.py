"""GM world notes tab — private lore notes saved as GM-only story events."""

from __future__ import annotations

import uuid
from typing import Any

import gradio as gr
from core.config import settings
from core.models import StoryEvent
from core.schemas import CampaignSession
from sqlalchemy import select
from storage.sqlite.adapter import SQLiteBackend

_backend = SQLiteBackend(settings.database_url)


async def _save_world_note(campaign_id: uuid.UUID, content: str) -> StoryEvent:
    async with await _backend.get_session() as session:
        count_result = await session.execute(
            select(StoryEvent).where(
                StoryEvent.campaign_id == campaign_id,
                StoryEvent.event_type == "world_change",
            )
        )
        event_order = len(list(count_result.scalars().all()))

        event = StoryEvent(
            campaign_id=campaign_id,
            session_id=None,
            event_type="world_change",
            content=content,
            participants=[],
            is_public=False,
            event_order=event_order,
        )
        session.add(event)
        await session.commit()
        await session.refresh(event)
        return event


async def _load_world_notes(campaign_id: uuid.UUID) -> list[StoryEvent]:
    async with await _backend.get_session() as session:
        result = await session.execute(
            select(StoryEvent)
            .where(
                StoryEvent.campaign_id == campaign_id,
                StoryEvent.event_type == "world_change",
                StoryEvent.is_public.is_(False),
            )
            .order_by(StoryEvent.created_at.desc())
        )
        return list(result.scalars().all())


def build_world_notes_page(session_state: gr.State) -> None:
    """Build the GM world notes tab. Must be called inside a gr.Blocks context."""

    with gr.Tab("World Notes"):
        gr.Markdown("## World Notes")
        gr.Markdown(
            "Record private lore, world-building details, and plot hooks. "
            "These notes are GM-only and never visible to players."
        )

        note_editor = gr.Code(
            label="New Note (Markdown)",
            language="markdown",
            value="",
            lines=8,
        )

        with gr.Row():
            save_btn = gr.Button("Save Note", variant="primary")
            save_status = gr.Markdown("")

        gr.Markdown("---")
        gr.Markdown("### Notes History (newest first)")

        with gr.Row():
            refresh_btn = gr.Button("↻ Refresh")

        notes_table = gr.Dataframe(
            headers=["Date", "Preview"],
            datatype=["str", "str"],
            label="Saved World Notes",
            interactive=False,
            col_count=(2, "fixed"),
        )

        note_detail = gr.Markdown("")

        # Internal state: IDs matching table rows
        note_ids_state: gr.State = gr.State(value=[])

        async def load_notes(
            state: CampaignSession | None,
        ) -> tuple[list[list[Any]], list[str]]:
            if state is None:
                return [], []
            notes = await _load_world_notes(state.campaign_id)
            rows = [
                [
                    n.created_at.strftime("%Y-%m-%d %H:%M") if n.created_at else "—",
                    (n.content[:80] + "…") if len(n.content) > 80 else n.content,
                ]
                for n in notes
            ]
            ids = [str(n.id) for n in notes]
            return rows, ids

        async def on_save(
            state: CampaignSession | None,
            content: str,
        ) -> tuple[str, dict[str, Any], list[list[Any]], list[str]]:
            if state is None:
                return "Error: not in a campaign session.", gr.update(), [], []
            if not content.strip():
                return "Note content cannot be empty.", gr.update(), [], []
            await _save_world_note(state.campaign_id, content.strip())
            rows, ids = await load_notes(state)
            return "✓ Note saved.", gr.update(value=""), rows, ids

        async def on_refresh(
            state: CampaignSession | None,
        ) -> tuple[dict[str, Any], list[str]]:
            rows, ids = await load_notes(state)
            return gr.update(value=rows), ids

        async def on_select_row(evt: gr.SelectData, ids: list[str]) -> str:
            if not ids or evt.index[0] >= len(ids):
                return ""
            note_id = uuid.UUID(ids[evt.index[0]])
            async with await _backend.get_session() as session:
                result = await session.execute(
                    select(StoryEvent).where(StoryEvent.id == note_id)
                )
                note = result.scalar_one_or_none()
            if note is None:
                return "*Note not found.*"
            return note.content

        session_state.change(
            on_refresh,
            inputs=[session_state],
            outputs=[notes_table, note_ids_state],
        )
        refresh_btn.click(
            on_refresh,
            inputs=[session_state],
            outputs=[notes_table, note_ids_state],
        )
        save_btn.click(
            on_save,
            inputs=[session_state, note_editor],
            outputs=[save_status, note_editor, notes_table, note_ids_state],
        )
        notes_table.select(
            on_select_row,
            inputs=[note_ids_state],
            outputs=[note_detail],
        )