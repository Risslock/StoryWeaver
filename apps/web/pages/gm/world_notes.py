"""GM world notes tab — single Markdown document stored on Campaign.world_notes."""

from __future__ import annotations

import uuid
from typing import Any

import gradio as gr
from core.config import settings
from core.models import Campaign
from core.schemas import CampaignSession
from sqlalchemy import select
from storage.sqlite.adapter import SQLiteBackend

_backend = SQLiteBackend(settings.database_url)


async def _load_notes(campaign_id: uuid.UUID) -> str:
    async with await _backend.get_session() as session:
        result = await session.execute(
            select(Campaign).where(Campaign.id == campaign_id)
        )
        campaign = result.scalar_one_or_none()
    return (campaign.world_notes or "") if campaign else ""


async def _save_notes(campaign_id: uuid.UUID, content: str) -> None:
    async with await _backend.get_session() as session:
        result = await session.execute(
            select(Campaign).where(Campaign.id == campaign_id)
        )
        campaign = result.scalar_one_or_none()
        if campaign is not None:
            campaign.world_notes = content
            await session.commit()


def build_world_notes_page(session_state: gr.State) -> None:
    """Build the GM world notes tab. Must be called inside a gr.Blocks context."""

    with gr.Tab("World Notes"):
        gr.Markdown("## World Notes")
        gr.Markdown(
            "Private lore, world-building details, and plot hooks. "
            "GM-only — never visible to players."
        )

        notes_editor = gr.Textbox(
            label="Notes (Markdown)",
            lines=20,
            placeholder="Write your world notes here using Markdown…",
        )
        with gr.Row():
            save_btn = gr.Button("Save Notes", variant="primary")
            save_status = gr.Markdown("")

        gr.Markdown("---")
        gr.Markdown("### Preview")
        notes_preview = gr.Markdown("")

        async def on_load(state: CampaignSession | None) -> tuple[Any, Any]:
            if state is None:
                return gr.update(value=""), gr.update(value="")
            try:
                text = await _load_notes(state.campaign_id)
                return gr.update(value=text), gr.update(value=text)
            except Exception as exc:
                return gr.update(value=""), gr.update(
                    value=f"Error loading notes: {exc}"
                )

        async def on_save(
            state: CampaignSession | None, content: str
        ) -> tuple[str, Any]:
            if state is None:
                return "Error: not in a campaign session.", gr.update()
            try:
                await _save_notes(state.campaign_id, content)
                return "Notes saved.", gr.update(value=content)
            except Exception as exc:
                return f"Error saving notes: {exc}", gr.update()

        session_state.change(
            on_load,
            inputs=[session_state],
            outputs=[notes_editor, notes_preview],
        )
        save_btn.click(
            on_save,
            inputs=[session_state, notes_editor],
            outputs=[save_status, notes_preview],
        )