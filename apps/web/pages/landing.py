"""Player campaign join flow."""

from __future__ import annotations

from typing import Any

import gradio as gr
from core.config import settings
from core.schemas import CampaignSession
from llm.providers.ollama import OllamaProvider
from storage.sqlite.adapter import SQLiteBackend
from storage.users import get_campaign_by_join_code, get_or_create_player

_backend = SQLiteBackend(settings.database_url)


def get_backend() -> SQLiteBackend:
    """Return the module-level storage backend singleton."""
    return _backend


def build_landing(session_state: gr.State) -> None:
    """Build the player join UI inside the current Blocks context.

    Players enter a 6-character join code and their player name. No campaign
    name is required — GMs share just the code. Returning players get the same
    Player record back via get_or_create_player().
    """
    gr.Markdown("### Join a Campaign")
    gr.Markdown(
        "Ask your GM for the 6-character join code, then enter your player name."
    )

    join_code_in = gr.Textbox(label="Join Code", placeholder="A3KP72", max_lines=1)
    join_name = gr.Textbox(
        label="Your Player Name", placeholder="Kira Stonefist", max_lines=1
    )
    join_btn = gr.Button("Join Campaign", variant="primary")
    join_status = gr.Markdown("")

    async def on_join(
        code: str,
        name: str,
    ) -> tuple[str, Any]:
        code = code.strip().upper()
        name = name.strip()

        if not code:
            return "Enter the join code your GM gave you.", None
        if not name:
            return "Enter your player name.", None

        async with await _backend.get_session() as session:
            campaign = await get_campaign_by_join_code(session, code)
            if campaign is None:
                return "No campaign found with that join code.", None

            await get_or_create_player(session, campaign.id, name)

        ai_available = await OllamaProvider().health_check()
        state = CampaignSession(
            campaign_id=campaign.id,
            display_name=name,
            role="player",
            join_code=campaign.join_code,
            ai_available=ai_available,
        )
        return f"Joined! Welcome, **{name}**.", state

    join_btn.click(
        on_join,
        inputs=[join_code_in, join_name],
        outputs=[join_status, session_state],
    )