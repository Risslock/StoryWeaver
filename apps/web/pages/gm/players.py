"""GM players tab — read-only list of joined players and their characters."""

from __future__ import annotations

import uuid
from typing import Any

import gradio as gr
from core.config import settings
from core.models import Character, Player
from core.schemas import CampaignSession
from sqlalchemy import select
from storage.sqlite.adapter import SQLiteBackend

_backend = SQLiteBackend(settings.database_url)


async def _load_players(campaign_id: uuid.UUID) -> list[list[str]]:
    async with await _backend.get_session() as session:
        result = await session.execute(
            select(Player)
            .where(Player.campaign_id == campaign_id)
            .order_by(Player.created_at)
        )
        players = list(result.scalars().all())

        rows: list[list[str]] = []
        for player in players:
            char_name = "—"
            if player.character_id is not None:
                char_result = await session.execute(
                    select(Character).where(Character.id == player.character_id)
                )
                char = char_result.scalar_one_or_none()
                if char is not None:
                    char_name = char.name
            rows.append([player.player_name, char_name])
    return rows


def build_players_page(session_state: gr.State) -> None:
    """Build the GM players tab. Must be called inside a gr.Tabs context."""

    with gr.Tab("Players"):
        gr.Markdown("## Players")
        gr.Markdown("All players who have joined this campaign and their characters.")

        players_table = gr.Dataframe(
            headers=["Player Name", "Character Name"],
            datatype=["str", "str"],
            value=[],
            interactive=False,
            label=None,
        )
        refresh_btn = gr.Button("↻ Refresh", size="sm")
        load_status = gr.Markdown("")

        async def on_load(state: CampaignSession | None) -> tuple[Any, str]:
            if state is None:
                return gr.update(value=[]), ""
            try:
                rows = await _load_players(state.campaign_id)
                return gr.update(value=rows), ""
            except Exception as exc:
                return gr.update(value=[]), f"Error loading players: {exc}"

        session_state.change(
            on_load,
            inputs=[session_state],
            outputs=[players_table, load_status],
        )
        refresh_btn.click(
            on_load,
            inputs=[session_state],
            outputs=[players_table, load_status],
        )